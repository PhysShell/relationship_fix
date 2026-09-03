package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/a-h/templ"

	"github.com/PhysShell/relationship_fix/src/annotation-web/internal/catalog"
	"github.com/PhysShell/relationship_fix/src/annotation-web/internal/model"
	"github.com/PhysShell/relationship_fix/src/annotation-web/internal/session"
	"github.com/PhysShell/relationship_fix/src/annotation-web/internal/views"
)

const sessionCookie = "rf_annotation_session"

type app struct {
	store *session.Store
}

func main() {
	a := &app{store: session.NewStore()}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /", a.home)
	mux.HandleFunc("POST /language", a.chooseLanguage)
	mux.HandleFunc("GET /intro", a.intro)
	mux.HandleFunc("GET /item/{index}", a.item)
	mux.HandleFunc("POST /item/{index}/decision", a.decision)
	mux.HandleFunc("POST /item/{index}/labels", a.labels)
	mux.HandleFunc("POST /item/{index}/evidence", a.evidence)
	mux.HandleFunc("POST /item/{index}/abstain", a.abstain)
	mux.HandleFunc("POST /item/{itemID}/original", a.original)
	mux.HandleFunc("GET /done", a.done)
	mux.HandleFunc("GET /submission.json", a.submission)
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.Dir("static"))))

	server := &http.Server{
		Addr:              ":8080",
		Handler:           securityHeaders(mux),
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf("annotation-web listening on http://localhost%s", server.Addr)
	log.Fatal(server.ListenAndServe())
}

func (a *app) home(w http.ResponseWriter, r *http.Request) {
	if _, ok := a.currentSession(r); ok {
		http.Redirect(w, r, "/intro", http.StatusSeeOther)
		return
	}
	render(w, r, views.LanguagePage())
}

func (a *app) chooseLanguage(w http.ResponseWriter, r *http.Request) {
	language := model.Language(r.FormValue("language"))
	if language != model.LanguageRU && language != model.LanguageEN {
		http.Error(w, "invalid language", http.StatusBadRequest)
		return
	}
	s := a.store.Create(language)
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookie,
		Value:    s.ID,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
	})
	http.Redirect(w, r, "/intro", http.StatusSeeOther)
}

func (a *app) intro(w http.ResponseWriter, r *http.Request) {
	s, ok := a.requireSession(w, r)
	if !ok {
		return
	}
	render(w, r, views.IntroPage(s.PresentationLanguage))
}

func (a *app) item(w http.ResponseWriter, r *http.Request) {
	s, ok := a.requireSession(w, r)
	if !ok {
		return
	}
	index, ok := parseIndex(w, r.PathValue("index"))
	if !ok {
		return
	}
	if index >= len(catalog.Items) {
		http.Redirect(w, r, "/done", http.StatusSeeOther)
		return
	}
	item := catalog.Items[index]
	state := session.EnsureItem(s, item.ID)
	step := "decision"
	if state.Decision == model.DecisionAssigned {
		if len(state.Labels) == 0 {
			step = "labels"
		} else {
			step = "evidence"
		}
	} else if state.Decision == model.DecisionAbstained {
		step = "abstain"
	}
	render(w, r, views.ItemPage(s.PresentationLanguage, item, index, len(catalog.Items), step, catalog.Labels, state.Labels, state.OriginalRevealed, ""))
}

func (a *app) decision(w http.ResponseWriter, r *http.Request) {
	s, index, item, ok := a.itemContext(w, r)
	if !ok {
		return
	}
	decision := model.Decision(r.FormValue("decision"))
	if decision != model.DecisionAssigned && decision != model.DecisionNoneObserved && decision != model.DecisionAbstained {
		render(w, r, views.ItemPage(s.PresentationLanguage, item, index, len(catalog.Items), "decision", catalog.Labels, nil, false, localized(s.PresentationLanguage, "Выберите один вариант.", "Choose one option.")))
		return
	}
	a.store.Update(s.ID, func(s *session.Session) {
		state := session.EnsureItem(s, item.ID)
		state.Decision = decision
		state.Labels = nil
		state.Evidence = map[string]string{}
		state.AbstentionReason = ""
	})
	if decision == model.DecisionNoneObserved {
		a.advance(w, r, s, index)
		return
	}
	http.Redirect(w, r, fmt.Sprintf("/item/%d", index), http.StatusSeeOther)
}

