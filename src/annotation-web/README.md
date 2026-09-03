# annotation-web

Server-rendered, JavaScript-free dogfood UI for the Relationship Fix annotation protocol.

## Why this exists

The Tally prototype was useful for discovering UX and ontology problems, but multilingual presentation required duplicating presentation blocks while answer blocks needed stable IDs. That made the form increasingly hard to reason about and made `presentation_language` only partially true.

This app makes the boundary explicit:

- `presentation_language` controls all respondent-facing language;
- stored decisions and label IDs are language-independent;
- an item has exactly one `source_language`;
- `Show original` appears only when `source_language != presentation_language`;
- no scientific functionality depends on client-side JavaScript;
- the server emits the final debug submission as JSON.

Tally v7 remains a historical dogfood artifact and should not receive further protocol features.

## Stack

- Go
- `net/http`
- `github.com/a-h/templ` v0.3.1020
- plain CSS
- no JavaScript
- in-memory sessions for dogfood only

## Run

From this directory:

```bash
go run github.com/a-h/templ/cmd/templ@v0.3.1020 generate
go mod tidy
go run .
```

Then open `http://localhost:8080`.

The current server uses only the fresh `dg-04` .. `dg-09` dogfood items. It deliberately does not import the frozen 40-item pilot and must not be treated as scientific evidence.

## Current flow

```text
language
  -> instructions
  -> episode
      -> decision
          -> none_observed -> next
          -> abstained -> reason -> next
          -> assigned -> labels -> exact evidence span(s) -> next
  -> submission.json
```

Every navigation transition is a normal HTTP GET/POST/redirect. No JS is required.

## Original/translation invariant

For an item whose source is Russian:

```text
presentation_language = ru
  -> Russian source text
  -> no "Show original"

presentation_language = en
  -> English presentation translation
  -> "Show original" reveals the Russian source
```

For an English source item the rule is exactly reversed.

The persisted meaning never changes with presentation language:

```json
{
  "decision": "assigned",
  "labels": ["B.VALIDATION"]
}
```

## Dogfood limitations

The current implementation intentionally has no durable database. Restarting the process loses sessions. Download `submission.json` before shutdown.

Before use with external annotators, at minimum add:

1. durable append-only submission storage;
2. CSRF protection for non-local deployment;
3. frozen dataset/ontology/presentation hashes in every submission;
4. reviewed/frozen RU/EN translations;
5. deterministic annotator-specific item ordering;
6. resume semantics that survive process restarts;
7. tests that render both languages and prove source/original invariants;
8. deployment configuration and an explicit data-retention policy.

Do not quietly turn this dogfood server into the scientific run. Freeze a new instrument version first.
