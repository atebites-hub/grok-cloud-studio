Feature: GROW wake session/prompt targets the serve pid that owns ACP listen
  Remaining slice after leftover ACP FAT #103.
  Living Sky LIV-41. Directors stay Grok Build. Extra High grunts are grok-4.6 xhigh fast=false.
  Never Bot CloudAgent. Never vendor Hermes. Never grok --resume.

  Scenario: Leftover daemon.pid is not the ACP listener
    Given a GROW seat whose daemon.pid is a live unrelated process
    And acp.url points at a different process that accepts TCP
    When seat-wake-loop / wake-daemon check serve health
    Then the seat is not healthy
    And argv does not contain grok --resume

  Scenario: Mismatch remints serve then session/prompts that new pid
    Given leftover daemon.pid does not own the ACP listen socket
    And a new inbox.jsonl line for that seat
    When wake-daemon process_once runs
    Then it restarts grok agent serve
    And the new serve receives ACP session/prompt inside that new serve pid
    And the leftover listener does not receive session/prompt
    And argv does not contain grok --resume
