Feature: LIV-41 director own-grunt spawn and watch
  A director-owns-launch turn without spawning/watching its own Cursor Cloud
  grunt via scripts/launch-cloud-extra-high.sh is FAIL (reason=no-spawn-watch).
  Empty GitHub checks are not merge. Unique --name. Refuse twin of RUNNING
  gcs-liv59-anti-twin-floor2105. Extra High stays grok-4.6 xhigh fast=false.

  Scenario: STATUS-only on a Director-owns-launch wake is FAIL
    Given a leftover ACP or mind turn whose mail is Director-owns-launch
    When the actor prints STATUS (or send.sh / ticket move) and never invokes
      scripts/launch-cloud-extra-high.sh or cloud_launch
    Then the turn is FAIL with reason=no-spawn-watch
    And leftover ACP does not print ACP_INJECT_OK
    And mind does not advance inbox offset

  Scenario: Inspect of the launcher is theatre, not a spawn
    Given a Director-owns-launch mail
    When the this-prompt argv is ls/cat/rg of launch-cloud-extra-high.sh
    Then the turn is FAIL with reason=no-spawn-watch

  Scenario: Real launcher with unique --name spawns and watches
    Given a Director-owns-launch mail
    When this prompt invokes scripts/launch-cloud-extra-high.sh
      --name gcs-liv41-own-grunt-floor2105 and the waiter is not skipped
    Then the turn is not FAIL
    And the name is not a twin of RUNNING gcs-liv59-anti-twin-floor2105

  Scenario: Twin of RUNNING gcs-liv59-anti-twin-floor2105 is refused
    Given a Director-owns-launch mail
    When this prompt invokes the launcher with --name gcs-liv59-anti-twin-floor2105
    Then the turn is FAIL with reason=no-spawn-watch
    And detail=twin

  Scenario: Spawn with GCS_SPAWN_WAITER=0 is not watching
    Given a Director-owns-launch mail
    When this prompt invokes the launcher with GCS_SPAWN_WAITER=0
      or the transcript contains CLOUD_WAITER_SKIPPED
    Then the turn is FAIL with reason=no-spawn-watch
    And detail=missing-watch

  Scenario: A2A_REPLY and FLEET_DONE are exempt
    Given mail that is A2A_REPLY or FLEET_DONE or PR_READY
    When the actor does not launch
    Then the turn is not FAIL

  Scenario: Empty CI is not merge
    Given this pull request
    Then .github/workflows/ship-gate.yml must exist
    And scripts/ci/ship-gate.sh must require pytest N passed and secret_scan=clean
