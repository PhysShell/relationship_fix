#!/usr/bin/env bash
# Activate a release of annotation-web, including its schema change.
#
# This is the deployment half of the migration contract. The application half
# says: the server never writes schema and refuses to start against a database
# it does not recognise. That is only safe if something else does write the
# schema, at a moment when nobody is reading or writing rows, with a verified
# way back. This script is that something else.
#
# The shape of it is stop-the-world on purpose. We are collecting relationship
# annotations from a handful of people, not clearing card payments, and an
# honest sixty-second outage that can be tested end to end beats a zero-downtime
# dual-schema choreography that cannot. Concretely:
#
#   quiesce -> verify -> backup -> verify backup -> migrate -> verify
#           -> activate -> health -> keep it, or go back
#
# Because writers are stopped before the backup is taken, "go back" can be the
# whole world: the database file and the release, together. That is a far better
# rollback unit than a reverse migration. Down migrations look symmetric right
# up until an up migration transformed or dropped something, at which point the
# symmetry quietly stops existing.
#
# The one thing this script will not do is undo a rollback decision on its own
# once respondents have written to the new schema. After activation the database
# contains answers the backup does not, so restoring the backup stops being a
# rollback and becomes data loss. That boundary is decided by evidence -- a
# digest of the stored rows, taken before the service is reachable and again
# afterwards -- and not by assuming how fast a health check runs.
#
# Never touches Caddy. The reverse proxy and its certificate are somebody else's
# state and outlive any release.

set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: activate.sh <store-path> [git-sha]

  store-path  the release to activate; must contain bin/annotation-web and
              bin/annotation-web-migrate, and both are used from inside it so a
              release can never be migrated by some other release's migrator
  git-sha     optional, recorded in the report for provenance only

Configuration, all overridable, all defaulted for the production host:
  RF_PROFILE            nix profile to switch          (/nix/var/nix/profiles/relationship-fix)
  RF_SERVICE            systemd unit                   (relationship-fix.service)
  RF_DB_PATH            database file                  (asked of the backend)
  RF_BACKUP_DIR         where verified backups go      (/var/lib/relationship-fix/backups)
  RF_HEALTH_URL         local health endpoint          (http://127.0.0.1:8080/)
  RF_HEALTH_ATTEMPTS    health polls before giving up  (20)
  RF_HEALTH_INTERVAL    seconds between polls          (1)
  RF_STOP_ATTEMPTS      stop polls before refusing     (30)
  RF_LOCK_FILE          activation lock                (/var/lock/relationship-fix-activate.lock)
  RF_ACTIVATE_BACKEND   host adapter to source         (backends/systemd.sh next to this script)

Exit codes carry the outcome, because "it failed" is not an operational answer:
   0  activated and healthy
  10  refused during preflight; nothing was stopped, copied or changed
  11  refused before migrating; the previous release is running again
  12  migration failed; database restored, previous release running again
  13  new release unhealthy; database restored, previous release running again
  14  new release unhealthy AND rows were written to it; NO automatic restore,
      an operator has to decide -- see the report
  15  the recovery path itself failed; the service is down, operator required
USAGE
}

# ---------------------------------------------------------------------------
# Reporting. Every line the workflow parses is emitted through here, so the
# report is complete whichever branch we leave by.
# ---------------------------------------------------------------------------

declare -a REPORT_KEYS=()
declare -A REPORT=()

record() {
  local key=$1 value=$2
  if [[ -z ${REPORT[$key]+set} ]]; then REPORT_KEYS+=("$key"); fi
  REPORT[$key]=$value
}

emit_report() {
  local key
  for key in "${REPORT_KEYS[@]}"; do
    printf '%s=%s\n' "$key" "${REPORT[$key]}"
  done
}

log() { printf '[activate] %s\n' "$*" >&2; }
die() { local code=$1; shift; log "$*"; record outcome "$(outcome_for "$code")"; emit_report; exit "$code"; }

outcome_for() {
  case $1 in
    0) echo activated ;;
    10) echo refused_preflight ;;
    11) echo refused_before_migration ;;
    12) echo migration_failed_restored ;;
    13) echo unhealthy_restored ;;
    14) echo unhealthy_writes_present_operator_required ;;
    15) echo recovery_failed_operator_required ;;
    *) echo failed ;;
  esac
}

# ---------------------------------------------------------------------------
# Configuration and the host adapter.
# ---------------------------------------------------------------------------

# Resolve through a symlink: the release installs this at
# libexec/annotation-web/activate.sh and links bin/annotation-web-activate to
# it, and the host adapter has to be found relative to the real file rather than
# relative to whichever name it was invoked by.
here=$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)

