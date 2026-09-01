"""LIV-62 remaining after #47: Hermes pin + stay-up is grok mind.

Executable binding for tests/features/liv62_hermes_pin_stay_up.feature.
Does not vendor Hermes. Does not land harvest mailbox PRs #26 and #28.
Living Sky only. Never Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "liv62_hermes_pin_stay_up.feature"
REMAINING = REPO / "docs" / "studio" / "HERMES_REMAINING.md"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
HUB_PY = REPO / "scripts" / "a2a" / "hub.py"
GITMODULES = REPO / ".gitmodules"
PRIVATE_GAME = "atebites-hub/" + "palemon"

GROK_MIND_MODEL = "grok-4.6"
GROK_MIND_REASONING_EFFORT = "xhigh"
BANNED_ACP = ("session/prompt", "acp_inject", "session/new", "pin-session")
BANNED_GROK_FLAGS = ("-p", "--single", "--trust", "--agent-profile", "--plugin-dir")
HARVEST_MARKERS = (
    "format_mail_turn",
    "filter_inbound_mail",
    "MAIL_MAX_CHARS",
    "mind/heartbeat",
    "defang",
    "mail envelope",
)
SCENARIO_BINDINGS = {
    "Empty harvest pins mind/session once and does not remint": (
        "test_scenario_empty_harvest_pins_session_once"
    ),
    "First mail after idle pin uses that UUID": (
        "test_scenario_first_mail_after_idle_pin_uses_that_uuid"
    ),
    "Stay-up empty ticks do not invent a mail turn": (
        "test_scenario_stay_up_empty_does_not_invent_mail_turn"
    ),
    "Do not vendor Hermes or land harvest PRs 26 and 28": (
        "test_scenario_do_not_vendor_hermes_or_land_harvest_prs"
    ),
}


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


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> Path:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-liv62",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def _offset(state: Path, seat: str) -> int:
    path = state / seat / "mind" / "offset"
    if not path.is_file():
        return 0
    return int(path.read_text(encoding="utf-8").strip() or "0")


def _session_id(state: Path, seat: str) -> str:
    path = state / seat / "mind" / "session"
    assert path.is_file(), "pinned session UUID missing"
    return path.read_text(encoding="utf-8").strip()


def _flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def _write_fake_grok(tmp_path: Path, log: Path) -> Path:
    blob = json.dumps({"ok": True, "role": "assistant", "liv": "62"})
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:], 'cwd': os.getcwd()})\n"
        "log.write_text(json.dumps(rows))\n"
        f"sys.stdout.write({blob!r})\n"
        "raise SystemExit(0)\n"
    )
    return _write_exec(tmp_path / "fake-bin" / "grok", script)


def _argv_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    grok: Path,
    unique: str,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_liv62_bdd_{unique}")
    state = tmp_path / f"a2a-state-{unique}"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    monkeypatch.delenv("GCS_CURSOR_BIN", raising=False)
    orig_home = mind.grok_home_dir

    def _grok_home_with_linear(seat: str) -> Path:
        d = orig_home(seat)
        cfg = d / "config.toml"
        if not cfg.is_file():
            cfg.write_text(
                "[mcp_servers.linear]\n"
                f'url = "{mind.LINEAR_MCP_URL}"\n'
                'headers = { Authorization = "Bearer ${LINEAR_API_KEY}" }\n',
                encoding="utf-8",
            )
        return d

    monkeypatch.setattr(mind, "grok_home_dir", _grok_home_with_linear)
    return mind, state


def _gherkin_scenarios(text: str) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Scenario:"):
            titles.append(stripped[len("Scenario:") :].strip())
    return titles


def test_bdd_feature_file_is_the_liv62_remaining_example() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    assert text.startswith("Feature: Hermes session pin on Grok Cloud Studio stay-up")
    low = text.lower()
    for needle in (
        "liv-62",
        "after",
        "#47",
        "pin",
        "stay-up",
        "empty harvest",
        "does not remint",
        "grok mind",
        "do not vendor",
        "hermes-agent",
        "#26",
        "#28",
        "grok-4.6",
        "xhigh",
        "never bot cloudagent",
        "living sky",
        "--session-id",
        "--resume",
        "mind/heartbeat",
    ):
        assert needle in low, needle
    assert PRIVATE_GAME not in text
    assert "vendor/hermes-agent" in text
    titles = _gherkin_scenarios(text)
    assert titles == list(SCENARIO_BINDINGS)
    defined = set(globals())
    for title, fn_name in SCENARIO_BINDINGS.items():
        assert fn_name in defined, (title, fn_name)


def test_docs_point_at_the_remaining_pin_example() -> None:
    assert REMAINING.is_file(), REMAINING
    remaining = REMAINING.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    blob = remaining + "\n" + mind
    low = blob.lower()
    assert "liv-62" in low
    assert "liv62_hermes_pin_stay_up.feature" in blob
    assert "#47" in blob
    assert "empty harvest" in low
    assert "do not remint" in low or "does not remint" in low
    assert "do not vendor" in low or "does not vendor" in low
    assert "nousresearch/hermes-agent" in low
    assert "#26" in blob and "#28" in blob
    assert "mind/heartbeat" in remaining
    assert PRIVATE_GAME not in remaining
    assert PRIVATE_GAME not in mind
    assert "palemon" not in remaining.lower()
    arch = (REPO / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "HERMES_REMAINING.md" in arch or "liv62_hermes_pin_stay_up.feature" in arch


def test_scenario_empty_harvest_pins_session_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="empty")
    first = mind.process_once("floor")
    assert first["consumed"] == 0
    assert first.get("reason") == "empty"
    sid = _session_id(state, "floor")
    uuid.UUID(sid)
    assert _offset(state, "floor") == 0
    assert not (state / "floor" / "mind" / "session.minted").is_file()
    assert _argv_log(log) == []
    second = mind.process_once("floor")
    assert second["consumed"] == 0
    assert _session_id(state, "floor") == sid
    assert _offset(state, "floor") == 0
    assert _argv_log(log) == []
    src = MIND_PY.read_text(encoding="utf-8")
    assert "load_or_create_session" in src
    assert "process_once" in src


def test_scenario_first_mail_after_idle_pin_uses_that_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="mail")
    idle = mind.process_once("floor")
    assert idle["consumed"] == 0
    sid = _session_id(state, "floor")
    uuid.UUID(sid)
    _append_inbox(state, "floor", "task-liv62-pin", "pin stay-up after idle")
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    assert first.get("reason") == "ok"
    assert _session_id(state, "floor") == sid
    rows = _argv_log(log)
    assert len(rows) == 1
    argv = rows[0]["argv"]
    for flag in BANNED_GROK_FLAGS:
        assert flag not in argv, argv
    for banned in BANNED_ACP:
        assert banned not in argv
        assert banned not in " ".join(argv)
    assert "--prompt-file" in argv
    mail = Path(_flag_value(argv, "--prompt-file"))
    assert mail.is_file()
    assert "pin stay-up after idle" in mail.read_text(encoding="utf-8")
    assert _flag_value(argv, "--model") == GROK_MIND_MODEL
    assert _flag_value(argv, "--reasoning-effort") == GROK_MIND_REASONING_EFFORT
    assert "--session-id" in argv
    assert _flag_value(argv, "--session-id") == sid
    assert "--resume" not in argv
    _append_inbox(state, "floor", "task-liv62-pin-2", "second mail same pin")
    later = mind.process_once("floor")
    assert later["consumed"] == 1
    assert _session_id(state, "floor") == sid
    argv2 = _argv_log(log)[1]["argv"]
    assert "--resume" in argv2
    assert _flag_value(argv2, "--resume") == sid
    assert "--session-id" not in argv2
    assert _flag_value(argv2, "--model") == GROK_MIND_MODEL


def test_scenario_stay_up_empty_does_not_invent_mail_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="nomail")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    mind_dir = state / "floor" / "mind"
    assert mind_dir.is_dir()
    assert (mind_dir / "session").is_file()
    assert not (mind_dir / "mail.txt").is_file()
    assert not (mind_dir / "turn.txt").is_file()
    assert not (mind_dir / "transcript.jsonl").is_file()
    assert _argv_log(log) == []
    src = MIND_PY.read_text(encoding="utf-8")
    loop = (REPO / "scripts" / "directors" / "seat-mind-loop.sh").read_text(encoding="utf-8")
    for blob in (src, loop):
        for banned in ("session/prompt", "acp_inject", "session/new"):
            assert banned not in blob


def test_scenario_do_not_vendor_hermes_or_land_harvest_prs() -> None:
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert not (REPO / "vendor" / "hermes").exists()
    modules = GITMODULES.read_text(encoding="utf-8")
    assert "hermes-agent" not in modules
    assert "tcarac/taskboard" in modules
    mind = MIND_PY.read_text(encoding="utf-8")
    hub = HUB_PY.read_text(encoding="utf-8")
    blob = mind + "\n" + hub
    for marker in HARVEST_MARKERS:
        assert marker not in blob, marker
    assert "message_agent.py" not in mind
    assert "plugin.yaml" not in mind
    send_fn = hub.split('if action == "message-send"', 1)[1]
    # LIV-85 already on main: enqueue SUBMITTED until harvest. Do not remint #26/#28.
    assert "TASK_STATE_SUBMITTED" in send_fn.split("def ", 1)[0]
    assert "format_mail_turn" not in send_fn
    assert PRIVATE_GAME not in mind
    assert PRIVATE_GAME not in FEATURE.read_text(encoding="utf-8")
    remaining = REMAINING.read_text(encoding="utf-8")
    assert "format_mail_turn" not in mind
    assert "not this pr" in remaining.lower() or "do not land" in remaining.lower()
