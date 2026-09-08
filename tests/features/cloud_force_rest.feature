# Unique remaining vs origin/main: CLOUD_FORCE_REST / GCS_CLOUD_BACKEND=rest
# take REST curl Extra High create without SDK Agent.create (no double-create).
# sdk/run.sh exit 75 still REST-falls-back. Coverage must not rely only on
# CURSOR_API_BASE (pytest mock URL). Never Bot CloudAgent. Living Sky (LIV) only.
# Do not remint extraHighModel / PAL-48 LIV-67. Do not clone LIV-41/67/85/82.

Feature: Extra High REST force skips SDK create
  Directors may force the curl control-plane. That path must not also call
  @cursor/sdk Agent.create. A bootstrap/unavailable SDK (run.sh exit 75)
  still falls back to REST. Other SDK failures must not REST-retry create.

  Scenario: CLOUD_FORCE_REST=1 launches via REST without Agent.create
    Given CLOUD_FORCE_REST=1
    And CURSOR_API_BASE points at a mock (URL routing only)
    And CLOUD_SDK_RUN is a stub that would Agent.create
    When scripts/launch-cloud-extra-high.sh runs
    Then the SDK stub is not invoked
    And REST POST /v1/agents happens once
    And stderr includes CLOUD_SDK_FALLBACK REST requested

  Scenario: GCS_CLOUD_BACKEND=rest launches via REST without Agent.create
    Given GCS_CLOUD_BACKEND=rest
    And CLOUD_SDK_RUN is a stub that would Agent.create
    When scripts/launch-cloud-extra-high.sh runs
    Then the SDK stub is not invoked
    And REST POST /v1/agents happens once

  Scenario: sdk/run.sh exit 75 still REST-falls-back
    Given CLOUD_FORCE_REST is unset
    And CLOUD_SDK_RUN exits 75
    And CURSOR_API_BASE points at a mock
    When scripts/launch-cloud-extra-high.sh runs
    Then the SDK stub is invoked
    And REST POST /v1/agents happens once
    And stderr includes SDK unavailable (exit 75)

  Scenario: non-75 SDK failure does not double-create via REST
    Given CLOUD_SDK_RUN exits 1 after a failed create
    When scripts/launch-cloud-extra-high.sh runs
    Then REST POST /v1/agents does not happen
