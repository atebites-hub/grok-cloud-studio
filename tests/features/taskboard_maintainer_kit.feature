# Host tcarac/taskboard maintainer kit: start / health / docs.
# Executable binding: tests/test_taskboard_maintainer_kit.py
# Distinct from GCS #112 (fleet-shepherd TASKBOARD_HEALTH probes).
# Distinct from GCS #100 (seat GROK_HOME stdio MCP).
# Palemon Linear is Living Sky (LIV), not Black Swan. Never Bot CloudAgent.
# Never reconnect Agent Kanban. Do not vendor Hermes.

Feature: studio-ops can start, health-check, and document the board
  The maintainer kit lives under scripts/studio/taskboard.
  GET /health on the MCP HTTP port is not a usable board.
  Usable means the SQLite DB exists, the UI is up, and either
  `taskboard --db $DB ticket list` succeeds or POST /mcp returns 2xx.

  Scenario: missing DB is not healthy
    Given GCS_A2A_STATE has no taskboard.db
    When health-taskboard.sh runs
    Then it prints TASKBOARD_HEALTH_FAIL reason=missing-db
    And it exits 1

  Scenario: GET /health alone is not enough
    Given taskboard.db exists and the UI is up
    And MCP HTTP answers GET /health but not POST /mcp
    And ticket list is unavailable
    When health-taskboard.sh runs
    Then it prints TASKBOARD_HEALTH_FAIL
    And it does not print TASKBOARD_HEALTH_OK

  Scenario: DB plus ticket list is healthy
    Given taskboard.db exists and the UI is up
    And TASKBOARD_BIN ticket list succeeds
    When health-taskboard.sh runs
    Then it prints TASKBOARD_HEALTH_OK
    And argv includes --db and ticket list

  Scenario: DB plus POST /mcp is healthy
    Given taskboard.db exists and the UI is up
    And MCP HTTP POST /mcp returns 2xx
    When health-taskboard.sh runs
    Then it prints TASKBOARD_HEALTH_OK

  Scenario: Agent Kanban tree is refused
    Given scripts/studio/agent-kanban exists under GCS_ROOT
    When health-taskboard.sh or maintainer.sh start runs
    Then it prints AK_REFUSE
    And it does not start ak

  Scenario: maintainer.sh start starts UI and MCP HTTP
    When maintainer.sh start runs
    Then it delegates to start-taskboard.sh start and mcp-http.sh start

  Scenario: maintainer.sh docs names Living Sky and never secrets
    When maintainer.sh docs runs
    Then it points at TASKBOARD.md, WIPE.md, and the host README
    And it names Living Sky LIV
    And it does not print CURSOR_API_KEY or Tailscale keys
    And it does not reconnect Agent Kanban
