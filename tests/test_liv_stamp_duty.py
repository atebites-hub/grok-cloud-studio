"""PAL-43 remaining: hive stamps Living Sky Linear without Donald DIY.

Footer + floor / floor-ops / studio-ops / cloud SOULs require a Living Sky
LIV-* stamp (save_comment / Linear tools) after real evidence every mind
turn. Extra High in the footer is the grok-4.6 xhigh effort pin, not a
product name. Directors still spawn via scripts/launch-cloud-extra-high.sh.

Grok mcp_servers.linear stays in seat GROK_HOME. Cursor Cloud catalog is
.cursor/mcp.json Linear + taskboard only (PAL-45 / GCS #46). A mind turn
must not complete when Linear tools are missing from the active catalog.

Does not remint #46. Does not remint conflicted Linear harvests
#38 #40 #48 #64 #109 #126 #130. Never Black Swan. Never Bot CloudAgent.
Never copy GROK_HOME into Cursor CLI. Never print credentials.
"""
from __future__ import annotations

import importlib.util
import json
import stat
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
SOULS = REPO / "docs" / "studio" / "directors" / "souls"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
SEAT_GROK_MCP = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
LAUNCH = "scripts/launch-cloud-extra-high.sh"

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LIVING_SKY_HOST = "linear.app/livingsky"
BLACK_SWAN = "Black Swan"
PRIVATE_GAME = "atebites-hub/" + "palemon"
STAMP_SEATS = ("floor", "floor-ops", "studio-ops", "cloud")
CANONICAL_RESULT = (
    "RESULT bc-id=<id or none> pr=<url or none> a2a=<task-id or none> notes=<one line>"
)
GROK_LINEAR_TOML = (
    "[mcp_servers.linear]\n"
    f'url = "{LINEAR_MCP_URL}"\n'
    'headers = { Authorization = "Bearer ${LINEAR_API_KEY}" }\n'
)
TASKBOARD_ONLY_TOML = (
    "[mcp_servers.taskboard]\n"
    'command = "/bin/taskboard"\n'
    'args = ["--db", "/tmp/taskboard.db", "mcp"]\n'
)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _write_fake_grok(tmp_path: Path, log: Path) -> Path:
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:], 'GROK_HOME': os.environ.get('GROK_HOME', '')})\n"
        "log.write_text(json.dumps(rows))\n"
        "sys.stdout.write('{\"ok\": true}')\n"
        "raise SystemExit(0)\n"
    )
    return _write_exec(tmp_path / "fake-bin" / "grok", script)


def _write_fake_cursor(tmp_path: Path, log: Path, *, chat_id: str = "chat-liv-stamp") -> Path:
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        f"chat_id = {chat_id!r}\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:]})\n"
        "log.write_text(json.dumps(rows))\n"
        "if 'create-chat' in sys.argv[1:]:\n"
        "    sys.stdout.write(chat_id + '\\n')\n"
        "    raise SystemExit(0)\n"
        "sys.stdout.write('{\"ok\": true}')\n"
        "raise SystemExit(0)\n"
    )
    return _write_exec(tmp_path / "fake-bin" / "agent", script)


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> None:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-liv",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _argv_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
    grok: Path | None = None,
    cursor: Path | None = None,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_liv_stamp_{unique}")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("", encoding="utf-8")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_TASKBOARD_DB", str(db))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    monkeypatch.delenv("GCS_CURSOR_BIN", raising=False)
    if grok is not None:
        monkeypatch.setenv("GROK_BIN", str(grok))
    if cursor is not None:
        monkeypatch.setenv("GCS_CURSOR_BIN", str(cursor))
    return mind, state


def _assert_stamp_law(text: str, *, label: str) -> None:
    assert text, label
    low = text.lower()
    assert "living sky" in low, f"{label} missing Living Sky"
    assert "liv" in low, f"{label} missing LIV"
    assert LIVING_SKY_HOST in low or "livingsky" in low, f"{label} missing livingsky"
    assert "stamp" in low, f"{label} missing stamp duty"
    assert "save_comment" in low, f"{label} missing save_comment"
    assert "real evidence" in low, f"{label} missing after real evidence"
    assert "black swan" in low, f"{label} missing Black Swan forbid"
    assert "never" in low, f"{label} missing never"
    assert "donald" in low, f"{label} missing Donald DIY forbid"
    assert PRIVATE_GAME not in text, f"{label} leaked private game repo"
    assert "lin_api_" not in low, f"{label} leaked Linear token"


def test_footer_requires_living_sky_linear_stamp_after_evidence() -> None:
    text = FOOTER.read_text(encoding="utf-8")
    _assert_stamp_law(text, label="common_footer.txt")
    assert "LIV-*" in text or "LIV-" in text
    assert LAUNCH in text
    assert CANONICAL_RESULT in text
    assert "liv=<LIV" not in text
    assert "LINEAR_API_KEY=" not in text
    assert "Bot CloudAgent" in text


def test_footer_drops_extra_high_as_product_name() -> None:
    text = FOOTER.read_text(encoding="utf-8")
    low = text.lower()
    assert "launch extra high" not in low
    assert "cursor cloud extra high grunts" not in low
    assert "coding work goes to cursor cloud extra high" not in low
    assert LAUNCH in text
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in text.replace(" ", "")
    if "extra high" in low:
        assert "effort" in low or "pin" in low
        assert "product" in low
    assert "never bot cloudagent" in low


