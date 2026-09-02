Feature: Hermes session pin on Grok Cloud Studio stay-up
  Living Sky LIV-62 remaining after GCS PR #47 (first hive-upgrade).
  Hermes named agents stay pinned across idle. Grok Cloud Studio already
  has mailbox-as-a-turn (#47) as grok mind. The remaining gap is pin +
  stay-up: empty harvest must pin mind/session once and never remint.

  Do not vendor NousResearch/hermes-agent. Do not land harvest mailbox
  PRs #26 and #28 (no envelope, defang, MAIL_MAX_CHARS, mind/heartbeat,
  hub SUBMITTED). Directors stay Grok Build. Specialists stay Cursor Cloud
  Extra High (grok-4.6 xhigh, fast=false). Never Bot CloudAgent.

  Scenario: Empty harvest pins mind/session once and does not remint
    Given an opted-in mind seat with no new inbox lines
    When the mind stay-up loop harvests empty
    Then mind/session is a uuid4 pin
    And a second empty harvest keeps the same UUID
    And grok is not invoked
    And offset does not advance
    And session.minted is not written

  Scenario: First mail after idle pin uses that UUID
    Given an idle mind seat whose session was pinned on empty harvest
    When the mind harvests one peer mail line
    Then grok is invoked with --session-id of that pinned UUID
    And --prompt-file, grok-4.6, and reasoning-effort xhigh
    And a later mail --resume that same UUID (not a new mint)

  Scenario: Stay-up empty ticks do not invent a mail turn
    Given an opted-in mind seat with no new inbox lines
    When the mind harvests empty
    Then mind/mail.txt is not invented
    And transcript.jsonl is not invented
    And the argv does not include ACP session/prompt

  Scenario: Do not vendor Hermes or land harvest PRs 26 and 28
    Then vendor/hermes-agent is absent
    And mind.py has no envelope, defang, or heartbeat harvest
    And this remaining does not remint harvest envelope or hub #26/#28
