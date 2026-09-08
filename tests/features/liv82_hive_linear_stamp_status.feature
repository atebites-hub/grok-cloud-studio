Feature: LIV-82 hive Linear stamp is STATUS evidence when MCP needsAuth
  Unique remaining vs origin/main. Living Sky only. Never Black Swan.
  Never Bot CloudAgent. Never print or commit LINEAR_API_KEY.
  Distinct from leftover Linear MCP catalog tests that only assert
  env-ref interpolation, and from GraphQL leftover comment posting.

  When LINEAR_API_KEY is unset and Linear MCP is needsAuth, hive stamp
  is STATUS evidence only. Print LINEAR_STAMP_FAIL with no comment id.
  Never call mcp_auth.

  Scenario: Unset key and needsAuth is STATUS evidence only
    Given LINEAR_API_KEY is unset
    And Linear MCP status is needsAuth
    When hive stamps LIV-82
    Then output contains LINEAR_STAMP_FAIL
    And output contains comment=none
    And output contains kind=status
    And output does not contain a comment id
    And mcp_auth is not called
    And the process exits non-zero

  Scenario: Hive stamp never calls mcp_auth to unlock Linear MCP
    Given LINEAR_API_KEY is unset
    And Linear MCP status is needsAuth
    When hive stamps LIV-82
    Then mcp_auth is not called
    And LINEAR_API_KEY is not printed