NEW_RELEASE=${1:-}
GIT_SHA=${2:-}
[[ -n $NEW_RELEASE ]] || { usage; exit 64; }
[[ $NEW_RELEASE == "-h" || $NEW_RELEASE == "--help" ]] && { usage; exit 0; }

RF_PROFILE=${RF_PROFILE:-/nix/var/nix/profiles/relationship-fix}
RF_SERVICE=${RF_SERVICE:-relationship-fix.service}
RF_BACKUP_DIR=${RF_BACKUP_DIR:-/var/lib/relationship-fix/backups}
RF_HEALTH_URL=${RF_HEALTH_URL:-http://127.0.0.1:8080/}
RF_HEALTH_ATTEMPTS=${RF_HEALTH_ATTEMPTS:-20}
RF_HEALTH_INTERVAL=${RF_HEALTH_INTERVAL:-1}
RF_STOP_ATTEMPTS=${RF_STOP_ATTEMPTS:-30}
RF_LOCK_FILE=${RF_LOCK_FILE:-/var/lock/relationship-fix-activate.lock}
RF_ACTIVATE_BACKEND=${RF_ACTIVATE_BACKEND:-$here/backends/systemd.sh}

[[ -r $RF_ACTIVATE_BACKEND ]] || { log "no host adapter at $RF_ACTIVATE_BACKEND"; exit 10; }
# shellcheck source=backends/systemd.sh
. "$RF_ACTIVATE_BACKEND"

# ---------------------------------------------------------------------------
# Serialisation. A manual run racing a workflow run is how one deploy's failure
# reverts a different deploy's success.
# ---------------------------------------------------------------------------

if [[ ${RF_ACTIVATE_LOCKED:-} != 1 ]]; then
  mkdir -p -- "$(dirname -- "$RF_LOCK_FILE")" 2>/dev/null || true
  exec env RF_ACTIVATE_LOCKED=1 flock --nonblock "$RF_LOCK_FILE" "$0" "$@" || {
    log "another activation holds $RF_LOCK_FILE"
    exit 10
  }
fi

# ---------------------------------------------------------------------------
# Small helpers over the release's own binaries. Note that every one of these
# runs the migrator from inside the release being activated, never from PATH:
# a release migrates itself or nothing does.
# ---------------------------------------------------------------------------

# stdout belongs to the report and nothing else, so whatever the migrator has to
# say goes to the log stream with everything else. A caller parsing key=value
# lines should not have to know what a migration narrates.
migrator() { RF_DB_PATH="$DB" "$NEW_RELEASE/bin/annotation-web-migrate" "$@" >&2; }

db_exists() { [[ -f $DB ]]; }

# The stored rows, as opposed to the shape holding them. Comparing files byte
# for byte cannot answer "did anyone write anything": opening a WAL database
# rewrites parts of it when nothing was stored.
data_digest() {
  local target=$1
  RF_DB_PATH="$target" "$NEW_RELEASE/bin/annotation-web-migrate" data-fingerprint 2>/dev/null || echo "UNREADABLE"
}

sound_database() {
  local target=$1
  RF_DB_PATH="$target" "$NEW_RELEASE/bin/annotation-web-migrate" integrity >/dev/null 2>&1
}

healthy() {
  local attempt=0
  while (( attempt < RF_HEALTH_ATTEMPTS )); do
    if curl -sf --max-time 5 "$RF_HEALTH_URL" >/dev/null 2>&1; then return 0; fi
    attempt=$(( attempt + 1 ))
    sleep "$RF_HEALTH_INTERVAL"
  done
  return 1
}

stop_and_confirm() {
  backend_service_stop || true
  local attempt=0
  while (( attempt < RF_STOP_ATTEMPTS )); do
    if ! backend_service_running; then return 0; fi
    attempt=$(( attempt + 1 ))
    sleep 1
  done
  return 1
}

# Copy the database as a unit. After a clean stop SQLite has normally folded the
# WAL back into the main file, but a service that died did not, so all three
# files travel together or the copy is not the database.
copy_database() {
  local from=$1 to=$2 suffix
  cp -- "$from" "$to" || return 1
  for suffix in -wal -shm; do
    if [[ -f ${from}${suffix} ]]; then
      cp -- "${from}${suffix}" "${to}${suffix}" || return 1
    else
      rm -f -- "${to}${suffix}" || return 1
    fi
  done
  return 0
}

# ---------------------------------------------------------------------------
# Recovery. Used by several failure branches, so it reports rather than exits
# and lets the caller pick the code.
# ---------------------------------------------------------------------------

restore_database() {
  [[ -n ${BACKUP:-} && -f ${BACKUP:-} ]] || return 1
  copy_database "$BACKUP" "$DB"
  sound_database "$DB"
}

start_previous_release() {
  [[ -n ${PREVIOUS:-} ]] || return 1
  backend_profile_set "$PREVIOUS" || return 1
  backend_service_start || return 1
  healthy
}

# ---------------------------------------------------------------------------
# 0. Preflight. Nothing has been stopped, copied or changed yet, so everything
#    that can be refused cheaply is refused here.
# ---------------------------------------------------------------------------

record requested_store_path "$NEW_RELEASE"
record git_sha "${GIT_SHA:-unknown}"

[[ -d $NEW_RELEASE ]] || die 10 "no release at $NEW_RELEASE"

for binary in annotation-web annotation-web-migrate; do
  [[ -x $NEW_RELEASE/bin/$binary ]] || die 10 "release is missing bin/$binary; a release that cannot migrate itself is not deployable"
done

# Release identity, checked rather than assumed. Both binaries must resolve to
# somewhere inside the release being activated. This is what stops the "migrator
# from release 17, application from release 18, database from who knows where"
# shape from ever being reachable.
release_root=$(cd -- "$NEW_RELEASE" && pwd -P)
for binary in annotation-web annotation-web-migrate; do
  resolved=$(readlink -f -- "$NEW_RELEASE/bin/$binary")
  case $resolved in
    "$release_root"/*) : ;;
    *) die 10 "bin/$binary resolves to $resolved, outside the release at $release_root; refusing to mix releases" ;;
  esac
done
record release_identity verified

DB=$(backend_db_path)
record db_path "$DB"

# A backup we cannot write is a rollback we do not have, and finding that out
# after the migration is finding it out too late.
if ! mkdir -p -- "$RF_BACKUP_DIR" 2>/dev/null || [[ ! -w $RF_BACKUP_DIR ]]; then
  die 10 "backup directory $RF_BACKUP_DIR is missing or not writable"
fi
record backup_dir "$RF_BACKUP_DIR"

if db_exists; then
  db_bytes=$(stat -c %s -- "$DB")
  free_bytes=$(( $(stat -f -c '%a * %S' -- "$RF_BACKUP_DIR" | bc 2>/dev/null || echo 0) ))
  if (( free_bytes > 0 && free_bytes < db_bytes * 3 )); then
    die 10 "only $free_bytes bytes free under $RF_BACKUP_DIR for a $db_bytes byte database"
  fi
fi

PREVIOUS=$(backend_profile_current || true)
record previous_store_path "${PREVIOUS:-none}"

# ---------------------------------------------------------------------------
# 1. Quiesce. Everything after this point assumes no writer is attached, and
#    that assumption is worth confirming rather than hoping for.
# ---------------------------------------------------------------------------

if ! stop_and_confirm; then
  die 10 "$RF_SERVICE will not stop; refusing to migrate underneath a live writer"
fi
record writers_stopped yes

# ---------------------------------------------------------------------------
# 2. Verify what we have, before making a copy of it. `integrity` deliberately
#    has no opinion about schema version -- this is the previous release's
#    database and being out of date is the entire point.
# ---------------------------------------------------------------------------

# Everything between quiescing and migrating fails the same way: put the
# previous release back and refuse, without having changed a single row. The
# exit code stays 11 even if the previous release will not come back up --
# reporting "recovery failed" would hide *why* we refused, which is the fact an
# operator needs first. Whether it came back is its own field.
refuse_before_migration() {
  local why=$1
  log "$why"
  if start_previous_release; then
    record rollback_performed true
    record rolled_back_to "${PREVIOUS:-none}"
    record operator_required false
  else
    record rollback_performed failed
    record operator_required true
    log "the previous release did not come back up either; the service is down"
  fi
  die 11 "$why"
}

if db_exists; then
  if ! sound_database "$DB"; then
    record pre_migration_integrity failed
    refuse_before_migration "the existing database fails its own integrity check; refusing to migrate or back up damage"
  fi
  record pre_migration_integrity ok
else
  record pre_migration_integrity absent
  log "no database at $DB yet; this is a first deployment and there is nothing to back up"
fi

# ---------------------------------------------------------------------------
# 3. Back up, then prove the backup is a database and holds what the live one
#    holds. An unverified backup is a comforting file, not a rollback.
# ---------------------------------------------------------------------------

BACKUP=""
discard_backup() {
  rm -f -- "$BACKUP" "$BACKUP"-wal "$BACKUP"-shm 2>/dev/null || true
  BACKUP=""
}

if db_exists; then
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  BACKUP="$RF_BACKUP_DIR/annotation-$stamp.db"

  if ! copy_database "$DB" "$BACKUP"; then
    record backup_verified "copy failed"
    discard_backup
    refuse_before_migration "could not copy $DB into $RF_BACKUP_DIR"
  fi

  # A file of the right name is not a backup. Two questions: is it a database at
  # all, and does it hold what the live one holds. A copy truncated by a full
  # disk answers yes to neither and looks fine to `ls`.
  if ! sound_database "$BACKUP"; then
    record backup_verified "not a sound database"
    discard_backup
    refuse_before_migration "the backup just written does not pass its own integrity check"
  fi

  live_digest=$(data_digest "$DB")
  backup_digest=$(data_digest "$BACKUP")
  if [[ $live_digest != "$backup_digest" ]]; then
    record backup_verified "content mismatch"
    discard_backup
    refuse_before_migration "the backup does not contain what the live database contains"
  fi

  record backup_path "$BACKUP"
  record backup_verified yes
else
  record backup_path none
  record backup_verified "not applicable"
fi

# ---------------------------------------------------------------------------
# 4. Migrate, using this release's own migrator.
# ---------------------------------------------------------------------------

recover_to_previous() {
  local why=$1 code=$2
  log "$why"
  if [[ -n $BACKUP ]]; then
    # Deliberately unconditional. The migration is written to be one SQLite
    # transaction and the test suite checks that a failure inside it leaves the
    # file untouched, but a deploy is the wrong place to rely on somebody else's
    # atomicity when a verified copy is sitting right there.
    if restore_database; then
      record db_restored true
    else
      record db_restored failed
      die 15 "could not restore $BACKUP over $DB"
    fi
  else
    record db_restored "not applicable"
  fi
  if start_previous_release; then
    record rollback_performed true
    record rolled_back_to "${PREVIOUS:-none}"
  else
    record rollback_performed failed
    die 15 "restored the database but could not bring the previous release back up"
  fi
  die "$code" "rolled back to ${PREVIOUS:-no previous release}"
}

if ! migrator migrate; then
  record migration failed
  recover_to_previous "migration failed" 12
fi
record migration applied

if ! migrator verify; then
  record post_migration_schema "not current"
  recover_to_previous "the migration reported success but the schema is not current" 12
fi
record post_migration_schema current

# The baseline the rollback decision will be measured against. Taken while the
# service is still down, so it describes the database exactly as the migration
# left it and before any respondent could add to it.
POST_MIGRATION_DIGEST=$(data_digest "$DB")

# ---------------------------------------------------------------------------
# 5. Activate and check. From here the application is reachable, which is what
#    makes the next failure branch different from every one above it.
# ---------------------------------------------------------------------------

backend_profile_set "$NEW_RELEASE" || recover_to_previous "could not switch the profile to the new release" 13
record activated_store_path "$NEW_RELEASE"
record generation "$(backend_profile_generation || echo unknown)"

backend_service_start || recover_to_previous "the new release would not start" 13

if healthy; then
  record local_health ok
  record rollback_performed false
  record outcome activated
  emit_report
  log "activated $NEW_RELEASE"
  exit 0
fi

record local_health fail
log "the new release started but never became healthy"

# Stop it before deciding anything, so nothing else can be written while we look.
stop_and_confirm || true

CURRENT_DIGEST=$(data_digest "$DB")
record post_activation_writes "$( [[ $CURRENT_DIGEST == "$POST_MIGRATION_DIGEST" ]] && echo none || echo present )"

if [[ $CURRENT_DIGEST == "$POST_MIGRATION_DIGEST" ]]; then
  # Nothing was stored while the new release was up, so the backup is still a
  # complete description of the world and going back to it loses nothing.
  recover_to_previous "no rows were written while the new release was up; restoring" 13
fi

# Something was stored. The backup no longer describes the world, so restoring
# it would not be a rollback, it would be deleting a respondent's answer. This
# is the boundary the whole design exists to respect, and it is the one place
# where the correct behaviour is to stop and get a person.
record db_restored refused
record rollback_performed false
cat >&2 <<EOF
[activate] The new release was activated, became reachable, failed its health
[activate] check, and rows were written to the database in between.
[activate]
[activate]   database:  $DB
[activate]   backup:    ${BACKUP:-none} (pre-migration, no longer complete)
[activate]   release:   $NEW_RELEASE (unhealthy, stopped)
[activate]   previous:  ${PREVIOUS:-none}
[activate]
[activate] Restoring the backup would silently discard whatever was written.
[activate] Rolling the binary back is only safe if the previous release can read
[activate] the migrated schema, which it generally cannot -- that is why it
[activate] refuses to start rather than guessing.
[activate]
[activate] The service is stopped. This needs a person: recover the new rows,
[activate] roll forward with a fix, or make an explicit, informed decision to
[activate] discard them.
EOF
die 14 "writes landed on the new schema; refusing to restore automatically"
