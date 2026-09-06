#!/usr/bin/env bash
# The deployment acceptance matrix.
#
# Every row here is a way a schema-changing deploy can go wrong, and the point
# of the exercise is that the failing rows are the interesting ones. A pipeline
# that has only ever been watched succeeding is a pipeline whose rollback path
# has never run.
#
# Nothing here needs systemd, sudo, a VPS or the network. It needs the two real
# binaries, a temporary directory, and a port. activate.sh runs unmodified; only
# its host adapter is swapped, so the choreography exercised is the one that
# ships.
#
# usage: matrix.sh <directory containing annotation-web and annotation-web-migrate>

set -uo pipefail

BIN_DIR=${1:-}
[[ -n $BIN_DIR && -x $BIN_DIR/annotation-web && -x $BIN_DIR/annotation-web-migrate ]] || {
  echo "usage: matrix.sh <bin-dir with annotation-web and annotation-web-migrate>" >&2
  exit 64
}
BIN_DIR=$(cd -- "$BIN_DIR" && pwd -P)

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
ACTIVATE="$REPO_ROOT/deploy/activate.sh"
FAKE_BACKEND="$REPO_ROOT/deploy/backends/fake.sh"
FIXTURE="$REPO_ROOT/src/annotation-web/test/fixtures/hs-v1-legacy.sql"

command -v sqlite3 >/dev/null 2>&1 || {
  echo "matrix.sh needs the sqlite3 CLI to act as a respondent; activate.sh does not" >&2
  exit 64
}

WORK=$(mktemp -d -t rf-deploy-matrix-XXXXXX)
PORT=${RF_MATRIX_PORT:-8477}
trap 'rm -rf "$WORK"' EXIT

pass=0
fail=0

ok()   { printf '  OK   %s\n' "$1"; pass=$(( pass + 1 )); }
bad()  { printf '  FAIL %s\n     %s\n' "$1" "$2"; fail=$(( fail + 1 )); }

check() {
  local name=$1 condition=$2 detail=${3:-}
  if [[ $condition == 1 ]]; then ok "$name"; else bad "$name" "$detail"; fi
}

# --- building the pieces a scenario is made of ------------------------------

# A release is a directory shaped like the Nix output: bin/annotation-web and
# bin/annotation-web-migrate. Real by default; individual binaries can be
# replaced by stubs to inject a specific failure.
make_release() {
  local name=$1
  local dir="$WORK/releases/$name"
  mkdir -p "$dir/bin"
  local binary
  for binary in annotation-web annotation-web-migrate; do
    # Hard link, not symlink. activate.sh resolves both binaries and refuses a
    # release whose contents live somewhere else, which is the whole point of
    # the release-identity check; a symlink farm would trip it for the wrong
    # reason and a real Nix store path never looks like one.
    ln "$BIN_DIR/$binary" "$dir/bin/$binary" 2>/dev/null \
      || cp "$BIN_DIR/$binary" "$dir/bin/$binary"
  done
  printf '%s\n' "$dir"
}

# Damage a database the way a truncated or half-written copy is damaged: keep
# page 1, so it is still recognisably a SQLite file with a readable schema, and
# destroy the pages holding rows. Scribbling on a small file at random is not
# enough -- SQLite has no per-page checksums, and bytes landing in free space
# are cheerfully ignored, which is itself worth knowing before trusting a
# corruption test.
damage_database() {
  local target=$1 size
  size=$(stat -c %s "$target")
  dd if=/dev/urandom of="$target" bs=1 seek=4096 count=$(( size - 4096 )) \
    conv=notrunc status=none
}

# A host is a fake machine: profile symlink, pid file, database.
make_host() {
  local name=$1
  local root="$WORK/hosts/$name"
  mkdir -p "$root/backups"
  printf '%s\n' "$root"
}

# The legacy hs-v1 database, exactly as the previous release left it.
#
# sqlite3 is a requirement of this harness and deliberately not of activate.sh:
# the production script asks the release's own migrator every question it has
# about a database, so the VPS needs no sqlite tooling at all. The harness, on
# the other hand, has to be able to act like a respondent.
seed_legacy_db() {
  sqlite3 "$1" < "$FIXTURE"
}

