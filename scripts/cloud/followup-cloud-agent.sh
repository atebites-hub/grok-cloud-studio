#!/usr/bin/env bash
# Follow-up prompt on an existing Cursor Cloud agent. SDK-first (resume+send).
# REFUSE when latest runStatus is RUNNING (do not stack a second live Extra High).
# Leftover ACTIVE+FINISHED may follow up. Never Bot CloudAgent.
# Usage: followup-cloud-agent.sh <bc-id> "prompt"
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/followup.sh" "$@"
