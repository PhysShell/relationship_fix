# Deploying a schema-changing release of annotation-web

## What this protects against

The application will not migrate its own database. It reads the schema, checks
that it is the one its queries were compiled against, and refuses to serve
anything else. That refusal is only safe because something writes the schema at
a moment when nobody is reading or writing rows, with a verified way back — and
that something is `deploy/activate.sh`, shipped inside the release it activates.

The shape is stop-the-world, deliberately. This instrument collects relationship
annotations from a handful of people; an honest short outage that can be tested
end to end beats a zero-downtime dual-schema choreography that cannot be.

```
quiesce → verify → back up → verify the backup → migrate → verify
        → activate → health → keep it, or go back
```

Because writers are stopped **before** the backup is taken, "go back" can be the
whole world: the database file and the release together. That is a much better
rollback unit than a reverse migration. Down migrations look symmetric right up
until an up migration transformed or dropped something, at which point the
symmetry quietly stops existing. There are no down migrations here and there is
not meant to be.

## Release identity

One store path carries all three of:

```
/nix/store/…-relationship-fix-annotation-web
├── bin/annotation-web             the server
├── bin/annotation-web-migrate     the only thing that writes schema
└── bin/annotation-web-activate    the choreography
```

The workflow builds one path, copies one path, and runs the activation script
out of that path. The script then uses `$RELEASE/bin/…` for everything and never
consults `PATH`. It also checks, before touching anything, that both binaries
resolve to somewhere inside the release. "Migration from release 17,
application from release 18, database from who knows where" is therefore not a
state this pipeline can reach.

## The three states, and where the boundary is

**A — the migration failed.** Writers are stopped, the backup is verified, and
nothing is serving the new release yet. The script restores the backup
unconditionally (it does not rely on the migration having been atomic, even
though the test suite shows that it is), puts the previous release back, and
health-checks it. Exit 12.

**B — the migration succeeded, the new release is unhealthy.** Writers were
stopped for the whole migration, and the health check failed. If nothing was
written in the meantime, this is identical to state A: restore the backup, roll
the profile back, start the previous release. Exit 13.

**C — the new release was reachable and something was written.** The backup no
longer describes the database. Restoring it would not be a rollback; it would be
deleting a respondent's answer. The script refuses, leaves the service stopped,
and exits 14.

The boundary between B and C is decided by evidence, not by a clock:

```
backup verified
      │
   migrate
      │
   verify
      │
 DIGEST A          ← after the migration, before anything is started
      │
    start
      │
 health FAIL
      │
   stop  ← confirmed, not attempted
      │
 DIGEST B
    /     \
A == B    A != B
   │         │
restore    refuse,
DB + old   exit 14
release
```

Two things about that ordering are load-bearing and easy to get wrong.

**A is taken after the migration, not before.** The question is "has anything
changed since the new application became reachable", not "did the migration
change anything". Take A before the migration and the first real data migration
— any `UPDATE` at all — makes every rollback look like it would destroy data, and
a perfectly safe deploy refuses to roll back. That failure would surface months
later, on the one night it matters. `matrix.sh` has a scenario whose migration
rewrites rows and whose server is then unhealthy: it must exit 13, and moving
the baseline earlier turns it red.

**B is taken only after the stop is confirmed.** A digest read while something
can still write is several moments stitched together, and overwriting a database
based on that is worse than not deciding at all. If the unhealthy release will
not stop, there is no evidence to be had and no automatic action to take: exit
15, nothing restored. The digest itself is also taken inside a single SQLite read
transaction, so it describes one snapshot even if that expectation is violated.

Comparing the file byte for byte would not work at all: merely opening a WAL
database rewrites parts of it, so the bytes change when nothing was stored.

## Exit codes

| Code | Meaning | State of the host |
| --- | --- | --- |
| 0 | activated and healthy | new release serving |
| 10 | refused during preflight | untouched, previous release still serving |
| 11 | refused before migrating | database unchanged, previous release restarted |
| 12 | migration failed | database restored, previous release restarted |
| 13 | new release unhealthy, no writes | database restored, previous release restarted |
| 14 | new release unhealthy, **writes present** | service **stopped**, needs a person |
| 15 | the recovery path itself failed | service down, needs a person |

