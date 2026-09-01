Feature: Grok-bot-like mind plugins (ticket/A2A/cloud) without Hermes (LIV-63 remaining)
  Living Sky LIV-63 remaining after #47 (command-center Extra High tools)
  and #90 (grok plugin.json install of ticket/A2A/cloud). This slice is the
  remaining Hermes-port mechanic: grok-bot-like plugins must handshake after
  `grok plugin install --trust` copies them off the repo tree, using
  GROK_HOME/gcs-root — not Hermes plugin.yaml, not a vendored hermes-agent.

  Grok Build minds get grok-bot-like plugins for ticket, A2A, and cloud —
  grok `plugin.json` MCP. Do not vendor NousResearch/hermes-agent.

  Mail-is-a-turn stays grok mailbox + pin + stay-up (`grok --prompt-file`,
  grok-4.6 xhigh). Not ACP `session/prompt` overlay. Do not land harvest
  mailbox PRs #26 and #28 (envelope, defang, heartbeat). Do not restack
  #47 `cloud_list` / `cloud_followup` into mind.py. Never Bot CloudAgent.
  skipSeats orchestrator/donald stay skipped. Empty CI is not ship-gate
  evidence. Demonstrate, don't theatre.

  Scenario: Mind GROK_HOME installs ticket, A2A, and cloud grok plugins
    Given an opted-in mind seat
    When seat-mind-loop installs grok plugins into GROK_HOME
    Then plugins/studio-mind, plugins/a2a, and plugins/cursor-cloud are
      `grok plugin install --trust` targets
    And each plugin has grok plugin.json (not Hermes plugin.yaml)
    And ticket, a2a_send / a2a_list_seats, and cloud_launch are available

  Scenario: A2A and cloud plugins honor GCS_ROOT when copied into GROK_HOME
    Given plugins/a2a and plugins/cursor-cloud copied off the repo tree
    When the stdio server starts with GCS_ROOT pointing at the kit
    Then tools/list still returns the A2A and cloud planes

  Scenario: Off-tree copies handshake from gcs-root stamp without GCS_ROOT
    Given grok plugin install copied studio-mind, a2a, and cursor-cloud
      into GROK_HOME
    And GROK_HOME/gcs-root points at the kit
    And GCS_ROOT is unset
    When initialize then notifications/initialized then tools/list run
      on the same stdio pid
    Then the process stays open
    And python3 -u is the mcp.json argv

  Scenario: Copying a Hermes tree into the repo fails the ship gate
    Given a vendored hermes-agent tree (plugin.yaml, message_agent.py)
    Then the Hermes-tree scan fails
    And a clean Grok Cloud Studio tree has no such hits

  Scenario: Mail-is-a-turn stays grok mailbox, not ACP overlay
    Given the grok mind harvest path
    Then one inbox line is grok --prompt-file on a pinned session
    And mind.py does not contain session/prompt or acp_inject
    And harvest envelope helpers from #26/#28 are absent
