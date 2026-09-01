# LIV-67. Executable binding: tests/test_liv67_list_prints_runstatus.py
# Palemon Linear is Living Sky (linear.app/livingsky, team Livingsky / LIV).
# NEVER Black Swan. Never Bot CloudAgent. Extra High stays grok-4.6 xhigh, fast=false.
# Distinct from leftover OPEN list twins #29/#44/#50/#55/#60/#68/#69.

Feature: list prints latest-run runStatus (LIV-67)
  Cloud Agents API v1 keeps agent status ACTIVE until archive.
  Execution state lives on the latest run (RUNNING vs FINISHED).
  Existence is not liveness. Leftover ACTIVE+FINISHED shells must not
  look like spinning workers.

  Scenario: Leftover ACTIVE+FINISHED is not a live worker
    Given a leftover agent status=ACTIVE with latest run FINISHED
    And a live agent status=ACTIVE with latest run RUNNING
    When scripts/cloud/list.sh and list-cloud-agents.sh print rows
    Then the leftover row includes status=ACTIVE and runStatus=FINISHED
    And the live row includes status=ACTIVE and runStatus=RUNNING
    And neither row is TSV membership-only (no runStatus token)

  Scenario: Missing latest run prints runStatus=none
    Given an ACTIVE agent whose latestRunId GET returns 404
    When list.sh prints that row
    Then the row includes runStatus=none
    And list still exits 0

  Scenario: SDK list.ts writes runStatus on each row
    Given scripts/cloud/sdk/list.ts
    Then the source emits runStatus= via mapRunStatus / listRuns
    And it does not remint list --repo, --running, MUST_LAUNCH, or MCP cloud_list
