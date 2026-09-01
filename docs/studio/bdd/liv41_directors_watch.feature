# LIV-41 — Grok Build directors spawn AND monitor Extra High
# Living Sky (linear.app/livingsky, team Livingsky / LIV). NEVER Black Swan.
# Never Bot CloudAgent. Extra High stays grok-4.6 xhigh, fast=false.
# Do not duplicate GCS #75 spawn-only (director_turn_spawn.py / no-spawn).
#
# BDD example (demonstrate, don't theatre): after a director owns a Cursor
# Cloud bc-id, that seat must spawn wait-notify (scripts/cloud/spawn-waiter.sh
# / cloud_wait). The waiter A2A-pings the owning seat FLEET_DONE. A director
# turn without watching its own grunt is FAIL. Prose about watching is
# theatre. Do not dump monitoring to Donald or fleet-shepherd. Do not block
# this session/prompt on watch-cloud-agent.sh.

Feature: Grok Build directors monitor their own Extra High bc-ids
  Directors spawn specialists via scripts/launch-cloud-extra-high.sh.
  They also monitor those bc-ids: spawn-waiter.sh registers the seat
  fleet ledger and detaches wait-notify.ts (run.wait). On
  FINISHED|ERROR|CANCELLED|EXPIRED the waiter A2A-pings the owning seat
  FLEET_DONE / PR_READY. fleet-shepherd is orphan-only, not the monitor.

  Scenario: A director turn without watching its own grunt is FAIL
    Given a Grok Build director mind seat that is not skipSeats
    And that seat spawned Extra High (cloud_launch or launch-cloud-extra-high.sh)
    When the turn does not invoke scripts/cloud/spawn-waiter.sh, cloud_wait, or wait-notify
    Then the turn is FAIL (reason=no-watch)
    And mind does not advance inbox offset
    And mentioning the waiter in prose is theatre, not watching

  Scenario: Spawn plus waiter PASSES
    Given the director invoked cloud_launch or scripts/launch-cloud-extra-high.sh
    When the same turn invokes cloud_wait or scripts/cloud/spawn-waiter.sh --id <bc-id>
    Then the turn is PASS
    And CLOUD_WAITER_SPAWNED in the turn is watching
    And Shell ls/cat/rg of spawn-waiter.sh or watch-cloud-agent.sh is not watching
    And GCS_SPAWN_WAITER=0 / CLOUD_WAITER_SKIPPED is not watching
    And donald / orchestrator Bot CloudAgent names do not count

  Scenario: Unwatched ledger grunt on a director turn is FAIL
    Given the seat fleet.jsonl has an open bc-id with no live waiter_pid
    When ACP_PING / STATUS/CONTINUE completes without spawn-waiter / cloud_wait
    Then the turn is FAIL (reason=no-watch)
    And a live waiter_pid or notified_by=waiter is already watching (not FAIL)

  Scenario: Waiter FLEET_DONE pings the owning seat
    Given wait-notify.ts reaches a terminal runStatus
    Then fleet_ledger.notify_owner A2A-pings the owning seat (not donald)
    And the ping text includes FLEET_DONE
    And PR_READY is included when runStatus=FINISHED with a prUrl
    And fleet-shepherd does not replace a live waiter

  Scenario: A2A_REPLY and FLEET_DONE collect do not require another watch
    Given an A2A_REPLY duplex ping or FLEET_DONE / PR_READY collect ping
    When the director turn does not invoke spawn-waiter
    Then the turn is not FAIL for no-watch

  Scenario: PATH cloud_wait wrapper and studio-mind plugin invoke spawn-waiter
    Given seat GROK_HOME/bin and ~/.grok/bin
    When seat identity installs wrappers
    Then spawn_waiter / cloud_wait on PATH execs scripts/cloud/spawn-waiter.sh
    And studio-mind MCP cloud_wait is the same script
    And cursor-cloud MCP cloud_wait is the same script

  Scenario: Never Bot CloudAgent, pin grok-4.6 xhigh
    Given Extra High create and mind argv
    Then model is grok-4.6 with reasoning-effort xhigh and fast=false
    And Grok Bot is never launched as a CloudAgent
    And this PR does not restack director_turn_spawn.py
