# IaC unique remaining: Extra High waiter owner seat.
# Executable binding: tests/test_waiter_owner_seat.py
# Distinct from GCS #32 (shepherd leftover ACTIVE+FINISHED skip — MERGED).
# Distinct from GCS #111 (waiter_pid tombstone — MERGED).
# Do not clone GCS #41/#44/#59/#67. Do not vendor Hermes. Never Bot CloudAgent.
# Palemon Linear is Living Sky (LIV), not Black Swan.

Feature: spawn-waiter registers FLEET_DONE on the owning director seat
  After CLOUD_LAUNCH_OK, spawn-waiter.sh / launch Extra High must register
  the bc-id on the owning director seat's fleet.jsonl and A2A-ping FLEET_DONE
  there. GCS_DIRECTOR_SEAT=cloud is the owner. Do not silently default to
  floor when the director seat is cloud.

  Scenario: cloud director launch does not register on floor
    Given GCS_DIRECTOR_SEAT=cloud
    When launch Extra High prints CLOUD_LAUNCH_OK and spawn-waiter runs
    Then fleet.jsonl is under the cloud seat
    And floor/fleet.jsonl does not gain that bc-id
    And CLOUD_WAITER_SPAWNED includes seat=cloud

  Scenario: --seat cloud keeps waiter_pid on cloud when env is unset
    Given GCS_DIRECTOR_SEAT and CLOUD_OWNER_SEAT are unset
    When spawn-waiter.sh --id bc-tandem --seat cloud runs
    Then cloud/fleet.jsonl stores the row and waiter_pid
    And ops/fleet.jsonl does not fork a second row
    And floor/fleet.jsonl does not store that bc-id

  Scenario: FLEET_DONE pings cloud, not floor
    Given a fleet.jsonl row registered on seat cloud
    When the waiter notifies the owner (REPORT_TO default studio-ops)
    Then A2A pings cloud then studio-ops
    And floor is not pinged
