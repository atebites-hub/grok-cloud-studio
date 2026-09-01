# Hive stale membership: Extra High waiter_pid in fleet.jsonl is not liveness.
# Executable binding: tests/test_stale_waiter_pid.py
# Distinct from GCS #77/#36 (bot-bridge.pid tombstone — do not touch bot-bridge.py).
# Distinct from GCS #32 (shepherd leftover ACTIVE+FINISHED skip).
# Palemon Linear is Living Sky (LIV), not Black Swan. Never Bot CloudAgent.

Feature: stale Extra High waiter_pid is not liveness
  Existence of waiter_pid in fleet.jsonl does not mean the waiter is running.
  An in-memory pid_alive / is_orphan check is not eviction.
  Eviction must be durable on the ledger so a reused pid cannot look live,
  and fleet-shepherd can orphan-notify once.

  Scenario: a dead waiter_pid is not a live waiter
    Given an open fleet.jsonl row whose waiter_pid names a process that is not running
    Then waiter_alive is false
    And the row is an orphan

  Scenario: in-memory orphan is not eviction
    Given an open fleet.jsonl row whose waiter_pid names a dead process
    When is_orphan is true in memory
    Then fleet.jsonl still stores that waiter_pid

  Scenario: sweep evicts the dead waiter_pid durably
    Given an open fleet.jsonl row whose waiter_pid names a dead process
    When sweep_stale_waiters runs
    Then fleet.jsonl waiter_pid is null
    And waiter_tombstone is true
    And waiter_pid_evicted names the dead pid

  Scenario: a live waiter_pid is kept
    Given an open fleet.jsonl row whose waiter_pid is this process
    When sweep_stale_waiters runs
    Then fleet.jsonl still names that live pid
    And the row is not an orphan

  Scenario: durable eviction survives pid reuse
    Given a row whose dead waiter_pid was evicted
    When pid_alive would return true for the old pid number
    Then waiter_alive is still false
    And the row is still an orphan

  Scenario: shepherd evicts a dead waiter_pid even when the probe is empty
    Given an open fleet.jsonl row whose waiter_pid names a dead process
    When fleet-shepherd.py --once runs and result-cloud-agent is empty
    Then fleet.jsonl waiter_pid is null
    And waiter_tombstone is true
    And shepherd did not notify

  Scenario: shepherd orphan-notifies once after eviction
    Given an open fleet.jsonl row whose waiter_pid names a dead process
    And the Extra High latest runStatus is FINISHED
    When fleet-shepherd.py --once runs
    Then the owning seat is A2A-pinged once with FLEET_DONE
    And notified_by is shepherd
    When fleet-shepherd.py --once runs again
    Then no second ping
