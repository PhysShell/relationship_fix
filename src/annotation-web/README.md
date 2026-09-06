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
- Persistent + SQLite for the entity model, queries and serialization
- `migrant-core` + `migrant-sqlite-simple` for the explicit schema history
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

Radio, checkbox and select inputs submit those wire codes directly rather than `yesod-form`'s positional indices, so the rendered HTML can be audited against the contract and a re-rendered form round-trips exactly the codes it was given.

## Current flow

```text
language
  -> instructions
  -> episode
      -> decision
          -> none_observed ---------------------------+
          -> abstained -> reason (+ note where required) -+
          -> assigned -> labels -> exact evidence span(s) -+
                                                       |
                                        optional item feedback
                                                       |
                                                    -> next
  -> submission.json
```

A respondent can reopen the decision of the item they are on from any later
step; the link goes to `/item/N/decision/edit`, which renders and writes
nothing. Changing the decision clears what it made stale — categories, quotes,
abstention reason and note — and that clearing lives in exactly one place, the
decision handler. Confirming the decision already on record is a different act
and keeps the work already entered.

Every transition is ordinary HTTP GET/POST/redirect. `runFormPost` provides CSRF-protected POST forms without JavaScript.

### Validation

Only a valid submission is persisted and redirected (POST/redirect/GET), so a reload never resubmits an answer.

A submission that fails validation is not redirected. The step is re-rendered in the same request with every value the respondent submitted, and each message is attached to the field that caused it. Nothing is written to SQLite. This matters for measurement, not only for comfort: an annotator who selects a span carefully, misses by one character and is handed an empty form is no longer being measured on the behaviour categories.

Cross-field rules follow the same principle. The note that `ambiguous_between_labels` and `other` require is reported under the note field rather than as a page-level banner.

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

## Item feedback is a separate axis

A respondent can also say something about the *item* rather than about the
interaction inside it: that the example sounds unnatural, that context is
missing, that the wording or translation raises questions. That is dogfood
evidence about the instrument, not an annotation, and conflating it with
observation labels or abstention reasons would make all three unreadable.

So it lives in its own module (`Feedback`), its own table (`ItemFeedback`) and
its own field of the submission. It is optional in content — an empty
submission is a valid answer — but it is a step in the flow, offered the same
way after every decision. It never affects `annotationComplete`, never becomes
an abstention and never touches labels.

```json
"feedback": { "flags": ["unnatural_example"], "note": "…" }
```

### Instrument version belongs to the session

Adding that field changes the submission contract, so new sessions are taken
under `annotation-web-dogfood-hs-v2`.

The version is recorded on the session when it starts, in `session_instrument`,
and every decision that depends on it is read from there rather than from the
running binary. A session that began before the feedback step existed has no
row, is therefore hs-v1, is never shown the feedback step, has `POST
/item/N/feedback` refused outright, and exports as hs-v1 without the `feedback`
key at all — because that key was not part of the contract it was taken under.

This is not tidiness. A live hs-v1 submission exists. Reading the version off
the deployment instead would let one unchanged database session be exported
under a version its respondent never saw, which is a provenance failure
regardless of how correct the answers are. If we ever want to ask an hs-v1
respondent whether an example sounded natural, that is post-hoc feedback with
its own provenance, not a step retroactively inserted into a run that already
happened.

`ontology_version` is untouched — the categories did not change.

#### Why a table and not a column

`instrument_version` began as a nullable column on `SurveySession`. Running that
migration against a copy of the live database failed:

    SQLite3 returned ErrorConstraint while attempting to perform step:
    FOREIGN KEY constraint failed

persistent-sqlite does not `ALTER TABLE ADD COLUMN`. It rebuilds the table —
create a backup, copy, `DROP TABLE survey_session`, recreate, copy back — and
dropping a table that `annotation` rows reference fails the foreign key check.
On the deployed database that is a server that does not start.

Creating a new table has no such problem. The migration this version actually
performs on a live hs-v1 database is two `CREATE TABLE` statements and nothing
else; `survey_session` is not touched, and its rows are not rewritten.

## Schema migrations

Schema change is explicit, ordered and owned by a separate executable. The
server does not migrate anything.

That split exists because of the failure above. Automatic migration means the
shape of a production table is decided by whatever persistent infers at start-up
from the entity model it happens to be compiled against, and persistent-sqlite's
answer to "add a column" is "drop the table and rebuild it". A migration that
destructive should be a deliberate act, reviewed as a diff, not a side effect of
a restart.

