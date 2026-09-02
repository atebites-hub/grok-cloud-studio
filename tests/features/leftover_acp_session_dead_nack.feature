Feature: Leftover ACP pin-session remints once after 3 no-start nacks
  Living Sky leftover host OS on grok-cloud-studio.
  Distinct from leftover ACP wake inbox→session/prompt FAT (#103).
  Distinct from LIV-85 mail-is-a-turn (hub COMPLETE is a receipt).
  Never grok --resume. Never Bot CloudAgent. Never vendor Hermes.

  Scenario: Three consecutive no-start nacks remint the pinned session once
    Given a GROW seat with a live grok agent serve and pinned acp.session
    And the fake serve stays silent (no chunks, no tools) on session/prompt
    When wake-daemon ACP-injects the same inbox line three times
    Then the first two nacks log ACP_INJECT_TIMEOUT reason=no-accept
    And they do not call session/new
    And acp.session stays the pinned id
    And wake.offset does not advance
    And the third nack logs ACP_INJECT_SESSION_DEAD
    And the serve receives exactly one session/new
    And acp.session is the reminted id
    And argv does not contain grok --resume
    And pin-session does not session/cancel
