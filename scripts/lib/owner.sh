# SPDX-License-Identifier: MIT
# Sourced by scripts/verify-*.sh: who owns the repo, where their home is, and
# re-running a script as them. Works with GNU tools (Linux, the sandbox) and
# BSD ones (macOS); bash 3.2 compatible.

# repo_owner DIR: the user who owns DIR.
repo_owner() {
  stat -c %U "$1" 2> /dev/null || stat -f %Su "$1"
}

# owner_home USER: USER's home directory, from getent where it answers (Linux),
# else from ~USER. USER must look like a user name: ~USER is expanded by eval.
owner_home() {
  case "$1" in
    "" | *[!A-Za-z0-9._-]*)
      echo "not a user name: $1" >&2
      return 2
      ;;
  esac
  local home
  home="$(getent passwd "$1" 2> /dev/null | cut -d: -f6)"
  [ -n "$home" ] || eval "home=~$1"
  echo "$home"
}

# run_as_owner DIR SELF [ARGS...]: returns if the current user owns DIR. As root
# (the sandbox's desktop terminal) it re-runs SELF as the owner, passing HOME,
# PATH, LANG and every CONTRACT_* variable: PostgreSQL won't run as root, and
# files root made in the repo would be unusable to its owner. Anyone else is
# told who to run it as, and the script stops.
run_as_owner() {
  local dir="$1" self="$2" owner
  shift 2
  owner="$(repo_owner "$dir")"
  [ "$(id -un)" = "$owner" ] && return 0
  if [ "$(id -u)" = 0 ] && command -v runuser > /dev/null; then
    local contract=() line
    while IFS= read -r line; do contract+=("$line"); done < <(env | grep '^CONTRACT_' || true)
    echo "== re-running as $owner (the repo's owner) =="
    exec runuser -u "$owner" -- env HOME="$(owner_home "$owner")" PATH="$PATH" LANG=C.UTF-8 \
      ${contract[@]+"${contract[@]}"} bash "$self" "$@"
  fi
  echo "FAIL run as $owner, who owns $dir"
  exit 1
}