## If you get exit 14

Do not re-run the deploy, and do not restore the backup reflexively.

1. The database is at the new schema and contains rows the backup does not.
2. The new release is stopped because it is unhealthy.
3. The previous release generally *cannot* be started against the new schema —
   it will refuse, which is correct behaviour and not a second bug.

The realistic options, in order of preference: fix forward and deploy a healthy
release against the schema that is already there; or extract the new rows,
restore the backup, and reapply them by hand. Discarding them is a decision a
person makes explicitly, never one the pipeline makes quietly.

## Why a plain copy is a sound backup here

`cp` of a live SQLite database is not a snapshot, and the WAL makes that worse
rather than better. It is sound in this script for two specific reasons, both of
which are checked rather than assumed:

1. **The copy happens after confirmed quiescence.** The service is stopped and
   the stop is polled until the process is actually gone; a stop that does not
   confirm is exit 10 with nothing else touched. The database file, its `-wal`
   and its `-shm` are then copied together, because a service that was killed
   rather than shut down cleanly leaves a WAL that is part of the database.
2. **The copy is then verified as a database.** `annotation-web-migrate
   integrity` runs against the copy, and its row digest is compared against the
   live one. A truncated or torn copy fails one or both. That is a stronger
   guarantee than "we called the right API": it is a check on the artifact, not
   a claim about the method.

If quiescence ever stops being guaranteed, this reasoning collapses and the
backup needs `VACUUM INTO` or the online backup API instead. That is why the
stop is a hard failure and not a best effort.

## Verifying the layer without a VPS

```bash
cd src/annotation-web && stack build --system-ghc --pedantic --test
./deploy/test/matrix.sh "$(cd src/annotation-web && stack path --system-ghc --local-install-root)/bin"
```

The matrix runs the real `activate.sh` and the real binaries against a fake
host — no systemd, no sudo, no network — and covers:

| Scenario | Expected |
| --- | --- |
| old schema + new binary, unmigrated | REFUSE |
| migration + health both succeed | DEPLOY |
| migration fails | old release recovered, database unchanged |
| health fails, nothing written | database restored, old release recovered |
| backup fails verification | refused before migrating |
| backup path unavailable | refused before anything is stopped |
| migrator from another release | refused before anything is stopped |
| writes during the migration window | impossible by construction, asserted |
| health fails after a write | **no automatic restore** |
| unusable database directory | refused before anything is stopped |
| migration rewrites rows, then health fails | rollback still allowed |
| unhealthy release will not stop | refused, nothing restored |

It also mutation-tests itself in the sense that matters: removing the
release-identity check or the write-detection branch turns rows red.

## Production qualification (2026-09-05) — FROZEN

Everything in "what this repository has not verified" below was true when this
line was written. It no longer is. `73b6cb7` was qualified on the production
VPS the same day it landed:

```
CI Run #23 / 9383226              PASS
CI Run #24 / 73b6cb7              PASS
real-Nix acceptance matrix        35/35 PASS
VPS preflight                     PASS
production rollback path          exercised successfully (see incident below)
production activation             PASS
real post-migration app write     PASS  (POST /language: survey_session 1->2,
                                          session_instrument 0->1, audit_event
                                          17->18 — the new table itself, not a
                                          synthetic probe)
restart persistence                PASS  (identical data fingerprint before/after)
legacy activation entrypoints      tombstoned
```

The first activation attempt **failed for real** — a genuine
`SQLite ErrorReadOnly` during migration, exit 12 — and the automatic recovery
ran on this production host, not in a test harness: backup restored, previous
release started, health confirmed. That is a stronger claim than the matrix
alone could make: the rollback path has now executed successfully against the
real database, once, under a real failure it did not expect.

Root cause of that failure and the two host gaps it and preflight surfaced,
neither of which the local matrix could ever catch because they are facts
about *this host*, not about the script:

- `/var/lib/relationship-fix` was `0700`, owned by `relationship-fix`. `deploy`
  had no access at all. Fixed by adding `deploy` to the `relationship-fix`
  group and setting the directory `0770`, the database file `0660`.
- Opening that directory to the group meant re-examining everything else in
  it: `client-session-key.aes` turned out to be `0644` at the file level,
  protected only by the directory being `0700`. Tightened to `0600` *before*
  loosening the directory, not after.
