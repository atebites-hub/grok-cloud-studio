# Hive beat: fleet-shepherd health vs leftover ACTIVE.
# Executable binding: tests/test_fleet_shepherd.py
# Distinct from GCS #32 leftover skip and GCS #112 TASKBOARD_HEALTH.
# Agent status=ACTIVE is membership until archive; latest runStatus=FINISHED
# is not live RUNNING. Palemon Linear is Living Sky (LIV). Never Bot CloudAgent.

Feature: shepherd taskboard health does not treat leftover ACTIVE as RUNNING
  fleet-shepherd probes tcarac/taskboard health each cycle.
  Leftover Extra High shells stay ACTIVE until archive after the latest
  run is FINISHED. Health OK must not cause those shells to look like
  live RUNNING workers.

  Scenario: healthy board plus leftover ACTIVE+FINISHED
    Given the taskboard DB exists and ticket list succeeds
    And an open fleet.jsonl row with agentStatus=ACTIVE and runStatus=FINISHED
    When fleet-shepherd.py --once runs
    Then it logs TASKBOARD_HEALTH_OK
    And it logs SHEPHERD_SKIP leftover
    And it does not get_agent_run the leftover
    And leftover run_status is not RUNNING

  Scenario: result payload with membership status=ACTIVE is not a live run
    Given an open orphan with no run_status on the ledger
    And result-cloud-agent returns status=ACTIVE without runStatus
    When fleet-shepherd.py --once runs
    Then persisted run_status is not RUNNING
    And persisted run_status is not ACTIVE
    And it does not A2A-ping FLEET_DONE
