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

The boundary between B and C is decided by evidence, not by a clock. Before the
service is started, the script records a digest of every row in every table.
After a failed health check it takes the digest again. Equal means the backup is
still a complete description of the world; different means it is not.

Comparing the file byte for byte would not work: merely opening a WAL database
rewrites parts of it, so the bytes change when nothing was stored.

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

Before the first real deploy, on the host:

```bash
sudo -n systemctl stop relationship-fix.service && sudo -n systemctl start relationship-fix.service
sudo -u deploy test -w /var/lib/relationship-fix/annotation.db && echo "db writable by deploy"
sudo -u deploy mkdir -p /var/lib/relationship-fix/backups && echo "backup dir writable by deploy"
```

If any of those fail, fix the ownership or the sudoers entry first. The script
fails closed — a backup directory it cannot write is exit 10 with nothing
touched — so the failure mode is a refused deploy rather than a damaged one, but
a refused deploy is still a deploy that did not happen.

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
