# Live GROK_HOME catalog hygiene (distinct from GCS #100 factory mcp-seats).
# Executable binding: tests/test_seat_taskboard_mcp_lint.py
# Isolated GROK_HOME/config.toml is the grok serve catalog:
#   taskboard --db $GCS_TASKBOARD_DB mcp
# Cursor ${workspaceFolder} never expands under grok.
# Do not twin OPEN #100 (setup.sh / mcp-seats factory write).
# Do not clone PAL-45 Linear MCP. Living Sky LIV only. Never Bot CloudAgent.

Feature: doctor WARNs on missing or malformed seat taskboard stdio MCP
  Existing seat GROK_HOME/config.toml files must keep stdio
  `taskboard --db <absolute db> mcp`. Doctor does not remint serve.
  Missing files are not this slice (factory mcp-seats is OPEN #100).

  Scenario: missing taskboard table is a WARN not a FAIL
    Given a seat grok-home/config.toml exists without [mcp_servers.taskboard]
    When doctor.sh runs
    Then it prints WARN and missing-taskboard-table
    And it does not treat that as doctor FAIL

  Scenario: relative db or missing mcp arg is a WARN
    Given a seat catalog whose args are not --db <absolute db> mcp
    When doctor.sh runs
    Then it prints WARN and args-not-db-mcp

  Scenario: healthy absolute stdio catalog is quiet
    Given a seat catalog with absolute command and args --db /abs/db mcp
    When doctor.sh runs
    Then it does not print missing-taskboard-table or args-not-db-mcp
