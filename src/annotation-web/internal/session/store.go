package session

import (
	"crypto/rand"
	"encoding/hex"
	"sync"
	"time"

	"github.com/PhysShell/relationship_fix/src/annotation-web/internal/model"
)

type ItemState struct {
	Decision         model.Decision
	Labels           []string
	Evidence         map[string]string
	AbstentionReason string
	OriginalRevealed bool
}

type Session struct {
	ID                   string
	PresentationLanguage model.Language
	CurrentItem           int
	StartedAt             time.Time
	Items                 map[string]*ItemState
}

type Store struct {
	mu       sync.RWMutex
	sessions map[string]*Session
}

func NewStore() *Store {
	return &Store{sessions: map[string]*Session{}}
}

func (s *Store) Create(language model.Language) *Session {
	id := randomID()
	session := &Session{
		ID:                   id,
		PresentationLanguage: language,
		StartedAt:             time.Now().UTC(),
		Items:                 map[string]*ItemState{},
	}
	s.mu.Lock()
	s.sessions[id] = session
	s.mu.Unlock()
	return session
}

func (s *Store) Get(id string) (*Session, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	v, ok := s.sessions[id]
	return v, ok
}

func (s *Store) Update(id string, fn func(*Session)) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	v, ok := s.sessions[id]
	if !ok {
		return false
	}
	fn(v)
	return true
}

func EnsureItem(s *Session, itemID string) *ItemState {
	state, ok := s.Items[itemID]
	if !ok {
		state = &ItemState{Evidence: map[string]string{}}
		s.Items[itemID] = state
	}
	if state.Evidence == nil {
		state.Evidence = map[string]string{}
	}
	return state
}

func randomID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b[:])
}
