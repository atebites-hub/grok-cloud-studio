#!/usr/bin/env bash
# Install tcarac/taskboard from scripts/studio/taskboard/PIN (v0.6.0 on main).
# Source pin: vendor/taskboard submodule. Prefer a prebuilt already in that
# checkout; else brew tap; else GitHub tarball. Do not compile. Do not vendor
# the binary into git. Agent Kanban stays gone. studio-ops bumps PIN via
# upgrade-taskboard.sh — do not snowflake a second version string.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

VERSION="${TASKBOARD_VERSION:-$(gcs_taskboard_pin)}"
DEST_DIR="${TASKBOARD_INSTALL_DIR:-$HOME/.local/bin}"
ROOT_BIN="$GCS_KIT_ROOT/bin"
REPO_SLUG="tcarac/taskboard"
ASSET_BASE="https://github.com/${REPO_SLUG}/releases/download/${VERSION}"

usage() {
  cat <<EOF
Usage: install-taskboard.sh

Installs tcarac/taskboard ${VERSION} onto PATH (PIN $(gcs_taskboard_pin_file)):
  0. Prefer a prebuilt already in vendor/taskboard (source pin; usually none)
  1. brew tap tcarac/taskboard && brew install taskboard
  2. else GitHub release tarball (linux/darwin amd64/arm64)

Does not compile from source. Does not vendor a compiled binary blob.
Bump the pin with upgrade-taskboard.sh --apply vX.Y.Z (studio-ops).
See scripts/studio/taskboard/README.md and docs/studio/WIPE.md.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

gcs_ensure_taskboard_submodule || true

already="$(gcs_taskboard_bin 2>/dev/null || true)"
if [[ -n "$already" ]]; then
  gcs_install_host_ticket_links || true
  echo "TASKBOARD_INSTALL_ALREADY bin=$already"
  exit 0
fi

if prebuilt="$(gcs_taskboard_submodule_prebuilt)"; then
  gcs_install_host_ticket_links || true
  echo "TASKBOARD_INSTALL_ALREADY source=vendor/taskboard bin=$prebuilt"
  exit 0
fi

install_from_brew() {
  command -v brew >/dev/null 2>&1 || return 1
  echo "TASKBOARD_INSTALL brew tap ${REPO_SLUG}"
  brew tap tcarac/taskboard
  brew install taskboard
}

os_arch() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$os" in
    linux|darwin) ;;
    *)
      echo "error: unsupported OS $os (need linux or darwin tarball)" >&2
      return 1
      ;;
  esac
  case "$arch" in
    x86_64|amd64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *)
      echo "error: unsupported arch $arch" >&2
      return 1
      ;;
  esac
  printf '%s %s\n' "$os" "$arch"
}

install_from_tarball() {
  local os arch url tmp tarball dest found
  read -r os arch < <(os_arch)
  url="${ASSET_BASE}/taskboard-${os}-${arch}.tar.gz"
  tmp="$(mktemp -d)"
  tarball="$tmp/taskboard.tar.gz"
  dest="${DEST_DIR}"
  mkdir -p "$dest"
  echo "TASKBOARD_INSTALL tarball $url"
  if ! curl -fsSL --retry 3 "$url" -o "$tarball"; then
    echo "error: failed to download $url" >&2
    rm -rf "$tmp"
    return 1
  fi
  tar -xzf "$tarball" -C "$tmp"
  found="$(find "$tmp" -type f -name 'taskboard*' ! -name '*.tar.gz' | head -n 1)"
  if [[ -z "$found" ]]; then
    echo "error: tarball had no taskboard binary" >&2
    rm -rf "$tmp"
    return 1
  fi
  install -m 0755 "$found" "$dest/taskboard"
  if [[ -d "$GCS_KIT_ROOT" ]]; then
    mkdir -p "$ROOT_BIN"
    if [[ ! -e "$ROOT_BIN/taskboard" ]]; then
      ln -s "$dest/taskboard" "$ROOT_BIN/taskboard" 2>/dev/null || \
        install -m 0755 "$found" "$ROOT_BIN/taskboard" || true
    fi
  fi
  rm -rf "$tmp"
  echo "TASKBOARD_INSTALL_OK bin=$dest/taskboard version=$VERSION"
}

if install_from_brew; then
  gcs_install_host_ticket_links || true
  echo "TASKBOARD_INSTALL_OK source=brew version=$VERSION"
  exit 0
fi

echo "TASKBOARD_INSTALL brew unavailable or failed; using GitHub release tarball"
install_from_tarball
gcs_install_host_ticket_links || true
