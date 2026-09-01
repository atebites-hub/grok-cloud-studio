Feature: Hermes mail-as-a-turn on Grok Cloud Studio
  Living Sky LIV-63. Hermes Agent Inbox is one CLI turn. Grok Cloud Studio
  already has that mechanic as grok mind (Bot-equivalent mailbox + pin +
  stay-up), not leftover ACP overlay, and not a vendored hermes-agent tree.

  Do not vendor NousResearch/hermes-agent. Do not land harvest mailbox
  PRs #26 and #28 together. Directors stay Grok Build. Specialists stay
  Cursor Cloud Extra High (grok-4.6 xhigh, fast=false). Never Bot CloudAgent.

  Scenario: An A2A inbox line is one grok --prompt-file turn
    Given an opted-in mind seat with one peer mail line
    When the mind harvests that line
    Then grok is invoked with --prompt-file, grok-4.6, and reasoning-effort xhigh
    And the argv does not include ACP session/prompt
    And the mailbox offset advances after runner exit 0

  Scenario: Opted-in mind seats skip leftover ACP overlay
    Given GCS_MIND_SEATS includes a Director seat
    Then the studio bus skips ACP wake with reason mind-owns-inbox
    And leftover dispatch does not ACP-inject that inbox
    And mind.py never calls acp_inject

  Scenario: Command-center spawn is Extra High, never Bot CloudAgent
    Given the studio-mind command-center tools
    Then cloud_launch wraps scripts/launch-cloud-extra-high.sh
    And Extra High create is grok-4.6 xhigh fast=false
    And Bot CloudAgent is not a launch path

  Scenario: Do not vendor Hermes or land harvest PRs 26 and 28
    Then vendor/hermes-agent is absent
    And mind.py has no envelope, defang, or heartbeat harvest
    And hub message:send stays a receipt COMPLETED, not harvest SUBMITTED
