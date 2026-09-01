# Living Sky Linear — stamp after TASK completes
# LIV-82 / LIV-43. Palemon Linear is Living Sky (linear.app/livingsky, team
# Livingsky / LIV). NEVER Black Swan Money. Never Bot CloudAgent.
# Follow-up to the MCP-catalog example: a mind script comments LIV-* after
# an A2A TASK completes. Do not have Donald DIY Linear.

Feature: Grok Build minds stamp Living Sky Linear after a TASK completes
  Studio Linear is Living Sky (linear.app/livingsky, team Livingsky / LIV).
  NEVER Black Swan Money.
  Palemon/GCS issues stay on Living Sky only, labeled
  atebites-hub/grok-cloud-studio (or the Palemon GitHub-repo label).
  The executable path is scripts/studio/linear/liv_stamp.py (GraphQL).
  Linear MCP save_comment uses the same comment body when the catalog is
  present. pytest mocks Linear.

  Scenario: After TASK completes, a mind comments LIV-82 itself
    Given an A2A TASK has completed for a mind seat (not skipSeats)
    When the mind runs liv_stamp.py after-task --issue LIV-82
    Then Linear GraphQL commentCreate (or MCP save_comment) runs
    And the comment body contains CLOUD_LAUNCH_OK or pytest evidence
    And workspace is linear.app/livingsky team LIV
    And stdout is LIV_STAMP_OK with liv= LIV-82

  Scenario: pytest mocks Linear and asserts the comment body
    Given LINEAR_API_KEY is a test token and GraphQL is localhost
    When tests/test_liv_stamp_after_task.py runs after-task
    Then the mock records CommentCreate
    And the posted body contains CLOUD_LAUNCH_OK
    And the posted body contains pytest evidence
    And the test token is never printed

  Scenario: Donald does not DIY Linear
    Given seat donald or orchestrator
    When liv_stamp.py after-task is invoked
    Then it exits LIV_STAMP_ERR before any GraphQL POST
    And skipSeats Donald does not DIY Linear

  Scenario: Never Black Swan Money
    Given an API key bound to a non-livingsky organization
    When the mind tries to stamp
    Then liv_stamp refuses
    And no comment is created on Black Swan Money