- `RF_LOCK_FILE`'s default, `/var/lock/relationship-fix-activate.lock`,
  resolves to `/run/lock` — root-owned, and tmpfs. `deploy` could not open it
  at all. Fixed with a pre-created, correctly-owned file *and* a
  `systemd-tmpfiles.d` rule, so the fix survives a reboot instead of being a
  manual `chown` someone has to remember to redo.

### Known incident: a procedure violation, not a design defect

While diagnosing the failure above, `annotation-web-migrate migrate` was run
directly against the live database while the previous release was still
serving — outside `activate.sh`, in violation of the stop-the-world contract
this whole document exists to enforce. Recorded plainly rather than quietly
fixed and forgotten:

```
annotation-web-migrate migrate invoked directly
  while the old service was running
  bypassing stop-the-world
integrity afterward:        ok
old-table fingerprint:      unchanged
new tables:                 empty (nothing had raced the write)
observed data damage:       none
```

Classification: **procedure violation / near miss, no observed data loss or
corruption** — not a defect in `activate.sh`, which was not in the loop for
this operation at all. The useful conclusion is operational, not
cryptographic: `annotation-web-migrate` is a mechanism, not a production
entrypoint. Production migrations happen only through release-bound
`activate.sh`. No token or lock can stop a person with root from running the
binary directly; the boundary that matters is "don't," documented here, not a
technical one that root can trivially route around anyway.

### Known limitations (not backlog)

Stated as accepted boundaries of this MVP, not as work still to schedule:

- Backups stay on the same host and disk as the database they back up. A
  verified copy here protects against a bad migration; it does not protect
  against losing the disk.
- Backups are never pruned.
- A privileged human operator can always bypass the choreography; that is an
  administrative fact, not a gap in the tooling.
- One production qualification run is one data point, not a statistical
  sample over many deploys.

None of this weakens the actual guarantee: a schema-changing release either
activates behind a verified migration, or restores the previous database and
release before any post-activation write exists to lose; when it cannot prove
which of those is safe, it refuses rather than guesses (exit 15). Off-host
disaster recovery, backup retention, zero-downtime migration and HA/
distributed deployment are explicitly out of scope until real usage demands
otherwise.

## What this repository had *not* verified, before the above

Stated plainly, because the alternative is someone assuming otherwise. Kept
here rather than deleted — it is what "verified" is being compared against.

- **The first production run of this path was unproven.** Everything above was
  exercised against a fake host and against a real Nix release locally. None of
  it had run on the VPS. (Resolved — see "Production qualification" above.)
- **The previous `activate.sh` on the VPS was never in this repository.** It
  lived at `/opt/relationship-fix/bin/activate.sh`, owned by `deploy`, and its
  body was not recorded anywhere here — only its command-line and the
  `key=value` lines it printed. It has since been replaced by a tombstone (see
  "Retire the old entrypoint" below); the file that lived there is not
  recovered by anything and was never meant to be.
- **Sudo coverage was unknown.** The new script runs `sudo systemctl stop/start`
  and `sudo nix-env --profile … --set`. Both are now granted to `deploy` via a
  narrow, argument-fixed `sudoers.d` entry (the `nix-env` rule's only variable
  part is the store path, which `nix-env` itself validates).
- **Filesystem access was unknown.** Resolved as described in "Production
  qualification" above — `deploy` was added to the `relationship-fix` group
  rather than granted broader access, and `client-session-key.aes` was
  independently tightened in the same pass.

### Operational qualification, before the first real deploy

Run these on the host, as the user the deploy actually runs as. `test -w` on the
database file is **not** sufficient: SQLite creates and removes `-wal`, `-shm`
and `-journal` siblings next to it, and a restore replaces the file in place, so
the permission that matters is on the directory.