# Run activate.sh against a fake host and capture its report.
run_activate() {
  local root=$1 release=$2
  shift 2
  env \
    RF_FAKE_ROOT="$root" \
    RF_FAKE_PORT="$PORT" \
    RF_ACTIVATE_BACKEND="$FAKE_BACKEND" \
    RF_DB_PATH="$root/annotation.db" \
    RF_BACKUP_DIR="$root/backups" \
    RF_HEALTH_URL="http://127.0.0.1:$PORT/" \
    RF_HEALTH_ATTEMPTS="${RF_MATRIX_HEALTH_ATTEMPTS:-8}" \
    RF_HEALTH_INTERVAL=0.5 \
    RF_STOP_ATTEMPTS=10 \
    RF_LOCK_FILE="$root/activate.lock" \
    "$@" \
    "$ACTIVATE" "$release" test-sha \
    >"$root/report.txt" 2>"$root/activate.log"
  echo $?
}

report_value() {
  local root=$1 key=$2
  sed -n "s/^$key=//p" "$root/report.txt" | tail -1
}

cleanup_host() {
  local root=$1
  RF_FAKE_ROOT="$root" bash -c ". $FAKE_BACKEND; backend_service_stop" 2>/dev/null || true
}

digest_of() {
  RF_DB_PATH="$1" "$BIN_DIR/annotation-web-migrate" data-fingerprint 2>/dev/null
}

# "Nothing was lost" is not "the digest is identical": a migration legitimately
# adds empty tables, and those show up as new entries. The property worth
# asserting is that every table that existed before still holds exactly what it
# held.
digest_preserved() {
  local before=$1 after=$2 entry
  for entry in $before; do
    case " $after " in
      *" $entry "*) ;;
      *) return 1 ;;
    esac
  done
  return 0
}

echo "deployment acceptance matrix"
echo

# ---------------------------------------------------------------------------
# 1. old schema + new binary without migrate -> REFUSE
#    Not a property of the deploy script at all: it is the application's own
#    refusal, checked here because the pipeline depends on it being true.
# ---------------------------------------------------------------------------
scenario_refuses_unmigrated() {
  local root; root=$(make_host unmigrated)
  seed_legacy_db "$root/annotation.db"
  local release; release=$(make_release current)
  RF_DB_PATH="$root/annotation.db" \
  RF_SESSION_KEY_PATH="$root/key.aes" \
  PORT="$PORT" \
    timeout 10 "$release/bin/annotation-web" >"$root/server.log" 2>&1
  local status=$?
  local refused=0
  [[ $status -ne 0 ]] && grep -q "annotation-web-migrate first" "$root/server.log" && refused=1
  check "old schema + new binary without migrate -> REFUSE" "$refused" \
    "exit $status, log: $(head -1 "$root/server.log")"
}

# ---------------------------------------------------------------------------
# 2. migration success + health success -> DEPLOY
# ---------------------------------------------------------------------------
scenario_happy_path() {
  local root; root=$(make_host happy)
  seed_legacy_db "$root/annotation.db"
  local before; before=$(digest_of "$root/annotation.db")
  local release; release=$(make_release good)
  local status; status=$(run_activate "$root" "$release")
  cleanup_host "$root"
  local after; after=$(digest_of "$root/annotation.db")

  check "migration success + health success -> DEPLOY" \
    "$([[ $status -eq 0 && $(report_value "$root" outcome) == activated ]] && echo 1 || echo 0)" \
    "exit $status, outcome $(report_value "$root" outcome), log: $(tail -3 "$root/activate.log" | tr '\n' ' ')"
  check "  and every historical row survived the migration" \
    "$(digest_preserved "$before" "$after" && echo 1 || echo 0)" "before=$before after=$after"
  check "  and a verified backup was kept" \
    "$([[ $(report_value "$root" backup_verified) == yes && -f $(report_value "$root" backup_path) ]] && echo 1 || echo 0)" \
    "backup_path=$(report_value "$root" backup_path)"
  check "  and release identity was checked, not assumed" \
    "$([[ $(report_value "$root" release_identity) == verified ]] && echo 1 || echo 0)" ""
}