func (a *app) labels(w http.ResponseWriter, r *http.Request) {
	s, index, item, ok := a.itemContext(w, r)
	if !ok {
		return
	}
	selected := r.Form["labels"]
	selected = validLabels(selected)
	if len(selected) == 0 {
		state := session.EnsureItem(s, item.ID)
		render(w, r, views.ItemPage(s.PresentationLanguage, item, index, len(catalog.Items), "labels", catalog.Labels, state.Labels, state.OriginalRevealed, localized(s.PresentationLanguage, "Выберите хотя бы одну категорию.", "Select at least one category.")))
		return
	}
	a.store.Update(s.ID, func(s *session.Session) {
		state := session.EnsureItem(s, item.ID)
		state.Labels = selected
		state.Evidence = map[string]string{}
	})
	http.Redirect(w, r, fmt.Sprintf("/item/%d", index), http.StatusSeeOther)
}

func (a *app) evidence(w http.ResponseWriter, r *http.Request) {
	s, index, item, ok := a.itemContext(w, r)
	if !ok {
		return
	}
	state := session.EnsureItem(s, item.ID)
	if state.Decision != model.DecisionAssigned || len(state.Labels) == 0 {
		http.Redirect(w, r, fmt.Sprintf("/item/%d", index), http.StatusSeeOther)
		return
	}
	evidence := make(map[string]string, len(state.Labels))
	for _, label := range state.Labels {
		value := strings.TrimSpace(r.FormValue("evidence_" + label))
		if value == "" || !strings.Contains(item.Presentation[s.PresentationLanguage].Target, value) {
			render(w, r, views.ItemPage(s.PresentationLanguage, item, index, len(catalog.Items), "evidence", catalog.Labels, state.Labels, state.OriginalRevealed, localized(s.PresentationLanguage, "Каждая цитата должна быть точным непрерывным фрагментом target message.", "Every evidence quote must be an exact continuous span from the target message.")))
			return
		}
		evidence[label] = value
	}
	a.store.Update(s.ID, func(s *session.Session) {
		state := session.EnsureItem(s, item.ID)
		state.Evidence = evidence
	})
	a.advance(w, r, s, index)
}

func (a *app) abstain(w http.ResponseWriter, r *http.Request) {
	s, index, item, ok := a.itemContext(w, r)
	if !ok {
		return
	}
	reason := r.FormValue("reason")
	if !validAbstentionReason(reason) {
		state := session.EnsureItem(s, item.ID)
		render(w, r, views.ItemPage(s.PresentationLanguage, item, index, len(catalog.Items), "abstain", catalog.Labels, nil, state.OriginalRevealed, localized(s.PresentationLanguage, "Выберите причину abstained.", "Choose an abstention reason.")))
		return
	}
	a.store.Update(s.ID, func(s *session.Session) {
		state := session.EnsureItem(s, item.ID)
		state.AbstentionReason = reason
	})
	a.advance(w, r, s, index)
}

func (a *app) original(w http.ResponseWriter, r *http.Request) {
	s, ok := a.requireSession(w, r)
	if !ok {
		return
	}
	itemID := r.PathValue("itemID")
	index := -1
	for i, item := range catalog.Items {
		if item.ID == itemID {
			index = i
			if item.SourceLanguage == s.PresentationLanguage {
				http.Error(w, "original is already the presentation", http.StatusBadRequest)
				return
			}
			break
		}
	}
	if index < 0 {
		http.NotFound(w, r)
		return
	}
	a.store.Update(s.ID, func(s *session.Session) {
		state := session.EnsureItem(s, itemID)
		state.OriginalRevealed = true
	})
	http.Redirect(w, r, fmt.Sprintf("/item/%d", index), http.StatusSeeOther)
}

