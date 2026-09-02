Feature: Opt-in grok mind is --resume plus --prompt-file, never bare -p
  Living Sky LIV-62 remaining clap after GCS #21. Hermes-style inbox mail is
  one grok headless turn on Grok Cloud Studio: pinned UUID + --prompt-file.
  Later turns --resume that UUID. Never bare -p (live 2026-08-21: -p before
  --resume is clap rc=2 because --single requires <PROMPT>).

  grok --model grok-4.6 --reasoning-effort xhigh. Extra High specialists stay
  grok-4.6 xhigh fast=false. Never Bot CloudAgent. Do not vendor
  NousResearch/hermes-agent. Do not clone LIV-85 mail preserve PRs
  (#81 / #61 / #67). Do not clone LIV-41 must-launch.

  Scenario: A later inbox line is grok --resume pinned UUID --prompt-file
    Given an opted-in mind seat whose first mail line already minted the pin
    When the mind harvests a second peer mail line
    Then grok is invoked with --resume of that same UUID and --prompt-file
    And the argv has no bare -p / --single
    And --model is grok-4.6 and --reasoning-effort is xhigh
    And the mailbox offset advances after runner exit 0

  Scenario: Mail that looks like -p still lives in --prompt-file
    Given an inbox line whose text contains -p --single --resume
    When the mind harvests that line
    Then those tokens are in the --prompt-file body
    And they are not grok CLI flags

  Scenario: grok_cli_argv refuses banned flags and pins extra-high
    Given a grok mind argv
    Then validate_grok_mind_argv accepts the law clap
    And it rejects -p, --single, missing --prompt-file, and missing pin

  Scenario: Extra High is grok-4.6 xhigh fast=false, never Bot CloudAgent
    Given scripts/launch-cloud-extra-high.sh and plugin cloud_launch
    Then Extra High create is grok-4.6 xhigh fast=false
    And Bot CloudAgent is not a launch path

  Scenario: Do not vendor Hermes or clone LIV-85 / LIV-41
    Then vendor/hermes-agent is absent
    And hub enqueue is SUBMITTED; COMPLETED / A2A ACK is a receipt
    And mind.py has no LIV-41 must-launch / RUNNING floor