# ---------------------------------------------------------------------------
# 3. migration failure -> OLD APP RECOVERED
# ---------------------------------------------------------------------------
scenario_migration_failure() {
  local root; root=$(make_host migfail)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-migfail)
  # The previous release is one that can serve this database, so bring the host
  # to a working state first, the way a real host already is. The baseline for
  # "nothing changed" is taken after that, since that deploy is the setup and
  # not the thing under test.
  run_activate "$root" "$previous" >/dev/null
  cleanup_host "$root"
  local before; before=$(digest_of "$root/annotation.db")

  local broken; broken=$(make_release broken-migrator)
  rm "$broken/bin/annotation-web-migrate"
  cat > "$broken/bin/annotation-web-migrate" <<STUB
#!/usr/bin/env bash
# Answers the read-only questions honestly, then fails the one that writes.
case "\${1:-migrate}" in
  migrate) echo "stub: migration exploded" >&2; exit 1 ;;
  *) exec "$BIN_DIR/annotation-web-migrate" "\$@" ;;
esac
STUB
  chmod +x "$broken/bin/annotation-web-migrate"

  local status; status=$(run_activate "$root" "$broken")
  local recovered=0
  curl -sf --max-time 5 "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && recovered=1
  cleanup_host "$root"
  local after; after=$(digest_of "$root/annotation.db")

  check "migration failure -> OLD APP RECOVERED" \
    "$([[ $status -eq 12 && $recovered -eq 1 ]] && echo 1 || echo 0)" \
    "exit $status (want 12), old app serving: $recovered"
  check "  and the database holds exactly what it held" \
    "$([[ $before == "$after" ]] && echo 1 || echo 0)" "before=$before after=$after"
  check "  and the report says it rolled back" \
    "$([[ $(report_value "$root" rollback_performed) == true ]] && echo 1 || echo 0)" \
    "rollback_performed=$(report_value "$root" rollback_performed)"
}

# ---------------------------------------------------------------------------
# 4. migration success + health failure -> DB RESTORED + OLD APP RECOVERED
# ---------------------------------------------------------------------------
scenario_health_failure() {
  local root; root=$(make_host healthfail)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-healthfail)
  run_activate "$root" "$previous" >/dev/null
  cleanup_host "$root"
  local before; before=$(digest_of "$root/annotation.db")

  local sick; sick=$(make_release sick-server)
  rm "$sick/bin/annotation-web"
  cat > "$sick/bin/annotation-web" <<'STUB'
#!/usr/bin/env bash
# Starts, stays up, never answers. The worst kind of unhealthy: a process that
# looks alive to a supervisor and is useless to a respondent.
while true; do sleep 1; done
STUB
  chmod +x "$sick/bin/annotation-web"

  local status; status=$(run_activate "$root" "$sick")
  local recovered=0
  curl -sf --max-time 5 "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && recovered=1
  cleanup_host "$root"
  local after; after=$(digest_of "$root/annotation.db")

  check "migration success + health failure -> DB RESTORED + OLD APP RECOVERED" \
    "$([[ $status -eq 13 && $recovered -eq 1 ]] && echo 1 || echo 0)" \
    "exit $status (want 13), old app serving: $recovered"
  check "  and the database went back to its pre-migration content" \
    "$([[ $before == "$after" ]] && echo 1 || echo 0)" "before=$before after=$after"
  check "  and the restore was recorded as safe because nothing had been written" \
    "$([[ $(report_value "$root" post_activation_writes) == none && $(report_value "$root" db_restored) == true ]] && echo 1 || echo 0)" \
    "writes=$(report_value "$root" post_activation_writes) restored=$(report_value "$root" db_restored)"
}