func (a *app) done(w http.ResponseWriter, r *http.Request) {
	s, ok := a.requireSession(w, r)
	if !ok {
		return
	}
	render(w, r, views.DonePage(s.PresentationLanguage))
}

func (a *app) submission(w http.ResponseWriter, r *http.Request) {
	s, ok := a.requireSession(w, r)
	if !ok {
		return
	}
	annotations := make([]model.Annotation, 0, len(catalog.Items))
	for _, item := range catalog.Items {
		state := session.EnsureItem(s, item.ID)
		annotations = append(annotations, model.Annotation{
			ItemID:           item.ID,
			Decision:         state.Decision,
			Labels:           append([]string(nil), state.Labels...),
			Evidence:         state.Evidence,
			AbstentionReason: state.AbstentionReason,
			OriginalRevealed: state.OriginalRevealed,
		})
	}
	out := model.Submission{
		InstrumentVersion:    "annotation-web-dogfood-v1",
		PresentationVersion:  "presentation-v1",
		OntologyVersion:      "behavior-v0.2-candidate",
		PresentationLanguage: s.PresentationLanguage,
		StartedAt:            s.StartedAt,
		CompletedAt:          time.Now().UTC(),
		Annotations:          annotations,
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Content-Disposition", "attachment; filename=relationship-fix-submission.json")
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	_ = enc.Encode(out)
}

func (a *app) advance(w http.ResponseWriter, r *http.Request, s *session.Session, index int) {
	next := index + 1
	a.store.Update(s.ID, func(s *session.Session) { s.CurrentItem = next })
	if next >= len(catalog.Items) {
		http.Redirect(w, r, "/done", http.StatusSeeOther)
		return
	}
	http.Redirect(w, r, fmt.Sprintf("/item/%d", next), http.StatusSeeOther)
}

func (a *app) itemContext(w http.ResponseWriter, r *http.Request) (*session.Session, int, model.Item, bool) {
	s, ok := a.requireSession(w, r)
	if !ok {
		return nil, 0, model.Item{}, false
	}
	index, ok := parseIndex(w, r.PathValue("index"))
	if !ok || index >= len(catalog.Items) {
		if ok {
			http.NotFound(w, r)
		}
		return nil, 0, model.Item{}, false
	}
	return s, index, catalog.Items[index], true
}

func (a *app) currentSession(r *http.Request) (*session.Session, bool) {
	cookie, err := r.Cookie(sessionCookie)
	if err != nil {
		return nil, false
	}
	return a.store.Get(cookie.Value)
}

func (a *app) requireSession(w http.ResponseWriter, r *http.Request) (*session.Session, bool) {
	s, ok := a.currentSession(r)
	if !ok {
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return nil, false
	}
	return s, true
}

func parseIndex(w http.ResponseWriter, raw string) (int, bool) {
	index, err := strconv.Atoi(raw)
	if err != nil || index < 0 {
		http.Error(w, "invalid item index", http.StatusBadRequest)
		return 0, false
	}
	return index, true
}

func validLabels(input []string) []string {
	known := map[string]bool{}
	for _, label := range catalog.Labels {
		known[label.ID] = true
	}
	out := make([]string, 0, len(input))
	seen := map[string]bool{}
	for _, value := range input {
		if known[value] && !seen[value] {
			seen[value] = true
			out = append(out, value)
		}
	}
	return out
}

func validAbstentionReason(value string) bool {
	switch value {
	case "insufficient_context", "ambiguous_between_labels", "unit_not_applicable", "source_corrupted", "language_unsupported", "other":
		return true
	default:
		return false
	}
}

func localized(language model.Language, ru, en string) string {
	if language == model.LanguageEN {
		return en
	}
	return ru
}

func render(w http.ResponseWriter, r *http.Request, component templ.Component) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := component.Render(r.Context(), w); err != nil {
		log.Printf("render: %v", err)
	}
}

func securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Security-Policy", "default-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		next.ServeHTTP(w, r)
	})
}
