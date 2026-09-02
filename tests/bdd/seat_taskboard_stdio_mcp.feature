Feature: Seat taskboard stdio MCP factory acceptance
  Isolated GROK_HOME does not inherit ~/.grok/config.toml.
  Seat catalogs live in each seat GROK_HOME/config.toml as
  taskboard --db $GCS_TASKBOARD_DB mcp.
  Cursor ${workspaceFolder} never expands under grok and is not the serve config.
  Two catalogs. Factory mcp-seats write does not remint Linear MCP PRs.
  Living Sky Linear HTTP may already exist in both catalogs from main.
  Linear workspace is Living Sky (LIV). Never Bot CloudAgent (skipSeats).

  Scenario: mcp-seats is the union of launch seats and mind seats minus skipSeats
    Given Palemon-style GCS_ACP_SEATS is a subset of GCS_MIND_SEATS
    Then mcp-seats includes mind-only directors (qa-a, qa-b, audio, narrative)
    And mcp-seats never includes donald or orchestrator

  Scenario: Factory setup writes absolute stdio MCP without starting serve
    When setup.sh runs with GCS_SETUP_SKIP_START=1
    Then each mcp-seat GROK_HOME/config.toml has [mcp_servers.taskboard]
    And args are exactly --db, absolute GCS_TASKBOARD_DB, mcp
    And the installer does not exec grok agent serve

  Scenario: Written command speaks stdio JSON-RPC tools/list
    Given a fake taskboard MCP on TASKBOARD_BIN
    When install_seat_grok_mcp writes GROK_HOME/config.toml
    Then exec of command+args answers initialize and tools/list on stdin/stdout

  Scenario: GROK_HOME catalog has taskboard stdio and no workspaceFolder
    Then config.toml has no ${workspaceFolder}
    And args are taskboard --db <absolute db> mcp
    And [compat.cursor] mcps = false

  Scenario: Cursor catalog is a second catalog, not the grok serve config
    Then .cursor/mcp.json may wrap run-mcp.sh for Cursor CLI
    And that file is not copied into GROK_HOME/config.toml
