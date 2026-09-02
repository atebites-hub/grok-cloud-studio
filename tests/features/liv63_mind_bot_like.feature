Feature: Grok Build minds are grok-bot-like (LIV-63 remaining)
  Living Sky LIV-63 remaining Hermes-port. PR #47 already has command-center
  Extra High tools and mail-as-a-turn BDD. This example is the leftover
  grok-bot-like mechanic: mailbox harvest is a disk turn (like Bot
  bot-wake.txt), and the mind spawn PATH is Extra High — never Bot
  CloudAgent, never ACP session/prompt.

  Demonstrate, don't theatre. Do not vendor NousResearch/hermes-agent.
  Do not land harvest mailbox PRs #26 and #28 (envelope, defang,
  heartbeat). Do not restack #47 cloud_list / cloud_followup plugins.
  Do not remint #61 SUBMITTED/COMPLETE or #41 send pin.

  Scenario: Mailbox harvest writes a Bot-like turn file before the runner
    Given an opted-in mind seat with one peer mail line
    When the mind harvests that line
    Then mind/mail.txt and mind/turn.txt exist before the runner starts
    And the runner prompt is that mailbox body (no envelope, no defang)
    And grok --prompt-file is the turn, not ACP session/prompt
    And empty harvest does not remint and does not invent a turn file

  Scenario: Mind spawn PATH is Extra High, never Bot CloudAgent
    Given a Grok Build mind seat GROK_HOME
    When the mind loop installs remaining spawn PATH wrappers
    Then cloud_launch execs scripts/launch-cloud-extra-high.sh
    And a2a_send execs scripts/a2a/send.sh (Bot-like reply)
    And the wrappers do not launch Bot CloudAgent
    And cloud_list / cloud_watch are not restacked here

  Scenario: Stay-up ticker includes opted-in mind seats as mailbox turns
    Given GCS_MIND_SEATS includes a Director seat outside leftover GROW
    When the host ticker ticks with default seats
    Then that mind seat gets an inbox keep-alive line
    And the line is mailbox mail, not ACP inject

  Scenario: Mind bus start keep-alives without ACP daemons
    Given GCS_MIND_SEATS is set and --daemons is off
    When start-studio-bus.sh start runs
    Then the host ticker starts for mind stay-up
    And ACP seat daemons stay skipped
