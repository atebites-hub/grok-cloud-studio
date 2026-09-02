Feature: CCGS audio + narrative lead map (not a 49-specialist registry)
  Living Sky CCGS leads on grok-cloud-studio. Extra High pin: grok-4.6 xhigh
  fast=false. Palemon Linear is Living Sky (LIV), never Black Swan Money.
  Never Bot CloudAgent. Never vendor Hermes. Never merge GCS #26+#28.

  Distinct from LIV-41 mind-must-launch / playability-below-8 clones.
  Distinct from leftover hive launch-map (GCS #138). This example is the
  first-class mind-seat map: audio and narrative are registry seats;
  CCGS lead titles alias in scripts/a2a/lib.py; unmapped specialist
  titles do not mint seats.

  Scenario: Aliases in lib.py resolve onto first-class seats
    Given CCGS_LEAD_ALIASES in scripts/a2a/lib.py
    When python3 scripts/a2a/lib.py canonical producer
    Then the name is floor-ops
    And creative folds onto floor
    And audio and narrative stay themselves

  Scenario: Unmapped specialist titles do not mint seats
    Given GCS_MIND_SEATS / GCS_GROW_SEATS / GCS_ACP_SEATS list composer
    And other unmapped titles such as narrative-designer and sound-designer
    When mind-seats, grow-seats, launch-seats, known, and the host ticker run
    Then those specialist names are absent from the maps
    And no .a2a-state/composer or .a2a-state/narrative-designer directory is created
    And producer still folds onto floor-ops
    And first-class audio and narrative still mint
