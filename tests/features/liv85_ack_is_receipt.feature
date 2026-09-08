Feature: Hub ACK is a receipt; STATUS ACK must not clobber an in-flight TASK
  Living Sky LIV-85 evidence gate on atebites-hub/grok-cloud-studio.
  Unique remaining vs origin/main: GCS #27 MERGED already queues mail
  (TASK_STATE_SUBMITTED until harvest) and keeps bot-bridge default off.
  This slice does not remint that enqueue. It does not remint CLOSED
  unmerged GCS #81 / #83 (sole-writer mail.in-flight, COMPLETE-on-send).

  Hub TASK_STATE_COMPLETED / send.sh ACK is a protocol receipt, not a
  mind turn. STATUS ACK must not overwrite an in-flight Donald TASK in
  mind/mail.txt until grok exits 0. Offset / MIND_TURN only after runner
  exit 0. Empty GitHub CI is not merge evidence. Isolated ship-gate is
  `.venv/bin/pytest -q` AND `python3 scripts/secret_scan.py`.

  Extra High stays grok-4.6 xhigh fast=false. Never Bot CloudAgent.
  Do not vendor NousResearch/hermes-agent. Never palemon #165/#167.

  Scenario: send.sh ACK is a receipt, not mind-turn done
    Given the local A2A hub
    When send.sh enqueues a peer mail line
    Then stdout is A2A_SEND_OK with TASK_STATE_SUBMITTED and kind=receipt
    And TASK_STATE_COMPLETED is not the enqueue ack
    And mind/offset stays 0 and mind/mail.txt is not a MIND_TURN
    And the hub receipt note says ACK is a receipt, not mind-turn done

  Scenario: STATUS ACK must not overwrite an in-flight Donald TASK
    Given floor-ops mind/mail.txt holds a Donald TASK and grok is in-flight
    When a later STATUS ACK writer and a nested process_once run
    Then mind/mail.txt still contains the TASK until grok exits 0
    And nested harvest returns reason=in-flight without advancing offset
    And grok --prompt-file still holds the TASK at start and before exit 0
    And --model is grok-4.6 with --reasoning-effort xhigh

  Scenario: Do not remint CLOSED #81/#83 or Palemon leftovers
    Then hub message:send stays TASK_STATE_SUBMITTED (GCS #27)
    And this FAT does not restore COMPLETE-on-enqueue from GCS #83
    And this FAT does not remint GCS #81 sole-writer mail.in-flight
    And NousResearch/hermes-agent is not vendored
    And Extra High is grok-4.6 xhigh fast=false
    And palemon #165/#167 are not this remaining
