Feature: Hive beat applies one Manning model to a real IaC change
  LIV-71. Living Sky hive only. Never Bot CloudAgent. Never Palemon game code.
  Each 10-minute studio-ops beat applies one allowlisted Manning model
  (this example: BDD in Action) to a real IaC path and appends that APPLY
  to studio-archive/log/YYYY-MM-DD.md. HEALTH_OK is observable behavior of
  that apply, not a probe-only status. Cite the book title only; never
  paste copyrighted book text.

  Scenario: Live probes without this beat APPLY must not print HEALTH_OK
    Given live studio probes are up
    And the current beat has no APPLY line
    When health_check.sh runs
    Then output does not contain HEALTH_OK
    And the process exits non-zero
    And output contains APPLY_LOG

  Scenario: Applying BDD in Action to health_check.sh unlocks HEALTH_OK
    Given live studio probes are up
    And studio-ops applies "BDD in Action" to "IaC: health_check.sh gates HEALTH_OK on this beat APPLY; Palemon: no game code"
    When health_check.sh runs
    Then output contains HEALTH_OK
    And the apply-log cites model "BDD in Action"
    And the apply-log cites IaC path health_check.sh

  Scenario: A change that does not cite a real IaC path is rejected
    Given studio-ops applies "BDD in Action" to "IaC: vibes only; Palemon: no game code"
    Then the apply command fails
