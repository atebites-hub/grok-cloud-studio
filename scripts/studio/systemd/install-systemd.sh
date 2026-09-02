#!/usr/bin/env bash
# Install user systemd units that run recover.sh on boot.
# Never pass --daemons. Never reconnect Agent Kanban. Never print secrets.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$ROOT"
export GCS_ROOT="${GCS_ROOT:-$ROOT}"

# shellcheck source=../taskboard/common.sh
source "$ROOT/scripts/studio/taskboard/common.sh"
gcs_source_studio_env

usage() {
  cat <<'EOF'
Usage: install-systemd.sh [--help]

Install lingering-safe user units that run ./recover.sh on boot:
  gcs-recover.service  oneshot -> recover.sh (NO --daemons)
  gcs-recover.timer    OnBootSec=30

Skip: GCS_SYSTEMD=0. Dry-run: GCS_SYSTEMD_DRY_RUN=1 writes units to
GCS_SYSTEMD_DEST (default ~/.config/systemd/user) without systemctl.
Does not install or enable Agent Kanban units. See docs/studio/WIPE.md.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -gt 0 ]]; then
  echo "error: unknown argument $1" >&2
  usage >&2
  exit 2
fi

skip() {
  echo "SYSTEMD_SKIP $*"
  exit 0
}

case "${GCS_SYSTEMD:-}" in
  0|false|off|no) skip "GCS_SYSTEMD=0" ;;
esac

STATE="$(gcs_studio_state_dir)"
export GCS_A2A_STATE="$STATE"
DEST="${GCS_SYSTEMD_DEST:-${HOME:-/tmp}/.config/systemd/user}"
mkdir -p "$DEST"

render() {
  local src="$1" dest="$2"
  sed \
    -e "s|@GCS_ROOT@|${GCS_ROOT}|g" \
    -e "s|@GCS_A2A_STATE@|${STATE}|g" \
    "$src" >"$dest"
}

render "$SCRIPT_DIR/gcs-recover.service.in" "$DEST/gcs-recover.service"
render "$SCRIPT_DIR/gcs-recover.timer.in" "$DEST/gcs-recover.timer"

if [[ "${GCS_SYSTEMD_DRY_RUN:-0}" == "1" ]]; then
  echo "SYSTEMD_DRY dest=$DEST service=$DEST/gcs-recover.service timer=$DEST/gcs-recover.timer"
  exit 0
fi

if ! command -v systemctl >/dev/null 2>&1; then
  skip "systemctl missing (units written to $DEST)"
fi

systemctl --user daemon-reload
systemctl --user enable --now gcs-recover.timer
echo "SYSTEMD_OK dest=$DEST"