# ---------------------------------------------------------------------------
# 5. corrupted / invalid backup -> DEPLOY REFUSED BEFORE MIGRATION
#
#    Two halves, because one without the other proves nothing. First: the
#    verifier actually rejects a damaged file, so "the backup verified" is not a
#    rubber stamp. Second: a database that fails verification stops the deploy
#    before it migrates or backs anything up -- which is the ordering that
#    matters, since a corrupt source can only ever produce a corrupt backup.
# ---------------------------------------------------------------------------
scenario_backup_verifier_is_real() {
  local dir="$WORK/verifier"; mkdir -p "$dir"
  seed_legacy_db "$dir/sound.db"
  local sound=0
  RF_DB_PATH="$dir/sound.db" "$BIN_DIR/annotation-web-migrate" integrity >/dev/null 2>&1 && sound=1
  check "the backup verifier accepts a sound database" "$sound" ""

  cp "$dir/sound.db" "$dir/damaged.db"
  damage_database "$dir/damaged.db"
  local rejected=0
  RF_DB_PATH="$dir/damaged.db" "$BIN_DIR/annotation-web-migrate" integrity >/dev/null 2>&1 || rejected=1
  check "the backup verifier rejects a damaged one" "$rejected" \
    "a verifier that accepts anything makes every backup check meaningless"
}

scenario_damaged_database_refused() {
  local root; root=$(make_host damaged)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-damaged)
  run_activate "$root" "$previous" >/dev/null
  cleanup_host "$root"
  # That setup deploy took a backup of its own, legitimately. What matters is
  # that the refused one adds none.
  local backups_before; backups_before=$(find "$root/backups" -name '*.db' | wc -l)

  damage_database "$root/annotation.db"

  local release; release=$(make_release good-damaged)
  local status; status=$(run_activate "$root" "$release")
  cleanup_host "$root"

  local backups_after; backups_after=$(find "$root/backups" -name '*.db' | wc -l)

  check "a database that fails verification -> REFUSED BEFORE MIGRATION" \
    "$([[ $status -eq 11 ]] && echo 1 || echo 0)" \
    "exit $status (want 11), log: $(tail -1 "$root/activate.log")"
  check "  and it never reached the migration" \
    "$([[ -z $(report_value "$root" migration) ]] && echo 1 || echo 0)" \
    "migration=$(report_value "$root" migration)"
  check "  and it kept no backup of the damage" \
    "$([[ $backups_after -eq $backups_before ]] && echo 1 || echo 0)" \
    "backups went from $backups_before to $backups_after"
}

# ---------------------------------------------------------------------------
# 6. backup path unavailable -> DEPLOY REFUSED
# ---------------------------------------------------------------------------
scenario_backup_unavailable() {
  local root; root=$(make_host nobackup)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-nobackup)
  run_activate "$root" "$previous" >/dev/null
  local before; before=$(digest_of "$root/annotation.db")

  local release; release=$(make_release good-nobackup)
  # A backup directory that cannot be created. Deliberately not "chmod 500":
  # this harness may run as root in a container, and root walks straight through
  # permission bits, so a test built on them would quietly pass by doing
  # nothing. A path whose parent is a regular file cannot be created by anyone.
  touch "$root/not-a-directory"
  local status
  status=$(env RF_FAKE_ROOT="$root" RF_FAKE_PORT="$PORT" RF_ACTIVATE_BACKEND="$FAKE_BACKEND" \
    RF_DB_PATH="$root/annotation.db" RF_BACKUP_DIR="$root/not-a-directory/backups" \
    RF_HEALTH_URL="http://127.0.0.1:$PORT/" RF_HEALTH_ATTEMPTS=4 RF_HEALTH_INTERVAL=0.5 \
    RF_LOCK_FILE="$root/activate.lock" \
    "$ACTIVATE" "$release" test-sha >"$root/report.txt" 2>"$root/activate.log"; echo $?)
  local still_serving=0
  curl -sf --max-time 5 "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && still_serving=1
  cleanup_host "$root"
  local after; after=$(digest_of "$root/annotation.db")

  check "backup path unavailable -> DEPLOY REFUSED" \
    "$([[ $status -eq 10 ]] && echo 1 || echo 0)" \
    "exit $status (want 10), log: $(tail -1 "$root/activate.log")"
  check "  and it refused before stopping the running service" \
    "$still_serving" "the previous release should never have been touched"
  check "  and nothing was migrated" \
    "$([[ $before == "$after" ]] && echo 1 || echo 0)" "before=$before after=$after"
}

