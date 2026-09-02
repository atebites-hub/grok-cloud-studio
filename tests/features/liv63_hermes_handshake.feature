Feature: studio-mind handshake after grok plugin install --trust (LIV-63 remaining)
  Living Sky LIV-63 remaining handshake slice (unique --name
  gcs-liv63-hermes-handshake-beat1849). After
  `grok plugin install --trust` copies plugins/studio-mind into seat
  GROK_HOME, the off-tree stdio MCP must stay open through initialize.

  Install stamps $GROK_HOME/gcs-root with GCS_ROOT so copied server.py
  can import repo scripts. mcp.json runs python3 -u. Default framing is
  Content-Length; a first line starting with `{` latches NDJSON.

  Demonstrate, don't theatre. Do not vendor NousResearch/hermes-agent.
  Do not land harvest mailbox PRs #26 and #28. Do not restack cloud_list
  into mind.py. Do not twin --name gcs-liv63-hermes-remaining-beat1849.
  Do not twin gcs-github-ship-gate-workflows-beat1740 / GCS #117.
  Never Bot CloudAgent. Never chrome-devtools.

  Scenario: Off-tree GROK_HOME copy reads gcs-root and stays open
    Given grok plugin install copied studio-mind off the repo tree
    And $GROK_HOME/gcs-root points at GCS_ROOT
    When the copied server.py receives initialize
    Then it replies and the same stdio pid stays up
    And tools/list returns ticket, a2a_send, cloud_launch

  Scenario: initialize is not shutdown
    Given studio-mind stdio MCP on python3 -u
    When the client sends initialize then notifications/initialized
    Then the process does not close
    And tools/list and ping run on that same pid

  Scenario: NDJSON initialize without GCS_MCP_NDJSON still handshakes
    Given default Content-Length framing
    When the first stdin line starts with `{`
    Then initialize still replies
    And later tools/list uses that same NDJSON session

  Scenario: plugin install stamps GROK_HOME/gcs-root
    Given a seat GROK_HOME
    When install_studio_mind_plugin runs grok plugin install --trust
    Then $GROK_HOME/gcs-root contains GCS_ROOT
    And already-installed remains MIND_PLUGIN_OK
