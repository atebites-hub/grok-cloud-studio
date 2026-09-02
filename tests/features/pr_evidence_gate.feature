# MERGE_REQUEST / QA paste evidence gate.
# Executable binding: tests/test_pr_evidence_gate.py
# Empty GitHub leftover-green (MERGEABLE + check_runs=[]) is not a ship-gate.
# A GitHub check named "pytest -q and secret_scan" SUCCESS is not paste.
# Distinct from leftover OPEN #140 CONFLICTING (do not rebase) and LIV-94
# GHA workflow twins. Never remint ship-gate.yml. Never Bot CloudAgent.
# Palemon Linear is Living Sky (LIV), not Black Swan.

Feature: MERGE_REQUEST requires pasted pytest -q + secret_scan
  QA must not squash on empty GitHub leftover-green.
  Extra High RESULT / MERGE_REQUEST body must paste both ship-gate commands.

  Scenario: empty leftover-green is not ship-gate
    Given a GitHub PR that is MERGEABLE with check_runs=[]
    And no pasted pytest -q / secret_scan output
    Then judge does not allow squash
    And the reason is leftover-green
    And MERGE_REQUEST is HOLD

  Scenario: GitHub SUCCESS is not paste
    Given a GitHub PR that is MERGEABLE with a check named "pytest -q and secret_scan" SUCCESS
    And no pasted pytest -q / secret_scan output
    Then judge does not allow squash
    And the reason is missing-paste
    And MERGE_REQUEST is HOLD

  Scenario: pasted N passed and secret_scan=clean is the ship-gate
    Given a GitHub PR that is MERGEABLE
    And the body pastes ".venv/bin/pytest -q" with "372 passed" and "secret_scan=clean"
    Then judge allows squash
    And MERGE_REQUEST is not HOLD

  Scenario: CONFLICTING is not squash even with paste
    Given a GitHub PR that is CONFLICTING or mergeStateStatus=DIRTY
    And the body pastes N passed and secret_scan=clean
    Then judge does not allow squash
    And the reason is conflicting

  Scenario: FLEET_DONE without paste does not ping QA MERGE_REQUEST
    Given an Extra High FINISHED payload whose prUrl is a GitHub PR
    And the payload has no paste evidence
    Then notify_text HOLDs MERGE_REQUEST
    And notify_text does not tell Directors to ping QA MERGE_REQUEST

  Scenario: FLEET_DONE with paste may ping QA MERGE_REQUEST
    Given an Extra High FINISHED payload whose prUrl is a GitHub PR
    And the payload pastes N passed and secret_scan=clean
    Then notify_text includes MERGE_REQUEST
