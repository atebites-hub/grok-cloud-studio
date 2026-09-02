Feature: Mind runner SWITCH persists grok|cursor and flips once on quota
  Living Sky FAT mechanic on atebites-hub/grok-cloud-studio. Default
  GCS_MIND_RUNNER=auto persists $GCS_A2A_STATE/<seat>/mind/runner
  (grok or cursor). Each mail line uses that file. On quota / HTTP 402,
  flip and retry that same mail line once on the other runner
  (MIND_SWITCH). Forced GCS_MIND_RUNNER=grok or cursor does not flip
  and does not rewrite mind/runner.

  Grok mind CLI is grok-4.6 --reasoning-effort xhigh (extra-high).
  Extra High grunts stay grok-4.6 xhigh fast=false. Cursor CLI is
  cursor-grok-4.6-xhigh with a separate mind/cursor-session pin.
  Never remint the grok UUID because the runner switched. Never Bot
  CloudAgent. Do not vendor Hermes. LIV-85 mail.txt hold (`mail.in-flight`)
  may sit beside this FAT; SWITCH does not remint COMPLETE-as-receipt.

  Demonstrate, don't theatre. Offset advances only on runner exit 0.

  Scenario: Auto persists the winning runner under mind/runner
    Given GCS_MIND_RUNNER is auto or unset
    And mind/runner is missing
    When a grok turn exits 0
    Then $GCS_A2A_STATE/<seat>/mind/runner contains grok
    And the next mail line uses grok without probing cursor

  Scenario: HTTP 402 flips once and retries the same mail line
    Given auto mode and the current runner is grok
    When grok returns HTTP 402 / usage balance exhausted
    Then mind logs MIND_SWITCH from=grok to=cursor reason=quota-exhausted
    And that same mail line runs on Cursor CLI once
    And mind/runner becomes cursor
    And the grok session UUID is not reminted

  Scenario: After a switch, later mail does not probe grok
    Given mind/runner is cursor after a quota switch
    When the next inbox line arrives
    Then only the cursor runner runs
    And MIND_SWITCH is not logged again

  Scenario: Forced grok or cursor does not flip on 402
    Given GCS_MIND_RUNNER=grok or GCS_MIND_RUNNER=cursor
    When that runner returns HTTP 402
    Then the other runner is not invoked
    And mind/runner is not rewritten
    And MIND_SWITCH is absent
    And offset stays 0

  Scenario: Both runners 402 still switch only once
    Given auto mode
    When grok and then cursor both return HTTP 402
    Then MIND_SWITCH is logged once
    And the same mail line is not ping-ponged
    And offset stays 0

  Scenario: Constraints stay intact
    Given this FAT slice
    Then grok argv still pins grok-4.6 xhigh
    And Extra High launch stays fast=false
    And the tree does not vendor Hermes
    And LIV-85 mail hold may sit beside this SWITCH FAT
