"""LIV-103: directors never block-wait on Cloud; SDK waiter/context return.

Never Bot CloudAgent. Extra High stays grok-4.6 xhigh.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "mcp"))
sys.path.insert(0, str(ROOT / "scripts" / "directors"))

from fleet_ledger import context_snippet, notify_text  # noqa: E402
from gcs_mcp import cloud_tools, tools_for  # noqa: E402
from test_cloud_launch import (  # noqa: E402
    CLOUD,
    EXAMPLE_REPO,
    FAKE_KEY,
    LAUNCH,
    MockCursorAPI,
    _run,
    _script_env,
)

FOOTER = ROOT / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = ROOT / "docs" / "CLOUD.md"
CLOUD_README = ROOT / "scripts" / "cloud" / "README.md"
AGENTS = ROOT / "AGENTS.md"
WATCH = CLOUD / "watch.sh"
WATCH_LONG = CLOUD / "watch-cloud-agent.sh"
WAIT_TS = CLOUD / "sdk" / "wait-notify.ts"
LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
MIND_PY = ROOT / "scripts" / "directors" / "mind.py"
GCS_NODE = ROOT / "plugins" / "gcs-cursor-cloud" / "server.mjs"


def test_mcp_cloud_plane_has_no_watch_tool() -> None:
    names = {t["name"] for t in cloud_tools()}
    assert "cloud_watch" not in names
    assert "cloud_wait" not in names
    assert names == {"cloud_launch", "cloud_list", "cloud_status", "cloud_result"}
    all_names = {t["name"] for t in tools_for("all")}
    assert "cloud_watch" not in all_names
    launch = next(t for t in cloud_tools() if t["name"] == "cloud_launch")
    result = next(t for t in cloud_tools() if t["name"] == "cloud_result")
    assert "block" in launch["description"].lower() or "waiter" in launch["description"].lower()
    assert "context" in result["description"].lower() or "non-blocking" in result["description"].lower()


def test_node_cloud_mcp_has_no_watch() -> None:
    src = GCS_NODE.read_text(encoding="utf-8")
    assert "cloud_watch" not in src
    assert "watch-cloud-agent" not in src
    assert "cloud_result" in src
    assert "cloud_launch" in src


def test_director_watch_refused_without_polling(tmp_path: Path) -> None:
    env = _script_env(
        tmp_path,
        "http://127.0.0.1:1",
        CURSOR_API_KEY=FAKE_KEY,
        GCS_DIRECTOR_SEAT="ops",
        CLOUD_WATCH_TIMEOUT_SEC="30",
        CLOUD_WATCH_INTERVAL="30",
    )
    env.pop("CLOUD_ALLOW_BLOCK_WAIT", None)
    started = time.monotonic()
    proc = _run(WATCH, ["bc-still-running"], env)
    elapsed = time.monotonic() - started
    blob = proc.stdout + proc.stderr
    assert elapsed < 2.0, elapsed
    assert proc.returncode != 0
    assert "CLOUD_WATCH_REFUSED" in blob
    assert "director-no-block-wait" in blob
    assert "result-cloud-agent.sh" in blob or "cloud_result" in blob
    assert FAKE_KEY not in blob


def test_watch_override_still_polls_once(tmp_path: Path) -> None:
    with MockCursorAPI(run_statuses=["RUNNING", "FINISHED"]) as api:
        env = _script_env(
            tmp_path,
            api.base,
            CURSOR_API_KEY=FAKE_KEY,
            GCS_DIRECTOR_SEAT="ops",
            CLOUD_ALLOW_BLOCK_WAIT="1",
            CLOUD_WATCH_TIMEOUT_SEC="4",
            CLOUD_WATCH_INTERVAL="0.05",
        )
        proc = _run(WATCH_LONG, ["bc-1"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_WATCH_REFUSED" not in blob
    assert FAKE_KEY not in blob


def test_launch_returns_while_run_still_creating(tmp_path: Path) -> None:
    with MockCursorAPI(run_statuses=["CREATING", "RUNNING", "RUNNING"]) as api:
        env = _script_env(
            tmp_path,
            api.base,
            CURSOR_API_KEY=FAKE_KEY,
            GCS_DIRECTOR_SEAT="ops",
            GCS_SPAWN_WAITER="1",
            CLOUD_SPAWN_WAITER="1",
            CLOUD_WAITER_DRY="1",
        )
        started = time.monotonic()
        proc = _run(
            LAUNCH,
            ["--name", "liv-103-no-wait", "Implement LIV-103. Open a PR."],
            env,
        )
        elapsed = time.monotonic() - started
    blob = proc.stdout + proc.stderr
    assert elapsed < 5.0, elapsed
    assert proc.returncode == 0, blob
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_WAITER_DRY" in blob or "CLOUD_WAITER_SPAWNED" in blob
    assert "CLOUD_WATCH_OK" not in blob
    assert FAKE_KEY not in blob
    assert api.posts and api.posts[0]["body"]["repos"][0]["url"] == EXAMPLE_REPO


def test_result_context_is_one_shot_not_a_wait(tmp_path: Path) -> None:
    with MockCursorAPI(run_statuses=["RUNNING"]) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY, GCS_DIRECTOR_SEAT="ops")
        started = time.monotonic()
        proc = _run(CLOUD / "result-cloud-agent.sh", ["bc-ctx"], env)
        elapsed = time.monotonic() - started
    blob = proc.stdout + proc.stderr
    assert elapsed < 3.0, elapsed
    assert proc.returncode == 0, blob
    payload = json.loads(proc.stdout)
    assert payload["agentId"] == "bc-ctx"
    assert payload["runStatus"] == "RUNNING"
    assert "result" in payload
    assert FAKE_KEY not in blob


def test_notify_text_returns_sdk_context_snippet() -> None:
    payload = {
        "name": "liv-103",
        "runStatus": "FINISHED",
        "prUrl": "https://github.com/example/repo/pull/1",
        "url": "https://cursor.com/agents/bc-1",
        "result": "Opened PR with waiter/context return. Directors must not watch.",
        "summary": "ignored when result is set",
    }
    text = notify_text("bc-1", payload)
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert "context=" in text
    assert "waiter/context return" in text
    assert "result-cloud-agent.sh bc-1" in text
    assert "MERGE_REQUEST" in text


def test_context_snippet_prefers_result_then_summary_and_truncates() -> None:
    assert context_snippet({"result": "  hello   world  "}) == "hello world"
    assert context_snippet({"summary": "from summary"}) == "from summary"
    long = "x" * 400
    snip = context_snippet({"result": long}, limit=40)
    assert len(snip) <= 40
    assert snip.endswith("…")


def test_director_docs_and_footer_forbid_block_wait_and_bot_cloudagent() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    cloud_md = CLOUD_DOC.read_text(encoding="utf-8")
    readme = CLOUD_README.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")
    assert "Do NOT block" in footer or "do not block" in footer.lower()
    assert "wait-notify" in footer
    assert "run.wait" in footer
    assert "Bot CloudAgent" in footer
    assert "Never" in footer and "Bot" in footer
    assert "never block-wait" in cloud_md.lower() or "do not watch" in cloud_md.lower()
    assert "CLOUD_WATCH_REFUSED" in cloud_md
    assert "waiter" in cloud_md.lower()
    assert "result-cloud-agent.sh" in cloud_md
    assert "Bot CloudAgent" in cloud_md
    assert "CLOUD_ALLOW_BLOCK_WAIT" in readme
    assert "do not block on watch" in agents.lower()
    assert "Bot CloudAgent" not in LAUNCH_TS.read_text(encoding="utf-8")
    assert "grok bot" not in LAUNCH.read_text(encoding="utf-8").lower()
    wait_src = WAIT_TS.read_text(encoding="utf-8")
    assert "run.wait" in wait_src
    assert "Bot CloudAgent" not in wait_src
    watch_sh = WATCH.read_text(encoding="utf-8")
    common = (CLOUD / "_common.sh").read_text(encoding="utf-8")
    assert "cloud_refuse_director_block_wait" in watch_sh
    assert "CLOUD_WATCH_REFUSED" in common
    assert "GCS_DIRECTOR_SEAT" in common
    assert "cloud_watch" not in footer.lower()


def test_mind_plugins_expose_context_return_not_watch() -> None:
    spec = importlib.util.spec_from_file_location("gcs_mind_liv103", MIND_PY)
    assert spec is not None and spec.loader is not None
    mind = importlib.util.module_from_spec(spec)
    sys.modules["gcs_mind_liv103"] = mind
    spec.loader.exec_module(mind)
    names = set(mind.PLUGINS)
    assert "cloud_launch" in names
    assert "ticket" in names
    assert "a2a_send" in names
    assert "cloud_watch" not in names
    assert "cloud_wait" not in names
    doc = mind.plugin_cloud_launch.__doc__ or ""
    assert "block" in doc.lower() or "waiter" in doc.lower() or "context" in doc.lower()


def test_studio_mind_plugin_lists_launch_not_watch() -> None:
    server = ROOT / "plugins" / "studio-mind" / "server.py"
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    proc = subprocess.run(
        ["python3", str(server)],
        cwd=str(ROOT),
        input=msg,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "GCS_ROOT": str(ROOT), "GCS_MCP_NDJSON": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    reply = json.loads(proc.stdout.splitlines()[0])
    names = {t["name"] for t in reply["result"]["tools"]}
    assert "cloud_launch" in names
    assert "ticket" in names
    assert "a2a_send" in names
    assert "cloud_watch" not in names
    assert "cloud_wait" not in names