- `annotation-web-migrate` applies the history in `src/Schema.hs`, verifies the
  result and exits. It is the only thing that writes schema.
- `annotation-web` checks that the database is at the end of that history and
  refuses to serve if it is not.

The history is append-only, oldest first:

| Version | Contents |
| --- | --- |
| `0001-baseline-hs-v1` | `survey_session`, `annotation`, `annotation_label`, `evidence`, `audit_event` |
| `0002-session-instrument-and-item-feedback` | adds `session_instrument`, `item_feedback` |

`0001` is not "the schema as of the commit that introduced migrations". It is the
schema production was *already* running, transcribed from a real hs-v1 database
file, so that an existing deployment can be recognised as being at `0001` rather
than rebuilt from scratch on top of live data.

### What happens to a database that predates all of this

A file with tables in it and no `_migrations` table is either a legacy
production database or something nobody recognises. Which one is decided by
structure, not by hope: the migrator fingerprints the file from
`sqlite_master` plus `PRAGMA table_info`, `foreign_key_list`, `index_list` and
`index_info`, and compares it against what each prefix of the history builds
from empty. The longest exact match is recorded as already applied; the rest of
the history then runs normally.

Anything that matches no version is refused, and refused before anything is
written — a missing column, a dropped unique constraint, a missing foreign key
and an unexpected extra table are each enough. Matching *some* tables is not
matching a schema.

The whole run — reading the history, deciding, writing schema, verifying — is a
single SQLite transaction, so a migration that throws halfway leaves the file
exactly as it was found, migration bookkeeping included.

### What the checks actually check

After the statements run, three independent things have to agree, and none of
them is the migrator's own report:

- the structural fingerprint of the file equals the fingerprint of a database
  built from the history in an empty `:memory:` database;
- `PRAGMA foreign_key_check` returns no rows and `PRAGMA integrity_check`
  returns `ok`;
- persistent, asked via `showMigration` and reading the entity model rather
  than the migration list, has no statement left it wants to run.

The third is the one that matters most. Migrant can only tell us that the
migrations it knows about ran. Persistent is the independent judge of whether
the resulting schema is the one the application's queries were compiled
against.

### The limitation worth stating

`migrant-sqlite-simple` records applied migration *names*, in order, and
nothing else — no checksum of the migration body. Migrant alone therefore
cannot tell that `0001` is still the `0001` that was applied to production.

What partly covers that here is the fingerprint check, which runs on every
migrate and every server start: editing an already-applied migration in a way
that changes the resulting schema makes the live file stop matching, loudly, on
the next run. An edit that leaves the structure identical is not detected. That
is a documented limitation, not a guarantee.

### How deployment sequences it

`deploy/activate.sh` ships inside the release it activates, alongside both
binaries, and owns the order: quiesce, verify, back up, verify the backup,
migrate, verify, activate, health-check, and on failure put the database *and*
the release back together. Because writers are stopped before the backup is
taken, the rollback unit is the whole world rather than a reverse migration —
there are no down migrations here and there are not meant to be.

The one thing it will not do automatically is restore a backup after rows have
been written to the new schema, because that would not be a rollback. See
`docs/runbooks/annotation-web-deploy.md`, and `deploy/test/matrix.sh` for the
nine failure scenarios that keep it honest.

## Persistence

SQLite stores:

- survey sessions;
- per-item decisions;
- selected labels;
- evidence quotes;
- abstention reasons/notes;
- whether the source original was revealed;
- optional item-quality feedback, separately from the annotation;
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
stack run annotation-web-migrate
stack run annotation-web
```

Schema first, server second: the server will not create or migrate a database,
and says so rather than starting. `annotation-web-migrate` is idempotent — a
second run applies nothing.

The server listens on `127.0.0.1:8080` by default.

Useful environment variables:

```text
RF_DB_PATH            SQLite path, default annotation.db (both executables)
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

All routes are rendered as relative URLs (`approot = ApprootRelative`). Yesod's
default `guessApproot` would derive absolute URLs from the loopback request,
which is plain HTTP, so behind a TLS-terminating proxy every form action would
come out as `http://host/...` on an `https://` page and be rejected by the
`form-action 'self'` directive in the app's own Content-Security-Policy.

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
