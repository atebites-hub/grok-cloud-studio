Feature: LIV-94 empty GitHub checks are not ship-gate evidence
  GitHub mergeable_state=clean (MERGEABLE) with check_runs=[] is not
  proof that pytest -q and secret_scan ran. GCS #41, #47, and #27
  showed that shape. GCS #92 SUCCESS is the required GitHub Actions
  job named pytest -q and secret_scan (scripts/ci/ship-gate.sh,
  fetch-depth 0) running .venv/bin/pytest -q AND
  python3 scripts/secret_scan.py. This PR adds that gate. Do not remint
  runStatus list PRs. Empty checks are a HOLD, not MERGE_REQUEST.

  Never Bot CloudAgent. Never print keys.

  Scenario: MERGEABLE with empty check_runs is not evidence
    Given a GitHub pull request with mergeable_state=clean
    And the head commit has check_runs total_count=0
    And combined commit statuses total_count=0
    Then that snapshot is not ship-gate evidence
    And FLEET_DONE must not ping QA MERGE_REQUEST

  Scenario: the ship-gate example those MERGEABLE PRs need
    Given GCS #92 SUCCESS added .github/workflows/ship-gate.yml
    And that job ran pytest -q and secret_scan on pull_request
    Then this change adds that same gate (not leftover-green override-ini)
    And the example remains pytest -q AND python3 scripts/secret_scan.py
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
