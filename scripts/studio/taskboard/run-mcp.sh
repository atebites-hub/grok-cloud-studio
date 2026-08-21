#!/usr/bin/env bash
# Cursor CLI / stdio MCP: taskboard --db $DB mcp
# Resolves DB from GCS_TASKBOARD_DB / TASKBOARD_DB / $GCS_A2A_STATE.
# Never prints secrets. Agent Kanban stays gone. Not a GROK_HOME copy.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
gcs_source_studio_env

bin=""
if ! bin="$(gcs_taskboard_bin)"; then
  echo "taskboard binary not found. Run scripts/studio/taskboard/install-taskboard.sh" >&2
  exit 1
fi
db="$(gcs_taskboard_db)"
mkdir -p "$(dirname "$db")"
exec "$bin" --db "$db" mcp "$@"