def test_stamp_souls_require_linear_after_evidence_not_donald_diy() -> None:
    for seat in STAMP_SEATS:
        path = SOULS / seat / "SOUL.md"
        text = path.read_text(encoding="utf-8")
        _assert_stamp_law(text, label=str(path.relative_to(REPO)))
        assert LAUNCH in text
        assert "LINEAR_API_KEY=" not in text
        assert PRIVATE_GAME not in text


def test_grok_home_merge_registers_linear_http_not_copied_cursor_catalog() -> None:
    mcp = _load(SEAT_GROK_MCP, "gcs_seat_grok_mcp_liv")
    out = mcp.merge_seat_taskboard_mcp("", "/bin/taskboard", "/tmp/db")
    parsed = tomllib.loads(out)
    servers = parsed["mcp_servers"]
    assert "taskboard" in servers
    assert "linear" in servers, out
    linear = servers["linear"]
    assert linear.get("url") == LINEAR_MCP_URL
    headers = linear.get("headers") or {}
    auth = str(headers.get("Authorization") or headers.get("authorization") or "")
    assert "Bearer" in auth
    assert "${LINEAR_API_KEY}" in auth
    assert "lin_api_" not in out.lower()
    assert out.count("[mcp_servers.linear]") == 1
    again = mcp.merge_seat_taskboard_mcp(out, "/bin/taskboard", "/tmp/db")
    assert tomllib.loads(again)["mcp_servers"]["linear"]["url"] == LINEAR_MCP_URL
    assert again.count("[mcp_servers.linear]") == 1
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "mcp_servers.linear" in out or "mcp_servers.linear" in common or LINEAR_MCP_URL in out


def test_cursor_cloud_catalog_stays_linear_plus_taskboard_only() -> None:
    data = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") or {}
    assert set(servers) == {"taskboard", "linear"}, servers
    assert servers["linear"].get("url") == LINEAR_MCP_URL
    blob = json.dumps(servers).lower()
    for banned in ("higgsfield", "studio-mind", "GROK_HOME", "config.toml"):
        assert banned.lower() not in blob, banned


def test_wrap_mind_mail_requires_linear_stamp_not_extra_high_product() -> None:
    mind = _load(MIND_PY, "gcs_wrap_liv_stamp")
    wrap = mind.wrap_mind_mail("task-1", "ctx-1", "STATUS ping")
    low = wrap.lower()
    assert "save_comment" in low
    assert "living sky" in low
    assert "liv" in low
    assert "real evidence" in low
    assert "black swan" in low
    assert "STATUS ping" in wrap
    assert CANONICAL_RESULT.split(" notes=")[0] in wrap or "bc-id=" in wrap
    assert "launch extra high" not in low
    assert "cursor cloud extra high grunts" not in low


def test_grok_mind_turn_does_not_complete_without_linear_in_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="nolinear", grok=grok)
    gh = state / "floor" / "grok-home"
    gh.mkdir(parents=True, exist_ok=True)
    (gh / "config.toml").write_text(TASKBOARD_ONLY_TOML, encoding="utf-8")
    _append_inbox(state, "floor", "task-nolinear", "STATUS: stamp LIV-82 after evidence")
    result = mind.process_once("floor")
    assert result["consumed"] == 0, result
    reason = str(result.get("reason") or "")
    blob = reason + str(result.get("returncode") or "")
    assert "linear" in reason.lower() or result.get("returncode") not in (None, 0)
    assert "missing-linear" in reason.lower() or "linear" in blob.lower() or reason == "runner-fail"
    assert _argv_log(log) == []
    offset = state / "floor" / "mind" / "offset"
    assert not offset.is_file() or int(offset.read_text(encoding="utf-8").strip() or "0") == 0


def test_cursor_mind_turn_does_not_complete_without_linear_in_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "cursor.argv.json"
    cursor = _write_fake_cursor(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="curnolinear", cursor=cursor)
    root = tmp_path / "cursor-root"
    mcp_dir = root / ".cursor"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "taskboard": {
                        "command": "bash",
                        "args": ["scripts/studio/taskboard/run-mcp.sh"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mind, "ROOT", root)
    monkeypatch.setenv("GCS_MIND_RUNNER", "cursor")
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    _append_inbox(state, "floor", "task-cur-nolinear", "STATUS: cursor stamp")
    result = mind.process_once("floor")
    assert result["consumed"] == 0, result
    reason = str(result.get("reason") or "")
    assert "linear" in reason.lower() or result.get("returncode") not in (None, 0)
    assert _argv_log(log) == []


def test_grok_mind_turn_completes_when_linear_is_in_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="yeslinear", grok=grok)
    gh = state / "floor" / "grok-home"
    gh.mkdir(parents=True, exist_ok=True)
    (gh / "config.toml").write_text(GROK_LINEAR_TOML, encoding="utf-8")
    _append_inbox(state, "floor", "task-yeslinear", "FLEET_DONE stamp LIV-82")
    result = mind.process_once("floor")
    assert result["consumed"] == 1, result
    assert result.get("reason") == "ok"
    assert _argv_log(log), "grok must run when Linear is in GROK_HOME"
    wrap = (state / "floor" / "mind" / "mail.txt").read_text(encoding="utf-8")
    assert "save_comment" in wrap.lower()
    assert "FLEET_DONE stamp LIV-82" in wrap
