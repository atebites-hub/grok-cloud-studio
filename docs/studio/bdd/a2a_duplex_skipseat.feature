Feature: Duplex RESULT notify must not 404 skipSeats (donald)
  Living Sky A2A duplex skipSeat notify (not LIV-85 hub-ack clone).
  Studio Linear is Living Sky (linear.app/livingsky, team LIV). Never Black Swan.
  Extra High stays grok-4.6 xhigh fast=false. Never Bot CloudAgent.
  Never vendor Hermes. donald/orchestrator stay skipSeats — not ACP inject targets.

  Hub TASK_STATE_COMPLETED / send.sh ACK is a protocol receipt only.
  Director RESULT is a separate duplex write onto the working seat's A2A task.
  A2A_REPLY is an optional caller ping — it must not 404, and a missed ping
  must not fail the task reply.

  Scenario: donald caller remaps to a hub card seat
    Given a Director RESULT whose inbox caller is skipSeat donald
    When duplex notifies A2A_REPLY
    Then the ping goes to floor-ops if that Agent Card exists
    And otherwise to orchestrator if that Agent Card exists
    And send.sh is never pointed at donald (no hub 404 unknown seat)

  Scenario: skip notify without failing the task reply
    Given donald has no floor-ops or orchestrator Agent Card to receive the ping
    Or the notify send returns false
    When duplex harvests RESULT bc-id= pr= a2a= notes=
    Then write_task_reply still stores director-result on the working seat
    And duplex ok remains true (notify skipped, not a failed task reply)
    And Hub TASK_STATE_COMPLETED stays a receipt, not Director RESULT

  Scenario: skipSeats stay skipSeats
    Then donald and orchestrator remain registry skipSeats
    And they are not launch-seats or ACP inject targets
    And A2A_REPLY never launches Bot CloudAgent
