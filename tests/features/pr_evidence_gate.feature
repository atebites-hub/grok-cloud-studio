Feature: MERGE_REQUEST / QA require pasted pytest -q + secret_scan
  Empty GitHub leftover-green (mergeable_state=clean with check_runs=[])
  is not a ship-gate. MERGEABLE is not a substitute. Directors must not
  ping QA MERGE_REQUEST, and QA must not squash-merge, unless the
  MERGE_REQUEST / Extra High result pastes `.venv/bin/pytest -q`
  (`N passed`, N>=1) AND `python3 scripts/secret_scan.py`
  (`secret_scan=clean`).

  Distinct from leftover LIV-94 #105/#88/#92 (do not rebase those).
  Distinct from GitHub Actions workflow twins #117/#118 / beat1740.
  Main already has scripts/ci/ship-gate.sh; this gate is paste
  evidence for MERGE_REQUEST / QA, not a second workflow file.

  Never Bot CloudAgent. Never vendor Hermes. Never merge GCS #26+#28.
  Palemon Linear is Living Sky (LIV), never Black Swan.
  Do not squash-merge CONFLICTING PRs.

  Scenario: MERGEABLE with empty check_runs is leftover-green, not evidence
    Given a GitHub pull request with mergeable_state=clean
    And the head commit has check_runs=[]
    And combined commit statuses total_count=0
    And no pasted pytest -q / secret_scan output
    Then that snapshot is not ship-gate evidence
    And FLEET_DONE must not ping QA MERGE_REQUEST

  Scenario: a successful GitHub check name is not a substitute for paste
    Given a pull request whose head has a completed success check
    named "pytest -q and secret_scan"
    And the Extra High result / MERGE_REQUEST body has no pasted
    "N passed" and no "secret_scan=clean"
    Then that snapshot is still not MERGE_REQUEST evidence
    And FLEET_DONE must HOLD (this beat is paste, not leftover CI-name)

  Scenario: pasted pytest -q + secret_scan is MERGE_REQUEST evidence
    Given Extra High finished with a GitHub prUrl
    And the result (or MERGE_REQUEST body) pastes
      12 passed in 1.23s
      secret_scan=clean
    Then that snapshot is ship-gate evidence
    And FLEET_DONE may ping QA MERGE_REQUEST with that paste

  Scenario: QA must not squash CONFLICTING or empty leftover-green
    Given MERGE_REQUEST for an odd or even PR
    When GitHub mergeable_state is conflicting or dirty
    Then QA must not squash-merge
    When checks are empty leftover-green
    Then QA must skip until paste exists
