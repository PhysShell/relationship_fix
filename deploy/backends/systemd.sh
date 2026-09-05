#!/usr/bin/env bash
# The production host adapter: systemd for the process, a nix profile for the
# release, the unit's own environment for the database path.
#
# Everything host-shaped lives behind these functions so the choreography in
# activate.sh -- which is where all the decisions and all the risk are -- is the
# same code under test as it is on the VPS.

backend_service_stop() {
  sudo systemctl stop "$RF_SERVICE"
}

backend_service_start() {
  sudo systemctl start "$RF_SERVICE"
}

backend_service_running() {
  systemctl is-active --quiet "$RF_SERVICE"
}

backend_profile_set() {
  sudo nix-env --profile "$RF_PROFILE" --set "$1"
}

backend_profile_current() {
  [[ -e $RF_PROFILE ]] || return 1
  readlink -f -- "$RF_PROFILE"
}

backend_profile_generation() {
  # `nix-env --list-generations` marks the live one with a trailing "(current)".
  sudo nix-env --profile "$RF_PROFILE" --list-generations 2>/dev/null \
    | awk '/\(current\)/ { print $1 }'
}

# Ask the unit where the database is rather than keeping a second copy of the
# answer here. A backup of a different file than the application writes is worse
# than no backup, because it looks like one.
backend_db_path() {
  if [[ -n ${RF_DB_PATH:-} ]]; then
    printf '%s\n' "$RF_DB_PATH"
    return 0
  fi
  local from_unit
  from_unit=$(systemctl show -p Environment --value "$RF_SERVICE" 2>/dev/null \
    | tr ' ' '\n' \
    | sed -n 's/^RF_DB_PATH=//p' \
    | head -1)
  printf '%s\n' "${from_unit:-/var/lib/relationship-fix/annotation.db}"
}
