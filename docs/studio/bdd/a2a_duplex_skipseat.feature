Feature: Duplex RESULT notify must not 404 skipSeat donald
  Living Sky A2A duplex skipSeat notify. Distinct from leftover GCS #133/#99
  (do not rebase those). Not a LIV-85 / LIV-67 / LIV-41 clone.
  Studio Linear is Living Sky (linear.app/livingsky, team LIV). Never Black Swan.
  Extra High stays grok-4.6 xhigh fast=false. Never Bot CloudAgent.
  Never vendor Hermes. donald/orchestrator stay skipSeats — not ACP inject targets.

  Hub enqueue is TASK_STATE_SUBMITTED until mind harvests (LIV-85 receipt).
  Director RESULT is a separate duplex write onto the working seat's A2A task.
  A2A_REPLY must succeed after that RESULT. A missed ping must not fail the
  task reply. send.sh donald may 404; duplex must not point A2A_REPLY at donald.

  Scenario: donald caller remaps to a hub card seat
    Given a Director RESULT whose inbox caller is skipSeat donald
    When duplex notifies A2A_REPLY
    Then the ping goes to floor-ops if that Agent Card exists
    And otherwise to orchestrator if that Agent Card exists
    And send.sh is never pointed at donald (no hub 404 unknown seat)
    And A2A_REPLY succeeds (notified true) when a fallback card exists

  Scenario: skip notify without failing the task reply
    Given donald has no floor-ops or orchestrator Agent Card to receive the ping
    Or the notify send returns false
    When duplex harvests RESULT bc-id= pr= a2a= notes=
    Then write_task_reply still stores director-result on the working seat
    And duplex ok remains true (notify skipped, not a failed task reply)
    And Hub TASK_STATE_SUBMITTED / later TASK_STATE_COMPLETED stay receipts,
      not Director RESULT

  Scenario: skipSeats stay skipSeats
    Then donald and orchestrator remain registry skipSeats
    And they are not launch-seats or ACP inject targets
    And A2A_REPLY never launches Bot CloudAgent
    And docs/a2a/cards/donald.json stays unshipped
