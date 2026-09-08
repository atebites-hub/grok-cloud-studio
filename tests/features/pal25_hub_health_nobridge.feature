# PAL-25 class remaining (beat1610 / gcs-hub-health-nobridge).
# Executable binding: tests/test_pal25_hub_health_nobridge.py
# BDD in Action: demonstrate, don't theatre. Looks Good to Me: no LGTM without evidence.
#
# Distinct from:
#   GCS #74 / #108 — missing pidfile spawn skip (want_bot_bridge)
#   GCS #36 — default keep-alive of leftover live pid (do not rebase)
#   GCS #77 — stale/dead pidfile tombstone bot-bridge.standby (do not rebase)
#   GCS #131 / #145 / beat1849 — leftover-pid eviction (do not rebase)
#   GCS #165 leftover-green paste gate (do not remint)
#   GCS #167 mind 402 MIND_SWITCH (do not steal)
#   GCS #168 pytest live-bus isolate plugin (do not steal)
#   PAL-8 Dewcave generate HOLD; do not steal PAL-8/11/12/16
#
# This ticket: recover.sh must not restart bot-bridge after RECOVER when
# hub GET /health and taskboard are already up (live layout
# GCS_A2A_STATE=/workspace/palemon/.a2a-state). Do not kill leftover dispatch.
# Bot-bridge stays off (spare component). Isolated tmp state only — never
# the live Palemon path. Never Bot CloudAgent.

Feature: recover keeps hub /health and leftover dispatch; bot-bridge stays off
  Live Palemon recover is hub+taskboard stay-up, not a bus bounce.
  studio.env GCS_MIND_SEATS must not recycle leftover dispatch when hub
  /health is already 200. Default recover must not spawn bot-bridge.py.

  Scenario: recover with hub /health and taskboard already up
    Given leftover hub/dispatch/shepherd pids on an isolated GCS_A2A_STATE
    And hub GET /health already returns 200
    And taskboard already returns 200
    And studio.env lists Palemon GCS_MIND_SEATS so minds look down
    And leftover dispatch.mind-seats is empty (recycle trap)
    And GCS_BOT_BRIDGE is unset or 0
    When ./recover.sh runs (not a dry-run)
    Then stdout includes RECOVER_OK
    And stdout does not include start-studio-bus.sh
    And stdout does not include STUDIO_BUS_DISPATCH_RECYCLE
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And the leftover dispatch pid is still that same live process
    And hub GET /health still returns 200
    And taskboard still returns 200
    And no live bot-bridge.py process is bound to that GCS_A2A_STATE
    And /workspace/palemon/.a2a-state is not the test state dir

  Scenario: recover default-off does not launch bot-bridge after RECOVER
    Given hub /health already up
    And no leftover bot-bridge.pid
    And GCS_BOT_BRIDGE is unset
    When ./recover.sh runs
    Then stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And bot-bridge.pid does not name a live process
