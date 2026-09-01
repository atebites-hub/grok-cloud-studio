#!/usr/bin/env bash
# studio-ops maintainer: bump tcarac/taskboard pin without a snowflake dashboard.
# Default --check. Mutation requires --apply TAG. Never compile. Never reconnect ak.
# Never copy GROK_HOME MCP into Cursor CLI. Do not remint the pin unless applying.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

usage() {
  cat <<'EOF'
Usage: upgrade-taskboard.sh [--check]
       upgrade-taskboard.sh --dry-run vX.Y.Z
       upgrade-taskboard.sh --apply vX.Y.Z [--skip-submodule]

studio-ops maintainer kit for tcarac/taskboard:
  --check            PIN matches .gitmodules; Agent Kanban tree absent (default)
  --dry-run TAG      print the bump plan; do not write PIN or .gitmodules
  --apply TAG        write PIN + .gitmodules branch (submodule checkout unless
                     --skip-submodule). Then run install-taskboard.sh.

Never floats main. Never compiles. Never vendors a binary blob.
Never reconnects Agent Kanban. Dashboard stays LEGACY.
Seat stdio MCP stays in isolated GROK_HOME/config.toml (never Cursor workspace-folder token).
Never copy GROK_HOME into Cursor CLI.
Ticket move uses the 26-char Crockford ULID primary key, not T-1/PAL-1.
EOF
}

gcs_taskboard_refuse_ak() {
  local tree="$GCS_KIT_ROOT/scripts/studio/agent-kanban"
  if [[ -e "$tree" ]]; then
    echo "AK_REFUSE tree=$tree — do not reconnect ak / Agent Kanban" >&2
    echo "TASKBOARD_UPGRADE_FAIL reason=ak-reconnect" >&2
    return 1
  fi
  return 0
}

gcs_taskboard_validate_tag() {
  local tag="${1:-}"
  local low
  low="$(printf '%s' "$tag" | tr '[:upper:]' '[:lower:]')"
  case "$low" in
    ""|main|master|head|origin/main|origin/master)
      echo "TASKBOARD_UPGRADE_FAIL reason=floating-ref tag=${tag:-empty} (pin a vX.Y.Z release, not main)" >&2
      return 1
      ;;
  esac
  if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "TASKBOARD_UPGRADE_FAIL reason=bad-tag tag=$tag (need vX.Y.Z)" >&2
    return 1
  fi
  return 0
}

gcs_taskboard_gitmodules_branch() {
  local gm="$GCS_KIT_ROOT/.gitmodules"
  if [[ ! -f "$gm" ]]; then
    echo "TASKBOARD_UPGRADE_FAIL missing $gm" >&2
    return 1
  fi
  git config -f "$gm" --get submodule.vendor/taskboard.branch
}

gcs_taskboard_write_pin() {
  local tag="$1"
  local pinf dest
  pinf="$(gcs_taskboard_pin_file)"
  dest="$(dirname "$pinf")"
  mkdir -p "$dest"
  cat >"$pinf" <<EOF
# tcarac/taskboard release tag (not floating main).
# studio-ops bumps this with scripts/studio/taskboard/upgrade-taskboard.sh --apply vX.Y.Z
# then reinstalls the host binary (brew/tarball). Do not compile. Do not vendor a blob.
# Do not reconnect Agent Kanban. Dashboard under scripts/studio/dashboard/ stays LEGACY.
${tag}
EOF
}

gcs_taskboard_write_gitmodules_branch() {
  local tag="$1"
  local gm="$GCS_KIT_ROOT/.gitmodules"
  if [[ ! -f "$gm" ]]; then
    echo "TASKBOARD_UPGRADE_FAIL missing $gm" >&2
    return 1
  fi
  git config -f "$gm" submodule.vendor/taskboard.branch "$tag"
}

gcs_taskboard_dashboard_legacy() {
  local dash="$GCS_KIT_ROOT/scripts/studio/dashboard/README.md"
  if [[ -f "$dash" ]] && ! grep -q "LEGACY" "$dash"; then
    echo "TASKBOARD_UPGRADE_FAIL snowflake dashboard (scripts/studio/dashboard must stay LEGACY)" >&2
    return 1
  fi
  return 0
}

