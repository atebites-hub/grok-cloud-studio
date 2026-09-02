Feature: Grok-bot-like mind plugins (ticket/A2A/cloud) without Hermes (LIV-63 remaining)
  Living Sky LIV-63 remaining vs origin/main after #47 OPEN CONFLICTING DIRTY
  (do not merge it) and unique LIV-63 #76 on main (mailbox disk turn + Extra
  High spawn PATH + ticker). Grok Build minds get grok-bot-like plugins for
  ticket, A2A, and cloud — grok `plugin.json` MCP. Do not vendor
  NousResearch/hermes-agent. Not Hermes `plugin.yaml`.

  Mail-is-a-turn stays grok mailbox + pin + stay-up (`grok --prompt-file`,
  grok-4.6 xhigh). Not ACP `session/prompt` overlay. Do not land harvest
  mailbox PRs #26 and #28 (envelope, defang, heartbeat). Do not restack
  #47 `cloud_list` / `cloud_followup` into mind.py. Extra High `cloud_list`
  stays on the cursor-cloud MCP plane already on main. Never Bot CloudAgent.
  Demonstrate, don't theatre.

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

  Scenario: Copying a Hermes tree into the repo fails the ship gate
    Given a vendored hermes-agent tree (plugin.yaml, message_agent.py)
    Then the Hermes-tree scan fails
    And a clean Grok Cloud Studio tree has no such hits

  Scenario: Mail-is-a-turn stays grok mailbox, not ACP overlay
    Given the grok mind harvest path
    Then one inbox line is grok --prompt-file on a pinned session
    And mind.py does not contain session/prompt or acp_inject
    And harvest envelope helpers from #26/#28 are absent