# ---------------------------------------------------------------------------
# 7. migrate binary from the wrong revision -> REFUSED
# ---------------------------------------------------------------------------
scenario_wrong_revision_migrator() {
  local root; root=$(make_host mixedrelease)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-mixed)
  run_activate "$root" "$previous" >/dev/null

  local other; other=$(make_release someone-elses-release)
  local release; release=$(make_release mixed)
  # The shape this row is about: an application from one release and a migrator
  # from another, which is how you end up with migration v17, application v18
  # and a database nobody can account for.
  ln -sf "$other/bin/annotation-web-migrate" "$release/bin/annotation-web-migrate"

  local status; status=$(run_activate "$root" "$release")
  local still_serving=0
  curl -sf --max-time 5 "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && still_serving=1
  cleanup_host "$root"

  check "migrator from another release -> REFUSED" \
    "$([[ $status -eq 10 ]] && echo 1 || echo 0)" \
    "exit $status (want 10), log: $(tail -1 "$root/activate.log")"
  check "  and it refused before stopping the running service" "$still_serving" ""
}

# ---------------------------------------------------------------------------
# 8. service writes during the migration window -> impossible by construction
#    Asserted, not asserted-about: the migrator itself checks whether the
#    application answers while it is running.
# ---------------------------------------------------------------------------
scenario_no_writes_during_migration() {
  local root; root=$(make_host quiesced)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-quiesced)
  run_activate "$root" "$previous" >/dev/null
  local serving_before=0
  curl -sf --max-time 5 "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && serving_before=1

  local watched; watched=$(make_release watched)
  rm "$watched/bin/annotation-web-migrate"
  cat > "$watched/bin/annotation-web-migrate" <<STUB
#!/usr/bin/env bash
# Refuses to migrate a database that anything is still able to serve.
if [ "\${1:-migrate}" = "migrate" ]; then
  if curl -sf --max-time 2 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    echo "a writer was still reachable when the migration started" >&2
    exit 1
  fi
fi
exec "$BIN_DIR/annotation-web-migrate" "\$@"
STUB
  chmod +x "$watched/bin/annotation-web-migrate"

  local status; status=$(run_activate "$root" "$watched")
  cleanup_host "$root"

  check "the service really was serving before the deploy started" "$serving_before" ""
  check "no writer is reachable while the migration runs" \
    "$([[ $status -eq 0 ]] && echo 1 || echo 0)" \
    "exit $status; migration ran with the app reachable: $(grep -c 'still reachable' "$root/activate.log" 2>/dev/null)"
}

# ---------------------------------------------------------------------------
# 9. post-activation failure after writes -> NO AUTOMATIC DB RESTORE
# ---------------------------------------------------------------------------
scenario_writes_then_unhealthy() {
  local root; root=$(make_host writesthenfail)
  seed_legacy_db "$root/annotation.db"
  local before; before=$(digest_of "$root/annotation.db")

  local previous; previous=$(make_release prev-writes)
  run_activate "$root" "$previous" >/dev/null
  cleanup_host "$root"

  # A release that writes a row the moment it starts and then never answers a
  # health check: a respondent's answer landing in the window between "the
  # application is reachable" and "the deploy decided it is unhealthy".
  local writer; writer=$(make_release writes-then-hangs)
  rm "$writer/bin/annotation-web"
  cat > "$writer/bin/annotation-web" <<STUB
#!/usr/bin/env bash
"$BIN_DIR/annotation-web-migrate" data-fingerprint >/dev/null 2>&1
"$WORK/insert-a-row" "\$RF_DB_PATH"
while true; do sleep 1; done
STUB
  chmod +x "$writer/bin/annotation-web"

  local status; status=$(run_activate "$root" "$writer")
  cleanup_host "$root"
  local after; after=$(digest_of "$root/annotation.db")

  check "post-activation failure after writes -> NO AUTOMATIC DB RESTORE" \
    "$([[ $status -eq 14 ]] && echo 1 || echo 0)" \
    "exit $status (want 14), log: $(tail -2 "$root/activate.log" | tr '\n' ' ')"
  check "  and it says why it refused" \
    "$([[ $(report_value "$root" post_activation_writes) == present && $(report_value "$root" db_restored) == refused ]] && echo 1 || echo 0)" \
    "writes=$(report_value "$root" post_activation_writes) restored=$(report_value "$root" db_restored)"
  check "  and the written row is still there" \
    "$([[ $before != "$after" ]] && echo 1 || echo 0)" \
    "the new row should have survived; before=$before after=$after"
}