```bash
# 1. may deploy stop and start the unit?
sudo -n systemctl stop relationship-fix.service && sudo -n systemctl start relationship-fix.service

# 2. may deploy touch the database, its siblings and its directory?
sudo -u deploy bash -c '
  DB=/var/lib/relationship-fix/annotation.db
  DIR=$(dirname "$DB")
  test -r "$DB"  || echo "FAIL: cannot read $DB"
  test -w "$DB"  || echo "FAIL: cannot write $DB"
  test -x "$DIR" || echo "FAIL: cannot traverse $DIR"
  test -w "$DIR" || echo "FAIL: cannot create -wal/-shm in $DIR, or replace the file on restore"
  : > "$DIR/.probe" && rm -f "$DIR/.probe" || echo "FAIL: $DIR rejects writes"
'

# 3. may deploy write backups?
sudo -u deploy bash -c '
  D=/var/lib/relationship-fix/backups
  mkdir -p "$D" && : > "$D/.probe" && rm -f "$D/.probe" || echo "FAIL: $D not usable"
'
```

The script performs the same checks itself in preflight and refuses with exit 10
before stopping anything, so the failure mode is a refused deploy rather than a
damaged one. Running them by hand first turns a refused deploy into a fixed
permission.

### Retire the old entrypoint during the same visit

`/opt/relationship-fix/bin/activate.sh` is now unused, which is not the same as
unreachable. A stale cron entry, an old runbook, a shell history line or a person
working from memory would call it, and all of the machinery above would sit in
the Nix store being no help at all.

Replace it with a tombstone that deploys nothing:

```bash
sudo mv /opt/relationship-fix/bin/activate.sh /opt/relationship-fix/bin/activate.sh.retired
sudo tee /opt/relationship-fix/bin/activate.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
echo "This entrypoint is retired. Activation ships inside the release:" >&2
echo "  <store-path>/bin/annotation-web-activate <store-path> [git-sha]" >&2
echo "See docs/runbooks/annotation-web-deploy.md." >&2
exit 64
EOF
sudo chmod 755 /opt/relationship-fix/bin/activate.sh
```

Deliberately a tombstone and not a proxy to the new script. Forwarding would
recreate exactly the production-owned indirection this change removed, and the
next person would have two activation paths to reason about instead of one.

## Configuration

All of these are defaulted for the production host and overridable:

| Variable | Default |
| --- | --- |
| `RF_PROFILE` | `/nix/var/nix/profiles/relationship-fix` |
| `RF_SERVICE` | `relationship-fix.service` |
| `RF_DB_PATH` | read from the unit's `Environment`, else `/var/lib/relationship-fix/annotation.db` |
| `RF_BACKUP_DIR` | `/var/lib/relationship-fix/backups` |
| `RF_HEALTH_URL` | `http://127.0.0.1:8080/` |
| `RF_LOCK_FILE` | `/var/lock/relationship-fix-activate.lock`, i.e. `/run/lock/…` — root-owned tmpfs by default; `deploy` needs a pre-created, correctly-owned file there (see "Production qualification" above) plus a `systemd-tmpfiles.d` rule so it survives a reboot |
| `RF_ACTIVATE_BACKEND` | `backends/systemd.sh` beside the script |

`RF_DB_PATH` is asked of the unit rather than duplicated, because a backup of a
different file than the application writes is worse than no backup: it looks
like one.

## Not in scope here

Backups are written and verified but never pruned, and nothing ships them off
the host. A verified copy on the same disk as the original protects against a
bad migration; it does not protect against losing the disk.

## Pilot surface: what a release must carry and what stays on the host

Simple pilot mode (2026-09-12; see the erratum at the top of
[the cutover contract](../pilot-v0.1-cutover-contract.md) for why): with
`RF_PILOT_ENABLED=1`, the server proves the one `issuable` package in the
registry at start — seal, manifest, every presentation file its manifest
names as a slot, the instruction document and the ontology file — and
refuses to start otherwise. No per-person issuance record, no bearer token:
identity is a slot (`annotator-1`, `annotator-2`, …), claimed first-come by
whichever browser session gets there first.

