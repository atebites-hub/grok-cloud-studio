# LIV-41 — director/mind turn execs Extra High launcher
# Living Sky (linear.app/livingsky, team LIV). NEVER Black Swan.
# Never Bot CloudAgent. Extra High stays grok-4.6 xhigh, fast=false.
# Do not reuse --name gcs-liv41-mind-must-launch (that agent is FINISHED).
#
# Distinct from GCS #65 (Python mailbox capacity beat / Donald-like fill)
# and GCS #75 (FAIL-without-spawn transcript judge / docs-only feature).
# This example is pytest-bound: the turn actually execs
# scripts/launch-cloud-extra-high.sh when it finds runStatus RUNNING < 8.

Feature: Director mind turn execs Extra High launcher when RUNNING < 8
  Grok Build directors and opted-in minds count latest-run runStatus
  RUNNING for GCS_CLOUD_REPO. Leftover agent ACTIVE+FINISHED shells are
  not workers. CREATING is not RUNNING. Floor is 8 per bound repo.
  When a director/mind turn finds RUNNING < 8 it execs
  scripts/launch-cloud-extra-high.sh itself. Host-ticker / Donald cron
  does not launch. Never Bot CloudAgent.

  Scenario: A director mind turn that finds RUNNING < 8 execs the launcher
    Given a Grok Build director mind seat that is not skipSeats
    And leftover ACTIVE Extra High shells whose latest runStatus is FINISHED
    And the bound repo therefore has fewer than 8 RUNNING
    When that seat's turn finds the under-floor runStatus count
    Then the turn actually execs scripts/launch-cloud-extra-high.sh
    And the create POST is grok-4.6 with effort=xhigh and fast=false
    And the agent name is not donald, orchestrator, or gcs-liv41-mind-must-launch

  Scenario: Leftover ACTIVE plus FINISHED is not a live worker
    Given an ACTIVE agent whose latest runStatus is FINISHED
    And a CREATING run on the same bound repo
    When the turn counts capacity
    Then running is 0
    And the turn still execs the launcher

  Scenario: At 8 RUNNING the turn does not exec the launcher
    Given 8 RUNNING Extra High on the bound repo
    When the director mind turn counts capacity
    Then the turn does not exec scripts/launch-cloud-extra-high.sh

  Scenario: Donald cron and Bot seats do not exec the launcher
    Given Donald and orchestrator are skipSeats
    And host-ticker / host-clock enqueue ACP_PING (the Donald-side cron)
    When the ticker fires
    Then it does not exec scripts/launch-cloud-extra-high.sh
    And process_once on donald consumes nothing
    And a Bot CloudAgent --name is refused
