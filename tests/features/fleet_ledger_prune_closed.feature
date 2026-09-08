# Hive fleet ledger: prune closed terminal leftovers so shepherd does not page them as live.
# Executable binding: tests/test_fleet_shepherd.py + tests/test_fleet_ledger.py
# Distinct from GCS #32 leftover ACTIVE+FINISHED skip (open shells stay).
# Distinct from GCS #34 / gcs-fleet-dedupe-notify-floor1747 leftover (notify idempotent).
# Distinct from leftover occupancy GCS #125/#132/#154. Never Bot CloudAgent.
# Palemon Linear is Living Sky (LIV). Never Emerald. Never palemon leftover #165/#167.

Feature: prune closed leftover fleet.jsonl rows so shepherd does not page them as live
  Closed leftover: notified, status=closed, latest run FINISHED or CANCELLED
  (ERROR/EXPIRED also terminal; US CANCELED maps to CANCELLED).
  Open leftover shells stay. RUNNING stays. Ledger-only: no Cloud cancel,
  no get_agent_run, no A2A ping.

  Scenario: shepherd cycle drops closed FINISHED leftover
    Given a notified closed fleet.jsonl row whose latest run is FINISHED
    When fleet-shepherd.py runs one cycle
    Then that row is gone from fleet.jsonl
    And shepherd did not get_agent_run that bc-id
    And shepherd did not A2A-ping

  Scenario: shepherd cycle drops closed CANCELLED leftover
    Given a notified closed fleet.jsonl row whose latest run is CANCELLED
    When fleet-shepherd.py runs one cycle
    Then that row is gone from fleet.jsonl
    And shepherd did not cancel a Cloud agent

  Scenario: a live RUNNING row is kept
    Given an open fleet.jsonl row whose latest run is RUNNING
    When fleet-shepherd.py runs one cycle
    Then fleet.jsonl still names that RUNNING row
    And shepherd did not cancel that agent

  Scenario: open leftover shell stays
    Given an open fleet.jsonl row whose latest run is FINISHED
    When fleet-shepherd.py runs one cycle
    Then fleet.jsonl still stores that open leftover shell
