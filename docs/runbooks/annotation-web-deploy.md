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

## What this repository has *not* verified

Stated plainly, because the alternative is someone assuming otherwise.

- **The first production run of this path is unproven.** Everything above was
  exercised against a fake host and against a real Nix release locally. None of
  it has run on the VPS.
- **The previous `activate.sh` on the VPS was never in this repository.** It
  lives at `/opt/relationship-fix/bin/activate.sh`, owned by `deploy`, and its
  body is not recorded anywhere here — only its command-line and the `key=value`
  lines it printed. This change replaces it with a script that ships in the
  closure. The old file is now unused; it is not removed by anything.
- **Sudo coverage is unknown.** The new script runs `sudo systemctl stop/start`
  and `sudo nix-env --profile … --set`. The old one certainly needed the last
  two; whether `deploy` may `stop` the unit has not been confirmed from here.
- **Filesystem access is unknown.** The script copies the database into
  `RF_BACKUP_DIR` and, on rollback, copies it back over the live file. That
  requires `deploy` to be able to read and write both `/var/lib/relationship-fix/`
  and the database file, which is normally owned by the service account.

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
| `RF_ACTIVATE_BACKEND` | `backends/systemd.sh` beside the script |

`RF_DB_PATH` is asked of the unit rather than duplicated, because a backup of a
different file than the application writes is worse than no backup: it looks
like one.

## Not in scope here

Backups are written and verified but never pruned, and nothing ships them off
the host. A verified copy on the same disk as the original protects against a
bad migration; it does not protect against losing the disk.
