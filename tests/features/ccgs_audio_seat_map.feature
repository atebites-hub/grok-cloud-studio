Feature: CCGS audio + narrative first-class seat map remaining (aliases + WIPE/MIND seats)
  Living Sky CCGS leads on grok-cloud-studio. Extra High pin: grok-4.6 xhigh
  fast=false. Palemon Linear is Living Sky (LIV), never Black Swan Money.
  Never Bot CloudAgent. Never vendor Hermes. Never merge GCS #26+#28.

  Distinct from gcs-ccgs-audio-narrative-map-beat1849 (already minted/FINISHED).
  Do not twin that fail-closed unmapped-title map. This example is the
  remaining first-class seat map: lib.py aliases for audio/narrative titles,
  and Palemon WIPE/MIND seats. Unique --name gcs-ccgs-audio-seat-map-beat1849.
  Do not add 49 specialists. Directors spawn Extra High only via
  scripts/launch-cloud-extra-high.sh.

  Scenario: Audio and narrative title aliases fold onto first-class seats
    Given the CCGS lead map in scripts/a2a/lib.py CCGS_LEAD_ALIASES
    When a caller uses audio-director, audio-lead, narrative-director, or narrative-lead
    Then canonical_seat resolves each title onto first-class audio or narrative
    And mind-seats / grow-seats print the first-class names, not the titles
    And first-class audio and narrative stay themselves

  Scenario: Palemon wipe mind seats include first-class audio and narrative
    Given studio.env.example Palemon GCS_MIND_SEATS
    When a wipe follows docs/studio/WIPE.md and docs/studio/MIND.md
    Then GCS_MIND_SEATS includes floor-ops,studio-ops,floor,art,content,systems,qa-a,qa-b,audio,narrative
    And WIPE/MIND name the audio-director and narrative-lead aliases
    And ACP/GROW stay crash-safe (audio and narrative are mind seats, not a 49-specialist floor)

  Scenario: send.sh and the hub route aliases onto first-class inboxes
    Given a running local A2A hub
    When send.sh audio-director or narrative-lead enqueues mail
    Then the line lands in .a2a-state/audio or .a2a-state/narrative
    And composer does not mint a seat directory
    And directors spawn specialists only via scripts/launch-cloud-extra-high.sh