# ---------------------------------------------------------------------------
# 9b. The database's *directory* is checked, not just the file.
#
#     SQLite creates and removes -wal, -shm and -journal siblings next to the
#     database, and a restore replaces the file in place. `test -w $DB` says
#     nothing about any of that, so a deploy that only checked the file would
#     get all the way to the restore before finding out it could not do one.
# ---------------------------------------------------------------------------
scenario_database_directory_checked() {
  local root; root=$(make_host dbdir)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-dbdir)
  run_activate "$root" "$previous" >/dev/null
  local before; before=$(digest_of "$root/annotation.db")

  local release; release=$(make_release good-dbdir)
  # A database whose directory cannot exist. Deliberately not a chmod: this may
  # run as root, and root walks through permission bits, so a test built on them
  # would pass by doing nothing.
  touch "$root/a-file-not-a-directory"
  local status
  status=$(env RF_FAKE_ROOT="$root" RF_FAKE_PORT="$PORT" RF_ACTIVATE_BACKEND="$FAKE_BACKEND" \
    RF_DB_PATH="$root/a-file-not-a-directory/annotation.db" RF_BACKUP_DIR="$root/backups" \
    RF_HEALTH_URL="http://127.0.0.1:$PORT/" RF_HEALTH_ATTEMPTS=4 RF_HEALTH_INTERVAL=0.5 \
    RF_LOCK_FILE="$root/activate.lock" \
    "$ACTIVATE" "$release" test-sha >"$root/report.txt" 2>"$root/activate.log"; echo $?)
  local still_serving=0
  curl -sf --max-time 5 "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && still_serving=1
  cleanup_host "$root"
  local after; after=$(digest_of "$root/annotation.db")

  check "an unusable database directory -> DEPLOY REFUSED" \
    "$([[ $status -eq 10 ]] && echo 1 || echo 0)" \
    "exit $status (want 10), log: $(tail -1 "$root/activate.log")"
  check "  and it refused before stopping the running service" "$still_serving" ""
  check "  and the real database was left alone" \
    "$([[ $before == "$after" ]] && echo 1 || echo 0)" "before=$before after=$after"
}

# ---------------------------------------------------------------------------
# 10. A migration that rewrites rows is not an application write.
#
#     This is about *when* the baseline digest is taken, which is the one thing
#     in the whole design that is a single edit away from being subtly wrong.
#     The baseline has to answer "has anything changed since the new
#     application became reachable", not "did the migration change anything".
#
#     Take it before the migration instead, and the first real data migration --
#     any UPDATE at all -- makes every rollback look like it would destroy data,
#     and a perfectly safe deploy refuses to roll back. That failure would show
#     up months from now, on the one night it matters.
# ---------------------------------------------------------------------------
scenario_data_migration_is_not_a_write() {
  local root; root=$(make_host datamigration)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-datamigration)
  run_activate "$root" "$previous" >/dev/null
  cleanup_host "$root"
  local before; before=$(digest_of "$root/annotation.db")

  # A release whose migration rewrites existing rows and whose server then
  # never answers: the rollback must still happen.
  local rel; rel=$(make_release rewrites-rows-then-hangs)
  rm "$rel/bin/annotation-web-migrate" "$rel/bin/annotation-web"
  cat > "$rel/bin/annotation-web-migrate" <<STUB
#!/usr/bin/env bash
if [ "\${1:-migrate}" = "migrate" ]; then
  "$BIN_DIR/annotation-web-migrate" migrate || exit 1
  sqlite3 "\$RF_DB_PATH" "UPDATE annotation SET abstention_note = 'rewritten by a data migration' WHERE decision = 'abstained';"
  exit 0
