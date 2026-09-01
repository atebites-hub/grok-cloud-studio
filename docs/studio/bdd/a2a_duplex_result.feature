Feature: A2A director RESULT is duplex, not success
  Living Sky A2A duplex RESULT FAT (not LIV-85 hub-ack).
  Studio Linear is Living Sky (linear.app/livingsky, team LIV). Never Black Swan.
  Extra High stays grok-4.6 xhigh fast=false. Never Bot CloudAgent.

  Hub TASK_STATE_COMPLETED / send.sh ACK is a protocol receipt (LIV-85).
  This FAT does not clone that mechanic. Director RESULT is a separate duplex
  write onto the A2A task plus an optional caller ping.

  Scenario: Directors print the canonical RESULT line
    When a Director prints a RESULT
    Then the line is exactly
      RESULT bc-id=<id or none> pr=<url or none> a2a=<task-id or none> notes=<one line>
    And common_footer.txt, MIND wrap, and A2A docs carry that format

  Scenario: RESULT is duplex, not success
    Given a mind or leftover inject turn that did real work
    When the Director prints RESULT bc-id= pr= a2a= notes=
    Then duplex writes that line onto the A2A task and may ping the caller
    And turn success is STATUS / this-prompt work / runner exit 0
    And RESULT is not ACP_INJECT_OK and not MIND_TURN proof by itself

  Scenario: RESULT-only / PONG is a bug
    Given a keep-alive or wake turn
    When the actor prints only RESULT or only PONG
    Then pin-session treat that as hangup-only, not HANDOFF
    And docs and the seat footer say RESULT-only / PONG is a bug
    And duplex does not treat PONG as a RESULT line
    And hub ACK / TASK_STATE_COMPLETED is not a Director RESULT

  Scenario: A2A_REPLY never launches Bot CloudAgent
    Given an A2A_REPLY duplex caller ping
    Then dispatch and wake do not create a Cursor Cloud agent
    And directors do not launch Grok Bot as a CloudAgent
    And Extra High create stays grok-4.6 effort=xhigh fast=false
