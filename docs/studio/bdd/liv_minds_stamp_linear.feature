# Living Sky Linear — Grok Build minds stamp themselves
# LIV-82 / LIV-43. Palemon Linear is Living Sky (linear.app/livingsky, team
# Livingsky / LIV). NEVER Black Swan. Never Bot CloudAgent.
# Extra High stays grok-4.6 xhigh, fast=false.
#
# This is the BDD example (BDD in Action): Linear MCP on Grok Build AND
# Cursor Cloud. Minds stamp LIV-* themselves. Do not have Donald DIY Linear.

Feature: Grok Build minds stamp Living Sky Linear themselves
  Studio Linear is Living Sky (linear.app/livingsky, team Livingsky / LIV).
  NEVER Black Swan Money.
  Linear MCP lives on Grok Build (GROK_HOME/config.toml) AND Cursor Cloud
  (.cursor/mcp.json). Two catalogs. Never fake a transfer.
  Grok Bot skipSeats (Donald / orchestrator) are not mind seats and do not
  DIY Linear.

  Scenario: Grok Build mind has Linear MCP in GROK_HOME
    Given a Grok Build mind seat that is not skipSeats
    When seat start writes that seat's isolated GROK_HOME/config.toml
    Then [mcp_servers.linear] is HTTP https://mcp.linear.app/mcp
    And Authorization is Bearer ${LINEAR_API_KEY} (env ref, never a literal)
    And [mcp_servers.taskboard] stdio remains next to it
    And [compat.cursor] mcps = false so grok does not load .cursor/mcp.json

  Scenario: Cursor Cloud Extra High has Linear MCP in checkout mcp.json
    Given Cursor Cloud Extra High cannot scrape GROK_HOME
    When a specialist boots from the cloud-env snapshot
    Then .cursor/mcp.json mcpServers is exactly {taskboard, linear}
    And Linear is HTTP https://mcp.linear.app/mcp with Bearer ${LINEAR_API_KEY}
    And the Grok catalog (Higgsfield, studio-mind, GROK_HOME dump) is not copied

  Scenario: A mind turn stamps Living Sky itself
    Given common_footer.txt and every named SOUL.md
    When a Grok Build mind completes a turn
    Then it MUST stamp a Living Sky Linear issue (LIV-*) itself
    And it uses Linear MCP save_comment / save_issue (not send.sh donald)
    And RESULT includes liv=<LIV-* identifier>
    And it never files, comments, or stamps Black Swan Money

  Scenario: Donald does not DIY Linear
    Given Donald and orchestrator are Grok Bot skipSeats
    Then GCS_MIND_SEATS never includes donald or orchestrator
    And process_once on donald consumes nothing (reason=skipSeats)
    And the footer forbids having Donald DIY Linear
    And floor-ops (Grok Build Donald-clone, a mind seat) still stamps itself

  Scenario: Never Bot CloudAgent, pin grok-4.6 xhigh
    Given Extra High create and mind argv
    Then model is grok-4.6 with reasoning-effort xhigh and fast=false
    And Grok Bot is never launched as a CloudAgent
