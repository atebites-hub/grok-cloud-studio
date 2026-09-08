# Recover/doctor Extra High park. Distinct from launch-cloud-extra-high.sh.
# Honor CLOUD_API_PARKED env, studio.env, or $GCS_A2A_STATE/CLOUD_API_PARKED.
# Never print secrets. Never Bot CloudAgent. Living Sky (LIV) only.
# shellcheck shell=bash

gcs_cloud_api_park_norm() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]' | tr -d '"'
}

gcs_cloud_api_park_from_studio_env() {
  local envf="" line="" val=""
  if [[ -n "${GCS_A2A_STATE:-}" && -f "${GCS_A2A_STATE}/studio.env" ]]; then
    envf="${GCS_A2A_STATE}/studio.env"
  elif [[ -n "${GCS_ROOT:-}" && -f "${GCS_ROOT}/.a2a-state/studio.env" ]]; then
    envf="${GCS_ROOT}/.a2a-state/studio.env"
  fi
  [[ -n "$envf" ]] || return 0
  line="$(grep -E '^[[:space:]]*CLOUD_API_PARKED=' "$envf" 2>/dev/null | tail -n 1 || true)"
  [[ -n "$line" ]] || return 0
  val="${line#*=}"
  gcs_cloud_api_park_norm "$val"
}

gcs_cloud_api_park_marker() {
  if [[ -n "${GCS_A2A_STATE:-}" && -e "${GCS_A2A_STATE}/CLOUD_API_PARKED" ]]; then
    printf '%s\n' "${GCS_A2A_STATE}/CLOUD_API_PARKED"
    return 0
  fi
  if [[ -n "${GCS_ROOT:-}" && -e "${GCS_ROOT}/.a2a-state/CLOUD_API_PARKED" ]]; then
    printf '%s\n' "${GCS_ROOT}/.a2a-state/CLOUD_API_PARKED"
    return 0
  fi
  return 1
}

gcs_cloud_api_parked() {
  local v marker body
  v="$(gcs_cloud_api_park_norm "${CLOUD_API_PARKED:-}")"
  if [[ -z "$v" ]]; then
    v="$(gcs_cloud_api_park_from_studio_env)"
  fi
  case "$v" in
    ""|0|false|no|off) ;;
    *) return 0 ;;
  esac
  marker="$(gcs_cloud_api_park_marker 2>/dev/null || true)"
  [[ -n "$marker" && -e "$marker" ]] || return 1
  body="$(tr -d '[:space:]' < "$marker" 2>/dev/null || true)"
  case "$(gcs_cloud_api_park_norm "$body")" in
    0|false|no|off) return 1 ;;
    *) return 0 ;;
  esac
}