gcs_taskboard_check() {
  local pin branch
  gcs_taskboard_refuse_ak
  gcs_taskboard_dashboard_legacy
  pin="$(gcs_taskboard_pin)"
  gcs_taskboard_validate_tag "$pin"
  branch="$(gcs_taskboard_gitmodules_branch)"
  if [[ "$pin" != "$branch" ]]; then
    echo "TASKBOARD_UPGRADE_FAIL pin=$pin gitmodules.branch=$branch (mismatch)" >&2
    return 1
  fi
  echo "TASKBOARD_PIN_OK pin=$pin gitmodules.branch=$branch src=$(gcs_taskboard_pin_file)"
  echo "notes=ticket move uses Crockford ULID; seat MCP stays GROK_HOME/config.toml; never copy GROK_HOME; dashboard LEGACY; do not reconnect ak"
}

gcs_taskboard_plan() {
  local want="$1" have
  have="$(gcs_taskboard_pin 2>/dev/null || echo none)"
  cat <<EOF
TASKBOARD_UPGRADE_DRY_RUN pin=$have want=$want
steps:
  1. write $(gcs_taskboard_pin_file)
  2. git config -f .gitmodules submodule.vendor/taskboard.branch $want
  3. git submodule update --init --recursive -- vendor/taskboard (checkout $want)
  4. bash scripts/studio/taskboard/install-taskboard.sh
never:
  compile / go build / make build
  vendor a compiled binary blob
  reconnect ak / Agent Kanban / scripts/studio/agent-kanban
  promote scripts/studio/dashboard (stays LEGACY; not a snowflake board)
  copy GROK_HOME MCP into Cursor CLI
  seat MCP via Cursor workspace-folder token (GROK_HOME/config.toml stdio only)
ticket move: Crockford ULID primary key (26 chars), not T-1/PAL-1/display-key
EOF
}

gcs_taskboard_apply() {
  local tag="$1" skip="${2:-0}"
  gcs_taskboard_refuse_ak
  gcs_taskboard_dashboard_legacy
  gcs_taskboard_validate_tag "$tag"
  gcs_taskboard_write_pin "$tag"
  gcs_taskboard_write_gitmodules_branch "$tag"
  if [[ "$skip" != "1" ]]; then
    git -C "$GCS_KIT_ROOT" submodule set-branch -b "$tag" -- vendor/taskboard 2>/dev/null || true
    git -C "$GCS_KIT_ROOT" submodule update --init --recursive -- vendor/taskboard
    if [[ -e "$GCS_KIT_ROOT/vendor/taskboard/.git" ]]; then
      git -C "$GCS_KIT_ROOT/vendor/taskboard" fetch --tags --force
      git -C "$GCS_KIT_ROOT/vendor/taskboard" checkout --detach "$tag"
    fi
  fi
  echo "TASKBOARD_UPGRADE_OK pin=$tag next=scripts/studio/taskboard/install-taskboard.sh skip_submodule=$skip"
  echo "notes=do not compile; do not vendor binary; do not reconnect ak; dashboard stays LEGACY; never copy GROK_HOME; ticket move uses ULID"
}

cmd="check"
tag=""
skip_submodule=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --check)
      cmd="check"
      shift
      ;;
    --dry-run)
      cmd="dry-run"
      tag="${2:-}"
      shift 2 || true
      ;;
    --apply)
      cmd="apply"
      tag="${2:-}"
      shift 2 || true
      ;;
    --skip-submodule)
      skip_submodule=1
      shift
      ;;
    *)
      echo "error: unknown argument $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$cmd" in
  check)
    gcs_taskboard_check
    ;;
  dry-run)
    gcs_taskboard_refuse_ak
    gcs_taskboard_validate_tag "$tag"
    gcs_taskboard_plan "$tag"
    ;;
  apply)
    gcs_taskboard_apply "$tag" "$skip_submodule"
    ;;
esac