- **In the release** (`$RELEASE/share/relationship-fix`, installed by the
  flake's `postInstall`): `data/pilot/package-registry.json`,
  `data/pilot/v0.1/CHECKSUMS.sha256`, `data/pilot/v0.1/presentation/*.jsonl`,
  `docs/pilot-v0.1-instructions.md`, `data/ontology/behavior-v0.1.json`.
  Never `items.jsonl` or `presentation-map/`: the server must not hold
  canonical ids.
- **Nothing host-state is needed for issuance any more.** There is no
  `RF_ISSUANCE_DIR`, no eligibility record, no per-person file to copy
  anywhere. The registry itself (not sealed, restart-effective) carries
  `instructions_file` and `instructions_sha256` for the package, since the
  sealed manifest's own `instructions` field is a frozen erratum pointing at
  the v0 document (`dialogue-naturalness-gate.md` §3) and the manifest
  cannot be edited without breaking the seal.

## Issuing people (J), simple pilot mode

The whole "issuance" step is now: send the same one link to both people.

```text
deploy with RF_PILOT_ENABLED=1
        │
the server proves the sealed package at start (or refuses to start)
        │
first person opens https://<host>/, presses "Начать" → claims annotator-1
second person opens the same link, presses "Начать" → claims annotator-2
        │
each annotates 40 items, resumable from the same browser at any time
        │
annotation-web-export annotator-1|annotator-2 (offline; refuses until complete)
```

Unit environment, in addition to `RF_DB_PATH`:

```text
RF_REPO_ROOT=/nix/var/nix/profiles/relationship-fix/share/relationship-fix
RF_PILOT_ENABLED=1
RF_DOGFOOD_ENABLED=0
RF_SECURE_COOKIES=1
```

The health check hits `/`; with a pilot package loaded this renders the
claim landing page (200), so activation health is unchanged. A release whose
package does not prove exits before it listens, which the health check
reports as a failed activation (state B) and rolls back.

Collecting a completed session is offline and read-only, same as before:

```bash
RF_DB_PATH=/var/lib/relationship-fix/annotation.db \
RF_REPO_ROOT=/nix/var/nix/profiles/relationship-fix/share/relationship-fix \
  $RELEASE/bin/annotation-web-export annotation-pilot-v0.1 annotator-1 /var/lib/relationship-fix/exports
```

The export refuses an incomplete session and names the items.

## J safety invariants, simple pilot mode

| # | Invariant | Enforced by | Test |
|---|---|---|---|
| 1 | `GET /` (unclaimed) → 200, no `PilotBinding` row, still claimable | `getHomeR` only ever reads a session cookie / `get sid`; the unclaimed branch renders a landing page and touches the database not at all — protects against messenger link-preview prefetch, which fetches a shared URL unclicked the moment it is pasted into a chat | `PilotSpec.hs`: "a fresh visitor gets a landing page and claims nothing until the button is pressed", "opening it any number of times before claiming is still harmless" |
| 2 | `POST /` claims exactly one slot; a second claim (concurrent or sequential) cannot create another for the same slot | `claimNextSlot` uses `insertUnique` on `PilotBinding.annotator_id`, not a check-then-blind-insert: a losing insert returns `Nothing` instead of throwing, and the loser moves on to the next slot rather than crashing | `PilotSpec.hs`: "only the POST claims a slot; resuming afterwards never opens a second session" (sequential), "a slot claimed elsewhere between the check and the insert resumes there, not a crash" (manufactures the exact DB conflict a real race would produce — deterministic, not a thread-timing gamble) |
| 3 | Both slots taken → plain refusal page, no crash, no third slot invented | `claimNextSlot []` renders a fixed "both taken" page | `PilotSpec.hs`: "both slots taken: a third visitor sees a plain refusal, no crash" |
| 4 | No per-request path (there is no token in it any more) is logged in cleartext | `app/Main.hs` builds the WAI app via `toWaiAppPlain` + `defaultMiddlewaresNoLogging`, not `toWaiApp` (whose built-in middleware logs the full request path to stdout/journal) | CI step "Enforce no-request-logging-middleware invariant" (greps `app/Main.hs` for a reintroduced bare `toWaiApp`) |
| 5 | Which slot maps to which real person is the facilitator's own record, not the system's | Procedure, not code: the facilitator notes which pseudonym pressed "Начать" first (e.g. by asking, or by being the one who sends the link and watches for the claim), same spirit as `contamination-ledger.json`'s pseudonym bookkeeping | Not unit-testable; this is a deliberate, accepted reduction from the earlier cryptographically-issued-per-person model — see the cutover contract erratum |

## Controlled pilot mode (historical, dormant — not the current deploy path)

Everything below this line describes the bearer-token issuance system
deployed 2026-09-09 through 2026-09-12 (commits `b8b17f1`, `367af14`) and
retired in favour of simple pilot mode above, once review concluded a
2-person pilot of people the facilitator invited directly did not need
per-person cryptographic issuance, external eligibility records or a
revoke/reissue procedure — the corresponding UX and operational cost were
disproportionate to what those bought. The code (`research/python/metrics/
issuance.py`, the `rf.issuance-record.v1` / `rf.annotator-eligibility.v1`
schemas) is untouched in git history and this documentation is kept, not
deleted, for the day a pilot actually needs it: paid external annotators,
blind assignment across more than a couple of people, or a real requirement
to prove which specific person produced which dataset.

Eligibility was host/private state, never the sealed package:
`data/pilot/v0.1/eligibility.json` is the null template sealed with the
package and is never edited (editing it breaks the seal, and issuance
refuses a broken seal). The operational record per person was
`rf.annotator-eligibility.v1`, kept at a private path:

```json
{
  "schema_version": "rf.annotator-eligibility.v1",
  "package_id": "annotation-pilot-v0.1",
  "annotator_id": "annotator-1",
  "criteria": {
    "did_not_author_ontology": true,
    "fluent_ru": true,
    "fluent_en": true,
    "has_not_seen_items": true
  },
  "established_at": "2026-09-09T10:00:00Z",
  "established_by": "facilitator"
}
```

Production flow once deployed and healthy (`/` said "no open study"; people
entered only through `/t/<token>`):

```text
establish eligibility for annotator-N  →  eligibility/annotator-N.json (private)
        │
metrics.issuance new                   →  issuance/annotator-N.json + the personal link, printed once
        │
copy the record to RF_ISSUANCE_DIR on the host, restart relationship-fix.service
        │
the server proves every record at start (or refuses to start)
        │
the person opens https://<host>/t/<token> and annotates 40 items
        │
annotation-web-export (offline; refuses until complete)
```

```bash
RF_PUBLIC_BASE_URL=https://relationship-fix.192-248-184-141.sslip.io \
uv run python -m metrics.issuance new --root ../.. \
  --package annotation-pilot-v0.1 --annotator annotator-1 \
  --eligibility /secure/eligibility/annotator-1.json \
  --instructions docs/pilot-v0.1-instructions.md \
  --out /secure/issuance/annotator-1.json
```

The command proved the sealed package and the eligibility record, wrote the
issuance record with only the token's sha256, and printed the personal link
exactly once. Then:

```bash
scp /secure/issuance/annotator-1.json host:/var/lib/relationship-fix/issuance/
ssh host sudo systemctl restart relationship-fix.service
ssh host journalctl -u relationship-fix -n 5   # "N issuance binding(s) proven"
```

Old J safety invariants table, for the record — the token-claim race,
the request-logging leak, and the revoke procedure it protected against are
moot without a token, but the underlying lessons (claim on POST only, don't
let a middleware default log a secret, keep a paper trail instead of
deleting) are exactly what invariants 1, 2 and 4 above still are:

| # | Invariant | Enforced by | Test |
|---|---|---|---|
| 1 | `GET /t/<valid-token>` (unclaimed) → 200, no `PilotBinding` row, token still claimable | `getTokenR` only ever read (`getBy`); the unclaimed branch rendered a landing page and touched the database not at all | (removed with the token system) |
| 2 | `GET /t/<revoked-or-unknown-token>` → 404, no mutation | `Map.lookup` against `appBindings`, loaded once at start from `RF_ISSUANCE_DIR` | (removed with the token system) |
| 3 | `POST` claim on an unclaimed token → exactly one `PilotBinding`; a second claim could not create another | `claimUnclaimed` used `insertUnique` on `PilotBinding.token_sha256` | (removed with the token system) |
| 4 | The raw token never appeared in application or proxy logs | `app/Main.hs`'s `toWaiAppPlain` + `defaultMiddlewaresNoLogging` (this part is unchanged and still true) | CI step "Enforce no-request-logging-middleware invariant" |
| 5 | A revoked issuance record was retained as audit evidence, not deleted | Procedure: moved to `RF_ISSUANCE_DIR/revoked/<name>.revoked-<timestamp>.json` with a reason | (removed with the token system) |
