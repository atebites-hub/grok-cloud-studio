"""LIV-63 BDD: Hermes mail-as-a-turn is grok mind, not ACP overlay.

Executable binding for tests/features/liv63_hermes_mail_as_turn.feature.
Does not vendor Hermes. Does not land harvest mailbox PRs #26 and #28.
Living Sky only. Never Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "liv63_hermes_mail_as_turn.feature"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
DISPATCH_PY = REPO / "scripts" / "a2a" / "dispatch.py"
HUB_PY = REPO / "scripts" / "a2a" / "hub.py"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
CLOUD_COMMON = REPO / "scripts" / "cloud" / "sdk" / "common.ts"
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
    "An A2A inbox line is one grok --prompt-file turn": (
        "test_scenario_inbox_line_is_one_grok_prompt_file_turn"
    ),
    "Opted-in mind seats skip leftover ACP overlay": (
        "test_scenario_mind_seats_skip_leftover_acp_overlay"
    ),
    "Command-center spawn is Extra High, never Bot CloudAgent": (
        "test_scenario_command_center_spawn_is_extra_high_not_bot_cloudagent"
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
        "contextId": "ctx-liv63",
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
    blob = json.dumps({"ok": True, "role": "assistant", "liv": "63"})
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


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    grok: Path,
    unique: str,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_liv63_bdd_{unique}")
    state = tmp_path / f"a2a-state-{unique}"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    monkeypatch.delenv("GCS_CURSOR_BIN", raising=False)
    return mind, state


def _gherkin_scenarios(text: str) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Scenario:"):
            titles.append(stripped[len("Scenario:") :].strip())
    return titles


def test_bdd_feature_file_is_the_liv63_example() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    assert text.startswith("Feature: Hermes mail-as-a-turn on Grok Cloud Studio")
    low = text.lower()
    for needle in (
        "liv-63",
        "mail-as-a-turn",
        "grok mind",
        "not leftover acp overlay",
        "do not vendor",
        "hermes-agent",
        "#26",
        "#28",
        "grok-4.6",
        "xhigh",
        "never bot cloudagent",
        "living sky",
        "--prompt-file",
        "mind-owns-inbox",
    ):
        assert needle in low, needle
    assert PRIVATE_GAME not in text
    assert "vendor/hermes-agent" in text
    titles = _gherkin_scenarios(text)
    assert titles == list(SCENARIO_BINDINGS)
    defined = set(globals())
    for title, fn_name in SCENARIO_BINDINGS.items():
        assert fn_name in defined, (title, fn_name)


def test_mind_doc_points_at_the_bdd_example() -> None:
    doc = MIND_DOC.read_text(encoding="utf-8")
    assert "liv63_hermes_mail_as_turn.feature" in doc
    assert "LIV-63" in doc or "liv-63" in doc.lower()


def test_scenario_inbox_line_is_one_grok_prompt_file_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="mail")
    _append_inbox(state, "floor", "task-liv63-mail", "ship the hive upgrade")
    assert _offset(state, "floor") == 0
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"
    assert _offset(state, "floor") > 0
    sid = _session_id(state, "floor")
    uuid.UUID(sid)
    rows = json.loads(log.read_text(encoding="utf-8"))
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
    assert "ship the hive upgrade" in mail.read_text(encoding="utf-8")
    assert _flag_value(argv, "--model") == GROK_MIND_MODEL
    assert _flag_value(argv, "--reasoning-effort") == GROK_MIND_REASONING_EFFORT
    assert "--session-id" in argv
    assert _flag_value(argv, "--session-id") == sid
    assert "--resume" not in argv
    src = MIND_PY.read_text(encoding="utf-8")
    for banned in ("session/prompt", "acp_inject", "session/new"):
        assert banned not in src


def test_scenario_mind_seats_skip_leftover_acp_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bus = BUS_SH.read_text(encoding="utf-8")
    loop = MIND_LOOP.read_text(encoding="utf-8")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    for blob in (mind_src, loop):
        assert "acp_inject" not in blob
        assert "session/prompt" not in blob
    assert "STUDIO_BUS_WAKE_SKIP" in bus
    assert "reason=mind-owns-inbox" in bus
    assert "GCS_MIND_PLUS_ACP_WAKE" in bus

    scripts_a2a = REPO / "scripts" / "a2a"
    lib_src, _rest = bus.split("\nWITH_DAEMONS=0", 1)
    lib_src = lib_src.replace(
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        f'SCRIPT_DIR="{scripts_a2a}"',
        1,
    )
    state = tmp_path / "wake-state"
    state.mkdir(parents=True)
    harness = tmp_path / "wake-skip.sh"
    harness.write_text(lib_src + "\nstart_wake_daemons\n", encoding="utf-8")
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "GCS_MIND_SEATS",
            "GCS_WAKE_SEATS",
            "GCS_GROW_SEATS",
            "GCS_ACP_SEATS",
            "GCS_MIND_PLUS_ACP_WAKE",
            "GCS_START_SEAT_DAEMONS",
        }
    }
    env.update(
        {
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(state),
            "GCS_MIND_SEATS": "floor",
            "GCS_WAKE_SEATS": "floor",
            "GCS_MIND_PLUS_ACP_WAKE": "0",
            "GCS_START_SEAT_DAEMONS": "0",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LC_ALL": "C",
            "TERM": "dumb",
        }
    )
    proc = subprocess.run(
        ["bash", str(harness)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "STUDIO_BUS_WAKE_SKIP seat=floor reason=mind-owns-inbox" in blob
    assert "STUDIO_BUS_WAKE_START" not in blob
    assert not (state / "floor" / "wake.pid").exists()

    monkeypatch.delenv("GCS_MIND_SEATS", raising=False)
    dispatch = _load(DISPATCH_PY, "gcs_liv63_bdd_dispatch")
    inject_stamp = tmp_path / "inject.extra"
    fake_inject = _write_exec(
        tmp_path / "fake_acp_inject.py",
        "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
        f"Path({str(inject_stamp)!r}).write_text(sys.argv[-1], encoding='utf-8')\n",
    )
    monkeypatch.setattr(dispatch, "STATE_DIR", state)
    monkeypatch.setattr(dispatch, "ACP_INJECT", fake_inject)
    monkeypatch.setattr(dispatch, "GROW_SEATS", frozenset())
    monkeypatch.setattr(dispatch, "_daemon_healthy", lambda seat: True)
    monkeypatch.setattr(dispatch, "_ensure_daemon", lambda seat: True)
    monkeypatch.setattr(dispatch, "_CHILDREN", {})
    monkeypatch.setenv("GCS_MIND_SEATS", "floor")
    _append_inbox(state, "floor", "task-liv63-skip-acp", "LAUNCH ONLY do not inject")
    started = dispatch._process_seat("floor", dry_run=False)
    assert started == 0
    assert not inject_stamp.is_file()
    out = capsys.readouterr().out
    assert "DISPATCH_SKIP seat=floor reason=mind-owns-inbox" in out


def test_scenario_command_center_spawn_is_extra_high_not_bot_cloudagent() -> None:
    mind = _load(MIND_PY, "gcs_liv63_bdd_plugins")
    assert "cloud_launch" in mind.PLUGINS
    launch = LAUNCH.read_text(encoding="utf-8")
    common = CLOUD_COMMON.read_text(encoding="utf-8")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    assert "launch-cloud-extra-high.sh" in mind_src
    assert "grok-4.6" in launch
    assert 'id: "grok-4.6"' in common
    assert 'value: "xhigh"' in common
    assert 'value: "false"' in common
    for path in (LAUNCH, CLOUD_COMMON, MIND_PY):
        text = path.read_text(encoding="utf-8")
        assert "Bot CloudAgent" not in text
        assert "Grok Bot CloudAgent" not in text


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
    assert '"state": TASK_STATE_COMPLETED' in hub
    send_fn = hub.split("if action == \"message-send\"", 1)[1]
    assert "TASK_STATE_COMPLETED" in send_fn.split("def ", 1)[0]
    assert "TASK_STATE_SUBMITTED" not in send_fn.split("artifacts", 1)[0]
    assert PRIVATE_GAME not in mind
    assert PRIVATE_GAME not in FEATURE.read_text(encoding="utf-8")
