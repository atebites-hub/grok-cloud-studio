Feature: Host ticker enqueues ACP_PING STATUS/CONTINUE work turns
  Living Sky leftover host OS on grok-cloud-studio.
  Palemon Linear is Living Sky (linear.app/livingsky, team LIV). Never Black Swan.
  Extra High stays grok-4.6 xhigh fast=false. Never Bot CloudAgent.
  host-ticker.py does not start bot-bridge.

  Distinct from LIV-85 hub COMPLETE is a receipt
  (PRs #61 / #67 / #83 / #106). This FAT does not clone mail.txt
  SUBMITTED/COMPLETE or hub TASK_STATE_COMPLETED as mind-turn done.

  Scenario: host-ticker.py --once enqueues a work turn
    Given GROW seats floor and ops
    When host-ticker.py --once --seats floor,ops runs
    Then each seat inbox.jsonl gains one ACP_PING STATUS/CONTINUE line
    And the JSON kind is message, never launch
    And the text allows tools (taskboard ticket move, send.sh, launch-cloud-extra-high.sh)
    And the text is not a RESULT-only hang-up and not a PONG keep-alive
    And the ping body says RESULT-only / PONG is a bug
    And bot-bridge.pid is not created

  Scenario: host-clock-ticker.sh enqueue_continue is the same work turn
    When host-clock-ticker.sh enqueue_continue floor runs
    Then floor inbox.jsonl is ACP_PING STATUS/CONTINUE with tools allowed
    And kind is never launch
    And the body is not PONG and not RESULT-only

  Scenario: Ticker is not hub COMPLETE and not Bot CloudAgent
    When the host ticker enqueues a keep-alive
    Then the line is not TASK_STATE_COMPLETED / send.sh ACK
    And directors do not launch Grok Bot as a CloudAgent
    And Extra High create stays grok-4.6 effort=xhigh fast=false