fi
exec "$BIN_DIR/annotation-web-migrate" "\$@"
STUB
  cat > "$rel/bin/annotation-web" <<'STUB'
#!/usr/bin/env bash
while true; do sleep 1; done
STUB
  chmod +x "$rel/bin/annotation-web-migrate" "$rel/bin/annotation-web"

  local status; status=$(run_activate "$root" "$rel")
  cleanup_host "$root"
  local after; after=$(digest_of "$root/annotation.db")

  check "a migration that rewrites rows still allows rollback" \
    "$([[ $status -eq 13 ]] && echo 1 || echo 0)" \
    "exit $status (want 13, not 14; 14 would mean the baseline digest was taken before the migration)"
  check "  and the migration's own rewrite is not counted as an application write" \
    "$([[ $(report_value "$root" post_activation_writes) == none ]] && echo 1 || echo 0)" \
    "post_activation_writes=$(report_value "$root" post_activation_writes)"
  check "  and the rollback undid the data migration too" \
    "$([[ $before == "$after" ]] && echo 1 || echo 0)" "before=$before after=$after"
}

# ---------------------------------------------------------------------------
# 11. No quiescence, no decision.
#
#     The digest is only evidence if nothing can write while it is taken. If the
#     unhealthy release will not stop, there is no evidence to be had, and the
#     honest move is to refuse rather than to read a database mid-write and
#     overwrite it based on what that said.
# ---------------------------------------------------------------------------
scenario_unstoppable_service() {
  local root; root=$(make_host unstoppable)
  seed_legacy_db "$root/annotation.db"

  local previous; previous=$(make_release prev-unstoppable)
  run_activate "$root" "$previous" >/dev/null
  cleanup_host "$root"
  local before; before=$(digest_of "$root/annotation.db")

  local sick; sick=$(make_release sick-and-unstoppable)
  rm "$sick/bin/annotation-web"
  cat > "$sick/bin/annotation-web" <<'STUB'
#!/usr/bin/env bash
while true; do sleep 1; done
STUB
  chmod +x "$sick/bin/annotation-web"

  # The stop only starts failing once the deploy has got as far as the health
  # check, so the earlier quiesce still succeeds and this exercises the branch
  # under test rather than the preflight one.
  local status
  status=$(run_activate "$root" "$sick" RF_FAKE_STOP_FAILS_AFTER_START=1)
  cleanup_host "$root"
  local after; after=$(digest_of "$root/annotation.db")

  check "an unhealthy release that will not stop -> REFUSED, nothing restored" \
    "$([[ $status -eq 15 ]] && echo 1 || echo 0)" \
    "exit $status (want 15), log: $(tail -1 "$root/activate.log")"
  check "  and it says the evidence could not be gathered" \
    "$([[ $(report_value "$root" post_activation_writes) == unknown ]] && echo 1 || echo 0)" \
    "post_activation_writes=$(report_value "$root" post_activation_writes)"
  check "  and it did not overwrite the database on a guess" \
    "$([[ $(report_value "$root" db_restored) == refused ]] && echo 1 || echo 0)" \
    "db_restored=$(report_value "$root" db_restored)"
}

# Stands in for a respondent answering a question in the window between "the
# new release is reachable" and "the deploy decided it is unhealthy".
cat > "$WORK/insert-a-row" <<'STUB'
#!/usr/bin/env bash
sqlite3 "$1" "INSERT INTO survey_session (presentation_language, started_at, completed_at) \
  VALUES ('ru', '2026-01-01T00:00:00Z', NULL);"
STUB
chmod +x "$WORK/insert-a-row"

scenario_refuses_unmigrated
scenario_happy_path
scenario_migration_failure
scenario_health_failure
scenario_backup_verifier_is_real
scenario_damaged_database_refused
scenario_backup_unavailable
scenario_wrong_revision_migrator
scenario_no_writes_during_migration
scenario_writes_then_unhealthy
scenario_database_directory_checked
scenario_data_migration_is_not_a_write
scenario_unstoppable_service

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
