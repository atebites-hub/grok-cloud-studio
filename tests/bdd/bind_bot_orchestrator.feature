# Bind Grok Bot orchestrator — remaining FAT
# Living Sky (linear.app/livingsky, team LIV). NEVER Black Swan.
# Never Bot CloudAgent. Extra High stays grok-4.6 xhigh, fast=false.
#
# Distinct from GCS #36 / #74 / #77 (bot-bridge live pid / default-off /
# stale pidfile tombstone). This slice is install bind + skipSeats ACP
# refuse. Do not clone those bot-bridge PRs.

Feature: Bind Grok Bot orchestrator; Bot seats are not ACP or CloudAgent
  Grok Bot is bound with GCS_BOT_AGENT_ID then ./install.sh or
  scripts/a2a/bind-bot-agent.sh. Bot seats land in registry skipSeats.
  They are not grok agent serve / ACP inject targets. Extra High must
  not be launched as the Bot (--name donald|orchestrator|grok-bot|bot).
  Palemon Linear is Living Sky (LIV).

  Scenario: Bind upserts the Bot seat into skipSeats without printing the id
    Given GCS_BOT_AGENT_ID is a real Grok Bot id
    When install or scripts/a2a/bind-bot-agent.sh runs
    Then BOT_BIND_OK names the seat
    And docs/a2a/bot-agents.json stores kind grok-bot and that agentId
    And registry skipSeats includes the seat and donald
    And the full agent id is not printed
    And CURSOR_API_KEY is not printed

  Scenario: Bind strips acpPort so the Bot cannot become an ACP target
    Given a registry Bot seat that wrongly has acpPort
    When bind-bot-agent.sh runs
    Then that seat has no acpPort
    And lib.py port for that seat fails closed (not an ACP target)

  Scenario: ACP serve and inject refuse Bot skipSeats
    Given orchestrator and donald are skipSeats
    When start-seat-daemon.sh or seat-prompt-acp.sh is invoked for those seats
    Then the script exits non-zero with reason=bot-not-acp-target
    And it does not spawn grok agent serve
    And launch-director.sh also refuses skipSeats

  Scenario: Extra High refuses a Bot CloudAgent name
    Given scripts/launch-cloud-extra-high.sh
    When --name is donald, orchestrator, grok-bot, or bot
    Then the create is refused with CLOUD_LAUNCH_ERR
    And never Bot CloudAgent is the reason
    And no POST /v1/agents happens

  Scenario: Allowed Extra High names stay grok-4.6 xhigh fast=false
    Given an Extra High name that is not a Bot skipSeat
    When launch-cloud-extra-high.sh creates via REST
    Then model is grok-4.6 with effort=xhigh and fast=false
    And autoCreatePR is true
