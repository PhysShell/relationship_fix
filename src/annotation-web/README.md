# annotation-web

Server-rendered, JavaScript-free dogfood UI for the Relationship Fix annotation protocol.

## Why this exists

The Tally prototype was useful for discovering UX and ontology problems, but multilingual presentation required duplicating presentation blocks while answer blocks needed stable IDs. That made `presentation_language` only partially true and made the instrument increasingly difficult to audit.

This app makes the boundary explicit:

- `presentation_language` controls all respondent-facing language;
- stored decisions and label IDs are language-independent;
- an item has exactly one `source_language`;
- `Show original` exists only when `source_language /= presentation_language`;
- scientific functionality does not depend on client-side JavaScript;
- responses and navigation state are durable in SQLite;
- the final dogfood submission is exported as JSON.

Tally v7 is a historical dogfood artifact and should not receive further protocol features.

## Stack

- Haskell, GHC 9.10.3 via Stackage LTS 24.57
- Yesod
- `yesod-form` for server-rendered forms and CSRF validation
- Persistent + SQLite
- Hamlet + Lucius
- Warp bound to `127.0.0.1`
- no client-side JavaScript

The CI has an explicit source check that fails if a `<script>` element or JavaScript source is introduced under `app/`, `src/`, or `test/`.

## Domain model

The protocol states are algebraic data types rather than loosely related strings/booleans:

```haskell
data Language = RU | EN

data Decision
  = Assigned
  | NoneObserved
  | Abstained

data BehaviorLabel
  = BlameCriticism
  | PressureForChange
  | Validation
  | RepairAttempt
  | AvoidanceTopicShift
```

Stable wire codes remain the research contract, e.g. `B.REPAIR_ATTEMPT`, `none_observed`, and `insufficient_context`.

## Current flow

```text
language
  -> instructions
  -> episode
      -> decision
          -> none_observed -> next
          -> abstained -> reason (+ note where required) -> next
          -> assigned -> labels -> exact evidence span(s) -> next
  -> submission.json
```

Every transition is ordinary HTTP GET/POST/redirect. `runFormPost` provides CSRF-protected POST forms without JavaScript.

## Original / translation invariant

For an item whose source is Russian:

```text
presentation_language = ru
  -> Russian source text
  -> no "Show original"

presentation_language = en
  -> English presentation translation
  -> "Show original" reveals the Russian source
```

For an English source item the rule is reversed. `original_revealed` is persisted and included in the submission.

## Persistence

SQLite stores:

- survey sessions;
- per-item decisions;
- selected labels;
- evidence quotes;
- abstention reasons/notes;
- whether the source original was revealed;
- a small audit event stream for dogfood UX analysis.

The browser session contains only Yesod session state including the opaque database session id and CSRF state. Annotation answers are not stored in the cookie.

Runtime files are gitignored:

- `annotation.db`, `annotation.db-wal`, `annotation.db-shm`;
- `client-session-key.aes`;
- Stack/Cabal build output.

## Run locally

From this directory:

```bash
stack test
stack run annotation-web
```

The server listens on `127.0.0.1:8080` by default.

Useful environment variables:

```text
RF_DB_PATH            SQLite path, default annotation.db
RF_SESSION_KEY_PATH   Yesod client-session key, default client-session-key.aes
RF_SECURE_COOKIES     1/true/yes enables Secure session cookies
PORT                   listen port, default 8080
```

For local plain HTTP, leave `RF_SECURE_COOKIES` unset. For deployment behind HTTPS, set it to `1`.

## Vultr VPS target

The intended small deployment is:

```text
Internet
   |
 Caddy :443
   |
   v
annotation-web 127.0.0.1:8080
   |
   v
SQLite
```

Example Caddy route:

```caddyfile
annotate.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Run the binary as an unprivileged service account. Keep the database and session key under a restricted directory such as `/var/lib/relationship-fix/` and never commit either file.

Production-style environment:

```text
RF_DB_PATH=/var/lib/relationship-fix/annotation.db
RF_SESSION_KEY_PATH=/var/lib/relationship-fix/client-session-key.aes
RF_SECURE_COOKIES=1
PORT=8080
```

Only Caddy should be Internet-facing; port 8080 remains loopback-only.

## Dogfood scope

The runtime currently contains only fresh `dg-04` .. `dg-09` challenge items. It deliberately does not import the frozen 40-item annotation pilot and must not be treated as scientific evidence.

Before promotion into a scientific run, freeze a new instrument and bind at least:

1. ontology hash/version;
2. item-set hash/version;
3. reviewed RU/EN presentation translations and hashes;
4. instructions and UI presentation version;
5. annotator eligibility and deterministic ordering policy;
6. data-retention policy;
7. rendered-language/source-original invariants;
8. immutable submission/provenance contract.

Dogfood output is debugging evidence about the instrument, not construct-validation evidence.
