# Remaining tcarac/taskboard WIPE/setup paths.
# Executable binding: tests/test_taskboard_wipe_setup.py
# BDD in Action: demonstrate, don't theatre. Looks Good to Me: no LGTM without evidence.
# Distinct from OPEN gcs-taskboard-maintainer-kit-beat1849 (maintainer.sh start/health/docs)
# and LIV-86 PIN/upgrade. This slice is board-only deploy/teardown/wipe under
# scripts/studio/taskboard/. No Agent Kanban reconnect. No compiled binary blob.

Feature: wipe-box taskboard setup and teardown paths
  Palemon wipe brings the tcarac/taskboard host processes up and down from
  scripts/studio/taskboard/setup-taskboard.sh. Host PATH tools are ticket / tb
  against $GCS_TASKBOARD_DB. Living Sky Linear is LIV; never Black Swan.

  Scenario: setup-taskboard start installs host ticket/tb and starts UI plus MCP HTTP
    Given a wipe box with TASKBOARD_BIN pointing at a fake taskboard
    And GCS_A2A_STATE is a live state dir
    When scripts/studio/taskboard/setup-taskboard.sh start runs
    Then stdout includes TASKBOARD_SETUP_OK
    And $GCS_ROOT/bin/ticket and $GCS_ROOT/bin/tb are on the kit PATH
    And ticket list execs taskboard --db $DB ticket list
    And start-taskboard.sh and mcp-http.sh are running against that DB

  Scenario: setup-taskboard stop leaves studio.env and the sqlite file
    Given a board started by setup-taskboard.sh
    When setup-taskboard.sh stop runs
    Then stdout includes TASKBOARD_SETUP_STOP
    And studio.env and taskboard.db still exist
    And UI and MCP HTTP pid files are gone

  Scenario: setup-taskboard wipe uses taskboard clear and does not touch inboxes
    Given a board DB, an inbox.jsonl, a mind pin, and studio.env
    When GCS_TASKBOARD_WIPE=1 setup-taskboard.sh wipe runs
    Then stdout includes TASKBOARD_WIPE_OK
    And the fake binary received --db $DB clear -f
    And taskboard.db is removed
    And inbox.jsonl, mind pin, and studio.env remain

  Scenario: planted Agent Kanban tree is AK_REFUSE
    Given scripts/studio/agent-kanban exists under GCS_ROOT
    When setup-taskboard.sh start or wipe runs
    Then it exits nonzero and prints AK_REFUSE
    And it does not exec ak start

  Scenario: root setup.sh and cleanup.sh delegate board paths
    Given the Palemon DR entrypoints
    Then ./setup.sh start path calls setup-taskboard.sh
    And ./cleanup.sh stop path calls setup-taskboard.sh stop
    And CLEANUP_WIPE_STATE=1 calls setup-taskboard.sh wipe
    And this is not maintainer.sh health/docs and not upgrade-taskboard.sh
