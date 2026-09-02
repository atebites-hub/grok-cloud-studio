Feature: unique remaining — empty GitHub checks are not merge evidence
  Unique GitHub Actions ship-gate (pytest -q AND secret_scan) is already
  on origin/main (.github/workflows/ship-gate.yml). This change does not
  remint that workflow. The unique remaining gap: empty GitHub checks
  (check_runs=[]) are not merge evidence. MERGEABLE+empty CI is
  leftover-green theatre. The required check is named
  "pytest -q and secret_scan" (scripts/ci/ship-gate.sh). Directors
  collect / waiter FLEET_DONE HOLD, not QA MERGE_REQUEST. Canonical
  commands remain `.venv/bin/pytest -q` AND `python3 scripts/secret_scan.py`.

  Do not vendor Hermes. Do not merge GCS #26+#28. Never Bot CloudAgent.
  Never print keys.

  Scenario: MERGEABLE with empty check_runs is leftover-green theatre
    Given a GitHub pull request with mergeable_state=clean
    And the head commit has check_runs total_count=0
    And combined commit statuses total_count=0
    Then that snapshot is not ship-gate evidence
    And FLEET_DONE must not ping QA MERGE_REQUEST
    And directors re-collect after the required check is SUCCESS

  Scenario: unique ship-gate already on main is not reminted
    Given origin/main already has .github/workflows/ship-gate.yml
    And that job ran pytest -q and secret_scan on pull_request
    Then this change does not add a second ship-gate YAML
    And the required check remains pytest -q AND python3 scripts/secret_scan.py
    on pull_request for atebites-hub/grok-cloud-studio

  Scenario: a successful ship-gate check is evidence
    Given a pull request whose head has a completed success check
    named "pytest -q and secret_scan"
    Then that snapshot is ship-gate evidence
    And FLEET_DONE may ping QA MERGE_REQUEST

  Scenario: Director collect JSON is the remaining evidence path
    Given Extra High finished with a GitHub prUrl
    And GitHub check_runs=[] (MERGEABLE is not a substitute)
    When a Director runs scripts/cloud/result-cloud-agent.sh
    Then the JSON includes emptyChecks and shipGateOk
    And emptyChecks=true is not MERGE_REQUEST evidence
    And collect.ts attaches the same flags (not only the waiter ping)
