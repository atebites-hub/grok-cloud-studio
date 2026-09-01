# LIV-74. Executable binding: tests/test_liv74_demonstrated_n.py
# Looks Good to Me: directors paste demonstrated N, not leftover-green --override-ini.
# Palemon Linear is Living Sky LIV. NEVER Black Swan. Never Bot CloudAgent.

Feature: demonstrated N without leftover-green --override-ini (LIV-74)
  pytest.ini addopts=-q plus CLI `.venv/bin/pytest -q` becomes extra-quiet
  on pytest 8+ and hides the "N passed" count. Leftover PRs then ran
  `--override-ini='addopts=' -q` on the whole suite (200+ leftover greens).
  That is theatre. Directors paste a small N from these evidence files.

  Scenario: Ship-gate pytest -q does not need --override-ini
    Given pytest.ini
    Then addopts does not include -q or --quiet
    And scripts/studio/demonstrate_bdd.sh does not pass --override-ini
    And the command is python3 -m pytest -q (or .venv/bin/pytest -q)
      on the LIV-67 / LIV-73 / LIV-74 test files only

  Scenario: Evidence files are not the leftover suite
    Given tests/test_liv67_list_prints_runstatus.py
    And tests/test_liv73_failing_then_passing.py
    And tests/test_liv74_demonstrated_n.py
    Then directors paste that targeted run as demonstrated N
    And they do not paste leftover-green 200+ dots from the full suite
