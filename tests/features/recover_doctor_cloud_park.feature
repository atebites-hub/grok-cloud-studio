# CLOUD_API_PARKED remaining (recover/doctor). Distinct from the
# launch-cloud-extra-high.sh park guard (other writer).
# BDD in Action: demonstrate, don't theatre. Looks Good to Me: no LGTM without evidence.
# PAL-25 stays studio-ops: bot-bridge stays off unless GCS_BOT_BRIDGE=1.
# Never Bot CloudAgent. Never vendor Hermes. Living Sky (LIV) only.

Feature: recover and doctor must not spawn Extra High while parked
  When CLOUD_API_PARKED is set (env, studio.env, or $GCS_A2A_STATE/CLOUD_API_PARKED
  marker), ./recover.sh and ./doctor.sh must not spawn Extra High. Local DR
  still runs. bot-bridge stays off unless GCS_BOT_BRIDGE=1.

  Scenario: recover with CLOUD_API_PARKED=1 does not spawn Extra High
    Given CLOUD_API_PARKED=1
    And a PATH honeypot for Extra High create
    When ./recover.sh runs (dry-run is allowed)
    Then stdout includes RECOVER_CLOUD_PARKED
    And stdout includes RECOVER_OK
    And the Extra High honeypot is not invoked
    And stdout does not include CLOUD_LAUNCH_OK

  Scenario: doctor with CLOUD_API_PARKED=1 does not spawn Extra High
    Given CLOUD_API_PARKED=1
    And Cursor Cloud launch-plane env is present
    When ./doctor.sh runs
    Then stdout includes CLOUD_API_PARKED
    And stdout includes doctor: OK
    And the Extra High honeypot is not invoked
    And stdout does not include CLOUD_LAUNCH_OK

  Scenario: recover parked still leaves bot-bridge off by default
    Given CLOUD_API_PARKED=1
    And GCS_BOT_BRIDGE is unset
    When ./recover.sh runs
    Then stdout includes STUDIO_BUS_BOT_BRIDGE_SKIP
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_START
