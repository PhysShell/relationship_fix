#!/usr/bin/env bash
# The test host adapter: no systemd, no sudo, no VPS.
#
# What it fakes is the host -- a unit, a nix profile, a machine. What it does
# not fake is the application: `backend_service_start` runs the real
# annotation-web binary out of the release the profile points at, on a real
# port, and activate.sh health-checks it over real HTTP. So the interesting
# behaviour under test is the actual server refusing an unrecognised database,
# not a stub agreeing that it would have.
#
# Driven by RF_FAKE_ROOT, which holds the profile symlink, the pid file and the
# service log.

backend_service_stop() {
  # Host conditions are simulated here, in the host adapter, because that is
  # what a host adapter is for. A unit that will not die is a real thing, and
  # the choreography needs an answer to it that is not "assume it worked".
  #
  # The _AFTER_START variant only starts refusing once something has been
  # started, so a scenario can let the deploy quiesce normally and then fail the
  # stop that follows a bad health check -- which is the branch worth testing,
  # rather than the preflight one.
  [[ ${RF_FAKE_STOP_FAILS:-} == 1 ]] && return 1
  if [[ ${RF_FAKE_STOP_FAILS_AFTER_START:-} == 1 && -f $RF_FAKE_ROOT/service.pid ]]; then
    return 1
  fi
  local pidfile="$RF_FAKE_ROOT/service.pid"
  [[ -f $pidfile ]] || return 0
  local pid
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    local waited=0
    while kill -0 "$pid" 2>/dev/null && (( waited < 50 )); do
      sleep 0.1
      waited=$(( waited + 1 ))
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pidfile"
}

backend_service_start() {
  local release
  release=$(backend_profile_current) || return 1
  [[ -x $release/bin/annotation-web ]] || return 1
  # Start it with a clean file descriptor table, the way a supervisor would.
  # systemd starts the unit from PID 1, so the service inherits nothing from
  # whoever ran `systemctl start`. A plain background job here inherits
  # everything activate.sh has open -- including the descriptor its activation
  # lock is held on, which would leave the lock held for as long as the service
  # runs and wedge every later deploy. That divergence would be invisible in the
  # matrix and absent in production, which is the worst combination, so the fake
  # closes them instead of pretending the question does not exist.
  (
    local fd
    for fd in /proc/$$/fd/*; do
      case ${fd##*/} in
        0 | 1 | 2) ;;
        *) eval "exec ${fd##*/}>&-" 2>/dev/null || true ;;
      esac
    done
    RF_DB_PATH="$(backend_db_path)" \
    RF_SESSION_KEY_PATH="$RF_FAKE_ROOT/session-key.aes" \
    PORT="$RF_FAKE_PORT" \
      exec "$release/bin/annotation-web" >>"$RF_FAKE_ROOT/service.log" 2>&1
  ) &
  echo $! > "$RF_FAKE_ROOT/service.pid"
  # Started is not running: the server exits on a database it will not serve,
  # and a fake that reported success there would hide the very behaviour the
  # matrix is checking.
  sleep 0.5
  backend_service_running
}

backend_service_running() {
  local pidfile="$RF_FAKE_ROOT/service.pid"
  [[ -f $pidfile ]] || return 1
  kill -0 "$(cat "$pidfile")" 2>/dev/null
}

backend_profile_set() {
  ln -sfn "$1" "$RF_FAKE_ROOT/profile.new"
  mv -T "$RF_FAKE_ROOT/profile.new" "$RF_FAKE_ROOT/profile"
  local generation
  generation=$(( $(cat "$RF_FAKE_ROOT/generation" 2>/dev/null || echo 0) + 1 ))
  echo "$generation" > "$RF_FAKE_ROOT/generation"
}

backend_profile_current() {
  [[ -L $RF_FAKE_ROOT/profile ]] || return 1
  readlink -f -- "$RF_FAKE_ROOT/profile"
}

backend_profile_generation() {
  cat "$RF_FAKE_ROOT/generation" 2>/dev/null || echo 0
}

backend_db_path() {
  printf '%s\n' "${RF_DB_PATH:-$RF_FAKE_ROOT/annotation.db}"
}
