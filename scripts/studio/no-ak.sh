# Fail-closed: never start or reconnect Agent Kanban (`ak` / AMA).
# Sourced by start-studio-bus.sh, recover.sh, and doctor.sh.
# Board stays tcarac/taskboard. Do not exec ak, ama, or the removed tree.
# shellcheck shell=bash

gcs_ak_norm_bridge() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]' | tr -d '"'
}

gcs_ak_bridge_from_studio_env() {
  local envf="" line="" val=""
  if [[ -n "${GCS_A2A_STATE:-}" && -f "${GCS_A2A_STATE}/studio.env" ]]; then
    envf="${GCS_A2A_STATE}/studio.env"
  elif [[ -n "${GCS_ROOT:-}" && -f "${GCS_ROOT}/.a2a-state/studio.env" ]]; then
    envf="${GCS_ROOT}/.a2a-state/studio.env"
  fi
  [[ -n "$envf" ]] || return 0
  line="$(grep -E '^[[:space:]]*PALEMON_AK_BRIDGE=' "$envf" 2>/dev/null | tail -n 1 || true)"
  [[ -n "$line" ]] || return 0
  val="${line#*=}"
  gcs_ak_norm_bridge "$val"
}

gcs_ak_bridge_on() {
  local v
  v="$(gcs_ak_norm_bridge "${PALEMON_AK_BRIDGE:-}")"
  if [[ -z "$v" ]]; then
    v="$(gcs_ak_bridge_from_studio_env)"
  fi
  case "$v" in
    ""|0|false|no|off) return 1 ;;
    *) return 0 ;;
  esac
}

gcs_ak_tree_present() {
  local root="${1:-}" cand
  for cand in \
    "${root}/scripts/studio/agent-kanban" \
    "${GCS_ROOT:-}/scripts/studio/agent-kanban"
  do
    [[ "$cand" == "/scripts/studio/agent-kanban" ]] && continue
    [[ -e "$cand" ]] || continue
    printf '%s' "$cand"
    return 0
  done
  return 1
}

gcs_refuse_agent_kanban() {
  local root="${1:-${GCS_ROOT:-}}"
  local tree=""
  tree="$(gcs_ak_tree_present "$root" || true)"
  if [[ -n "$tree" ]]; then
    echo "AK_REFUSE tree=scripts/studio/agent-kanban — Agent Kanban was removed; do not reconnect ak. Board is tcarac/taskboard." >&2
    return 1
  fi
  if gcs_ak_bridge_on; then
    echo "AK_REFUSE PALEMON_AK_BRIDGE — Agent Kanban was removed; do not reconnect ak. Board is tcarac/taskboard." >&2
    return 1
  fi
  return 0
}
