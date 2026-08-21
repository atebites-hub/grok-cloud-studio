#!/usr/bin/env bash
# Shared director-prompt path helpers. Expects ROOT. Optional LIB_PY.
# prompts/ is the extract canonical dir; docs/studio/directors is the
# product-floor layout. Remint must find either.
# shellcheck disable=SC2034

_gcs_capture_prompt_override() {
  if [[ -n "${_GCS_PROMPT_OVERRIDE_CAPTURED:-}" ]]; then
    return 0
  fi
  if [[ -z "${GCS_PROMPT_DIR:-}" && -n "${PROMPTS_DIR:-}" ]]; then
    GCS_PROMPT_DIR="$PROMPTS_DIR"
  fi
  _GCS_PROMPT_OVERRIDE_CAPTURED=1
}

gcs_prompts_dir() {
  if [[ -n "${GCS_PROMPT_DIR:-}" ]]; then
    printf '%s\n' "$GCS_PROMPT_DIR"
    return 0
  fi
  local shipped="${ROOT:?}/prompts"
  local docs="$ROOT/docs/studio/directors"
  if [[ -d "$shipped" ]] && compgen -G "$shipped/*_director_prompt.txt" >/dev/null; then
    printf '%s\n' "$shipped"
    return 0
  fi
  if [[ -d "$docs" ]] && compgen -G "$docs/*_director_prompt.txt" >/dev/null; then
    printf '%s\n' "$docs"
    return 0
  fi
  if [[ -d "$shipped" ]]; then
    printf '%s\n' "$shipped"
    return 0
  fi
  printf '%s\n' "$docs"
}

gcs_resolve_prompt_file() {
  local seat="${1:?}"
  local out stem cand d n
  if [[ -n "${LIB_PY:-}" && -f "$LIB_PY" ]]; then
    out="$(python3 "$LIB_PY" prompt-file "$seat" 2>/dev/null || true)"
    if [[ -n "$out" && -f "$out" ]]; then
      printf '%s\n' "$out"
      return 0
    fi
  fi
  stem="${seat//-/_}"
  local names=("${stem}_director_prompt.txt")
  case "$seat" in
    floor-ops) names+=("floor_director_prompt.txt") ;;
    floor) names+=("floor_ops_director_prompt.txt") ;;
    studio-ops) names+=("ops_director_prompt.txt") ;;
    ops) names+=("studio_ops_director_prompt.txt") ;;
  esac
  local dirs=()
  [[ -n "${GCS_PROMPT_DIR:-}" ]] && dirs+=("$GCS_PROMPT_DIR")
  dirs+=("$ROOT/prompts" "$ROOT/docs/studio/directors")
  for d in "${dirs[@]}"; do
    [[ -n "$d" ]] || continue
    for n in "${names[@]}"; do
      cand="$d/$n"
      if [[ -f "$cand" ]]; then
        printf '%s\n' "$cand"
        return 0
      fi
    done
  done
  return 1
}

_gcs_capture_prompt_override
PROMPTS_DIR="$(gcs_prompts_dir)"
