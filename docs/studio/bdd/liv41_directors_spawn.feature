# LIV-41 — Grok Build directors spawn Extra High themselves
# Living Sky (linear.app/livingsky, team Livingsky / LIV). NEVER Black Swan.
# Never Bot CloudAgent. Extra High stays grok-4.6 xhigh, fast=false.
# Do not reuse --name gcs-liv41-mind-must-launch (that agent is FINISHED).
#
# BDD example (demonstrate, don't theatre): minds/directors themselves call
# scripts/launch-cloud-extra-high.sh or the cloud_launch plugin. Donald does
# not spawn. A director turn that does not spawn when RUNNING < 8 per repo
# is a FAIL. Prose about launching is theatre, not a spawn.

Feature: Grok Build directors spawn Extra High themselves
  Directors and leads are Grok Build minds. Specialists are Cursor Cloud
  Extra High via scripts/launch-cloud-extra-high.sh or cloud_launch.
  Count latest-run runStatus RUNNING for GCS_CLOUD_REPO (leftover
  ACTIVE+FINISHED shells are not workers). Floor is 8 per bound repo.
  Do not have Donald DIY Extra High launch.

  Scenario: Under floor, a director turn without a spawn is FAIL
    Given a Grok Build director mind seat that is not skipSeats
    And the bound repo has fewer than 8 RUNNING Extra High
    When that seat completes a spawn-required turn (ACP_PING / LAUNCH / TASK_ASSIGN / playability)
    And the turn does not invoke scripts/launch-cloud-extra-high.sh or cloud_launch
    Then the turn is FAIL (reason=no-spawn)
    And mind does not advance inbox offset
    And mentioning the launcher in prose is theatre, not a spawn

  Scenario: Under floor, an actual launcher or plugin invoke PASSES
    Given fewer than 8 RUNNING Extra High on the bound repo
    When the director invokes cloud_launch or scripts/launch-cloud-extra-high.sh on argv
    Then the turn is PASS
    And Shell ls/cat/rg of the launcher path is not a spawn
    And --name gcs-liv41-mind-must-launch does not count (name is FINISHED)
    And donald / orchestrator Bot CloudAgent names do not count

  Scenario: At floor, a director turn without a spawn is not FAIL
    Given 8 or more RUNNING Extra High on the bound repo
    When a spawn-required director turn does not launch
    Then the turn is not FAIL for no-spawn

  Scenario: Donald does not spawn Extra High
    Given Donald and orchestrator are Grok Bot skipSeats
    Then GCS_MIND_SEATS never includes donald or orchestrator
    And process_once on donald consumes nothing (reason=skipSeats)
    And the footer forbids having Donald DIY Extra High launch
    And floor-ops (Grok Build Donald-clone) still spawns itself via the launcher

  Scenario: A2A_REPLY and FLEET_DONE do not require a spawn
    Given an A2A_REPLY duplex ping or FLEET_DONE / PR_READY collect ping
    When the director turn does not launch
    Then the turn is not FAIL for no-spawn

  Scenario: PATH cloud_launch wrapper and studio-mind plugin invoke the launcher
    Given seat GROK_HOME/bin and ~/.grok/bin
    When seat identity installs wrappers
    Then cloud_launch on PATH execs scripts/launch-cloud-extra-high.sh
    And studio-mind MCP cloud_launch is the same script
    And Cursor CLI still uses the PATH launcher (GROK_HOME plugin does not transfer)

  Scenario: Never Bot CloudAgent, pin grok-4.6 xhigh
    Given Extra High create and mind argv
    Then model is grok-4.6 with reasoning-effort xhigh and fast=false
    And Grok Bot is never launched as a CloudAgent
