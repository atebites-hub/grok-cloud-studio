Feature: Leftover ACP GROW wake delivers mail as session/prompt
  Living Sky leftover host OS on grok-cloud-studio.
  Directors stay Grok Build. Extra High grunts are grok-4.6 xhigh fast=false.
  Never Bot CloudAgent. Never vendor Hermes. Never grok --resume.

  Scenario: Inbox growth prompts the live serve pid
    Given a GROW seat with a live grok agent serve and pinned acp.session
    And a new inbox.jsonl line for that seat
    When seat-wake-loop / wake-daemon process the inbox
    Then the serve receives ACP session/prompt inside that same serve pid
    And argv does not contain grok --resume
    And acp.session is unchanged
    And wake.offset advances

  Scenario: Serve restart never falls back to grok --resume
    Given the seat serve is down
    When wake processes an inbox line
    Then it restarts grok agent serve
    And it ACP session/prompts that new serve pid
    And argv does not contain grok --resume
