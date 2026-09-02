Feature: Grok mind spawn pins mind/session onto --prompt-file mail.txt
  Living Sky LIV-62 remaining spawn identity. GCS #21 already fixed the
  headless clap. OPEN #95 owns validate_grok_mind_argv (construction).
  This example is the leftover spawn hook: grok_cli_runner must pass
  that seat's mind/mail.txt and mind/session UUID, not latest-in-cwd.

  Opt-in mind inbox → grok --resume pinned UUID --prompt-file, never bare -p.
  grok --model grok-4.6 --reasoning-effort xhigh.

  Refuse --continue, --fork-session, glued --resume=-1, and --print /
  positional prompt (2026-08-21: -p before --resume is clap rc=2 because
  --single requires <PROMPT>). Cursor CLI -p is a different runner.

  Do not vendor NousResearch/hermes-agent. Do not clone LIV-85 mail
  preserve PRs (#81 / #61 / #67). Do not clone LIV-41/67/85 spawn-floor
  or runStatus mail piles. Never Bot CloudAgent. Never merge GCS #26+#28.

  Scenario: Spawn --prompt-file is seat mind/mail.txt and pin matches session
    Given an opted-in mind seat with one peer mail line
    When grok_cli_runner harvests that line
    Then --prompt-file is $GCS_A2A_STATE/<seat>/mind/mail.txt
    And --session-id equals mind/session
    And the mail body is not a positional argv prompt
    And a later line --resume's that same UUID onto the same mail.txt path

  Scenario: Latest-in-cwd and --print are refused at spawn
    Given a grok mind argv for a pinned mail.txt
    Then assert_pinned_prompt_file_spawn accepts the law clap
    And it rejects --continue, --fork-session, --print, and --resume=-1
    And it rejects a positional prompt next to --prompt-file
    And it rejects --prompt-file pointing at a different path
    And grok_cli_runner fail-closes those argv mutations (offset unchanged)
