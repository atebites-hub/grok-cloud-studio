Feature: wait-notify FLEET_DONE uses latest runStatus
  Wait-notify must GET the agent's latest runStatus before A2A-pinging
  FLEET_DONE. A leftover FINISHED run is not done while a newer run is
  CREATING or RUNNING.

  Distinct from occupancy #132 (bounded listRuns capacity counts) and
  from paginated-catalog beat1849. Do not clone LIV-67 list printers,
  LIV-41 directors-spawn, or LIV-85 mail harvest. Never Bot CloudAgent.
  Empty GitHub CI leftover-green is not a ship gate.

  Scenario: leftover FINISHED while a newer run is RUNNING
    Given Extra High bc-wait has leftover run run-leftover runStatus=FINISHED
    And GET /v1/agents/bc-wait still reports latestRunId=run-leftover
    And a newer run run-new is RUNNING
    And wait-notify is invoked with --id bc-wait --run run-leftover
    When the waiter GETs runStatus
    Then it must GET /v1/agents/bc-wait/runs (the collection, latest by createdAt)
    And it must not A2A-ping FLEET_DONE for leftover FINISHED

  Scenario: leftover FINISHED while a newer run is CREATING
    Given the same leftover FINISHED shell
    And a newer run is CREATING
    Then wait-notify must keep polling the latest run
    And must not print CLOUD_WAITER_DONE runStatus=FINISHED

  Scenario: latest run itself is terminal
    Given leftover FINISHED and a newer run that is also FINISHED
    Then wait-notify may FLEET_DONE for the latest run, not the leftover id
