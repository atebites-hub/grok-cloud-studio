# LIV-73. Executable binding: tests/test_liv73_failing_then_passing.py
# BDD in Action: demonstrate failing-then-passing, not leftover-green theatre.
# Palemon Linear is Living Sky LIV. NEVER Black Swan. Never Bot CloudAgent.

Feature: failing-then-passing evidence (LIV-73)
  Directors paste RED then GREEN on the same mock fleet.
  The main-era list formatter prints TSV membership (id, status, name, url,
  latestRunId) with no runStatus token. After LIV-67, list.sh prints
  runStatus=FINISHED vs runStatus=RUNNING.

  Scenario: RED — main-era TSV has no runStatus token
    Given leftover ACTIVE+FINISHED and live ACTIVE+RUNNING
    When the main-era TSV formatter prints rows
    Then leftover is ACTIVE with no runStatus= token
    And live is ACTIVE with no runStatus= token

  Scenario: GREEN — the same fleet prints runStatus after the fix
    Given the same mock leftover and live agents
    When scripts/cloud/list.sh runs against the mock API
    Then leftover prints runStatus=FINISHED
    And live prints runStatus=RUNNING
    And GET /v1/agents/{id}/runs/{latestRunId} is used (not agent status alone)
