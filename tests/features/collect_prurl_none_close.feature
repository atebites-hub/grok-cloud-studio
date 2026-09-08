# Unique remaining vs origin/main: collect prUrl null/empty → CLOSE.
# Executable binding: tests/test_collect_prurl_none_close.py
# Distinct from waiter-owner-seat-tandem (GCS #172, already RUNNING) and
# occupancy remint (#125 / #132 / #154). Do not remint those.
# Do not clone LIV-41/67/85/82. Do not touch start-studio-bus.
# Do not vendor Hermes. Do not merge GCS #26/#28.
# Do not land palemon leftover #165/#167. Never Bot CloudAgent.

Feature: collect prUrl URL vs none; leftover of merged shard is CLOSE
  Directors collect Extra High with scripts/cloud/result-cloud-agent.sh.
  When the JSON prUrl is a URL, existing MERGE_REQUEST / HOLD / INSPECT
  paths apply. When prUrl is null or empty, Directors CLOSE. No
  MERGE_REQUEST. No twin Extra High. Leftover of a merged shard is CLOSE.

  Scenario: prUrl URL vs none
    Given Extra High FINISHED
    And collect JSON prUrl is a GitHub pull URL
    Then directorAction is not CLOSE
    And Directors may ping QA MERGE_REQUEST when ship-gate paste exists
    Given Extra High FINISHED
    And collect JSON prUrl is null or empty or the token none
    Then directorAction is CLOSE
    And Directors do not ping QA MERGE_REQUEST
    And Directors do not launch a twin Extra High

  Scenario: leftover of merged shard is CLOSE
    Given the unique remaining shard already merged on origin/main
    And a leftover Extra High FINISHED with prUrl none
    When a Director runs scripts/cloud/result-cloud-agent.sh
    Then the JSON includes prUrl none and directorAction CLOSE
    And leftover of merged shard is CLOSE
    And FLEET_DONE notify_text is CLOSE not PR_READY

  Scenario: live RUNNING with prUrl none is not CLOSE
    Given Extra High latest runStatus is RUNNING
    And collect JSON prUrl is null
    Then directorAction is not CLOSE
    And Directors do not close a live Extra High

  Scenario: tandem and occupancy remint stay distinct
    Given waiter-owner-seat-tandem already RUNNING on origin/main
    And occupancy remint PRs #125 / #132 / #154 stay HOLD
    Then this change does not remint spawn-waiter.sh
    And this change does not remint occupancy-count.sh
    And start-studio-bus.sh is untouched
    And Hermes is not vendored
    And GCS #26 and #28 stay CLOSED unmerged
    And palemon leftover #165 / #167 do not land
    And Extra High is never Bot CloudAgent
