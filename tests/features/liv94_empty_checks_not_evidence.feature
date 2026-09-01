Feature: LIV-94 empty GitHub checks are not ship-gate evidence
  GitHub mergeable_state=clean (MERGEABLE) with check_runs=[] is not
  proof that pytest -q and secret_scan ran. GCS #41, #47, and #27
  showed that shape. GCS #62 already added the Actions workflow that
  those MERGEABLE PRs need; do not remint it.

  The example those PRs need is a pull_request workflow on
  atebites-hub/grok-cloud-studio that runs .venv/bin/pytest -q AND
  python3 scripts/secret_scan.py. Until that check is on the PR head
  (or on main after #62 lands and they rebase), empty checks are a
  HOLD, not MERGE_REQUEST.

  Never Bot CloudAgent. Never print keys.

  Scenario: MERGEABLE with empty check_runs is not evidence
    Given a GitHub pull request with mergeable_state=clean
    And the head commit has check_runs total_count=0
    And combined commit statuses total_count=0
    Then that snapshot is not ship-gate evidence
    And FLEET_DONE must not ping QA MERGE_REQUEST

  Scenario: the ship-gate example those MERGEABLE PRs need
    Given GCS #62 already added .github/workflows/ship-gate.yml
    And that job ran pytest -q and secret_scan on pull_request
    Then this change must not clone that workflow
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
