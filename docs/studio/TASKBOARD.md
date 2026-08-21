# Taskboard

Studio mission control is **[tcarac/taskboard](https://github.com/tcarac/taskboard)** — ticket CLI plus HTTP `/mcp`.

Agent Kanban (`ak`, AMA, `scripts/studio/agent-kanban/`) was removed from this control plane. Do not reconnect it. Do not run `ak start` from the A2A bus.

## What Directors should use

- Ticket CLI from the taskboard checkout (create / move / comment).
- MCP over HTTP `/mcp` when the taskboard server is running locally.
- GROW keep-alives (`ACP_PING STATUS/CONTINUE`) allow a ticket move as work. They are not a LAUNCH assigner.

This repository does not vendor the taskboard binary. Point seats at your local taskboard checkout the same way you point Extra High at `GCS_CLOUD_REPO`.

The HTML files under `scripts/studio/dashboard/` remain LEGACY and are not the board.
