package model

import "time"

type Language string

const (
	LanguageRU Language = "ru"
	LanguageEN Language = "en"
)

type Decision string

const (
	DecisionAssigned     Decision = "assigned"
	DecisionNoneObserved Decision = "none_observed"
	DecisionAbstained    Decision = "abstained"
)

type Message struct {
	Author string `json:"author"`
	Text   string `json:"text"`
	Target bool   `json:"target,omitempty"`
}

type Presentation struct {
	Context              string `json:"context"`
	Target               string `json:"target"`
	TranslationProvenance string `json:"translation_provenance"`
}

type Item struct {
	ID             string                    `json:"id"`
	SourceLanguage Language                  `json:"source_language"`
	Source         []Message                 `json:"source"`
	Presentation   map[Language]Presentation `json:"presentation"`
}

type Label struct {
	ID          string            `json:"id"`
	DisplayName map[Language]string `json:"display_name"`
}

type Annotation struct {
	ItemID           string            `json:"item_id"`
	Decision         Decision          `json:"decision"`
	Labels           []string          `json:"labels,omitempty"`
	Evidence         map[string]string `json:"evidence,omitempty"`
	AbstentionReason string            `json:"abstention_reason,omitempty"`
	OriginalRevealed bool              `json:"original_revealed"`
}

type Submission struct {
	InstrumentVersion     string       `json:"instrument_version"`
	PresentationVersion   string       `json:"presentation_version"`
	OntologyVersion       string       `json:"ontology_version"`
	PresentationLanguage  Language     `json:"presentation_language"`
	StartedAt             time.Time    `json:"started_at"`
	CompletedAt           time.Time    `json:"completed_at"`
	Annotations           []Annotation `json:"annotations"`
}
