#!/usr/bin/env bash
# Locate or install Node >= 22.13 for @cursor/sdk. Prints the node binary path.
# Never prints secrets. Cache: ~/.cache/gcs-node/<version>
set -euo pipefail

NEED_MAJOR=22
NEED_MINOR=13
NODE_DIST_VER="${GCS_NODE_DIST_VER:-v22.14.0}"
CACHE_ROOT="${GCS_NODE_CACHE:-$HOME/.cache/gcs-node}"

node_ok() {
  local bin="$1"
  [[ -x "$bin" ]] || return 1
  "$bin" -e 'const [maj,min]=process.versions.node.split(".").map(Number); process.exit(maj>22|| (maj===22 && min>=13) ? 0 : 1)' 2>/dev/null
}

emit() {
  printf '%s\n' "$1"
}

# 1) explicit override
if [[ -n "${GCS_NODE:-}" ]] && node_ok "$GCS_NODE"; then
  emit "$GCS_NODE"
  return 0 2>/dev/null || exit 0
fi

# 2) already-new node on PATH
if command -v node >/dev/null 2>&1 && node_ok "$(command -v node)"; then
  emit "$(command -v node)"
  return 0 2>/dev/null || exit 0
fi

# 3) cached official tarball
CACHED="${CACHE_ROOT}/${NODE_DIST_VER}/bin/node"
if node_ok "$CACHED"; then
  emit "$CACHED"
  return 0 2>/dev/null || exit 0
fi

# 4) fnm / nvm / volta if the host already has them
if command -v fnm >/dev/null 2>&1; then
  eval "$(fnm env)" || true
  fnm install 22 >/dev/null 2>&1 || true
  fnm use 22 >/dev/null 2>&1 || true
  if command -v node >/dev/null 2>&1 && node_ok "$(command -v node)"; then
    emit "$(command -v node)"
    return 0 2>/dev/null || exit 0
  fi
fi

if [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
  nvm install 22 >/dev/null 2>&1 || true
  nvm use 22 >/dev/null 2>&1 || true
  if command -v node >/dev/null 2>&1 && node_ok "$(command -v node)"; then
    emit "$(command -v node)"
    return 0 2>/dev/null || exit 0
  fi
fi

if command -v volta >/dev/null 2>&1; then
  volta install node@22 >/dev/null 2>&1 || true
  if command -v node >/dev/null 2>&1 && node_ok "$(command -v node)"; then
    emit "$(command -v node)"
    return 0 2>/dev/null || exit 0
  fi
fi

# 5) download official linux/darwin tarball into the cache
arch="$(uname -m)"
os="$(uname -s)"
case "$os" in
  Linux)  plat="linux" ;;
  Darwin) plat="darwin" ;;
  *)
    echo "CLOUD_SDK_ERR: unsupported OS for Node bootstrap ($os); install Node >= ${NEED_MAJOR}.${NEED_MINOR}" >&2
    exit 75
    ;;
esac
case "$arch" in
  x86_64|amd64) cpu="x64" ;;
  aarch64|arm64) cpu="arm64" ;;
  *)
    echo "CLOUD_SDK_ERR: unsupported arch for Node bootstrap ($arch); install Node >= ${NEED_MAJOR}.${NEED_MINOR}" >&2
    exit 75
    ;;
esac

mkdir -p "$CACHE_ROOT"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tarball="node-${NODE_DIST_VER}-${plat}-${cpu}.tar.gz"
url="https://nodejs.org/dist/${NODE_DIST_VER}/${tarball}"
if ! curl -fsSL "$url" -o "${tmp}/${tarball}"; then
  echo "CLOUD_SDK_ERR: failed to download Node ${NODE_DIST_VER} from nodejs.org" >&2
  exit 75
fi
tar -xzf "${tmp}/${tarball}" -C "$tmp"
dest="${CACHE_ROOT}/${NODE_DIST_VER}"
rm -rf "$dest"
mv "${tmp}/node-${NODE_DIST_VER}-${plat}-${cpu}" "$dest"
if ! node_ok "${dest}/bin/node"; then
  echo "CLOUD_SDK_ERR: Node ${NODE_DIST_VER} installed but version check failed" >&2
  exit 75
fi
emit "${dest}/bin/node"
