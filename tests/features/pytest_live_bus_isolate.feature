Feature: Isolated pytest must not hit the live Palemon bus
  Directors leak GCS_ACP_SEATS, GCS_MIND_SEATS, GCS_A2A_STATE,
  GCS_A2A_REGISTRY, and GCS_TASKBOARD_DB into pytest. The live studio
  hub holds :8732. Isolated pytest must unset those knobs unless a test
  opts into a temp state dir, and the suite must fail if it binds the
  live hub port. Do not start the live bus from tests. Do not bounce
  leftover dispatch. Living Sky only. Never Bot CloudAgent.

  Scenario: A live-looking parent env is stripped before tests run
    Given the parent process exported GCS_A2A_STATE to the live Palemon state dir
    And GCS_TASKBOARD_DB points at the live taskboard SQLite file
    When pytest loads the required gcs_pytest_isolate plugin
    Then those leak variables are unset in the test process
    And a test must opt into gcs_temp_state to receive a temporary state dir

  Scenario: Live-looking env cannot open the real Palemon hub or taskboard
    Given a live-looking env pointing at the Palemon state dir and port 8732
    When a test would launch hub.py or start-taskboard.sh
    Then the isolate plugin refuses the launch
    And the suite fails if a test binds 127.0.0.1:8732

  Scenario: Ship-gate and doctor require the isolation plugin
    Given pytest.ini registers -p gcs_pytest_isolate
    And tests/conftest.py loads the same plugin
    When ship-gate.sh runs
    Then it unsets the leak variables before .venv/bin/pytest -q
    And doctor.sh fails closed if that wiring is missing
