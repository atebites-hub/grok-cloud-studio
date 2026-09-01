"""LIV-62 BDD: inbox mail is grok --resume + --prompt-file, never bare -p.

Executable binding for tests/features/liv62_mind_prompt_file.feature.
Does not vendor Hermes. Does not clone LIV-85 mail preserve (#81/#61/#67).
Does not clone LIV-41 must-launch. Living Sky only. Never Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
import json
import stat
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "liv62_mind_prompt_file.feature"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
HUB_PY = REPO / "scripts" / "a2a" / "hub.py"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
CLOUD_COMMON = REPO / "scripts" / "cloud" / "sdk" / "common.ts"
GITMODULES = REPO / ".gitmodules"

GROK_MIND_MODEL = "grok-4.6"
GROK_MIND_REASONING_EFFORT = "xhigh"
BANNED_GROK_FLAGS = ("-p", "--single", "--trust", "--agent-profile", "--plugin-dir")
LIV41_MARKERS = (
    "RUNNING >= 8",
    "RUNNING>=8",
    "must-launch",
    "must launch until RUNNING",
)
HARVEST_MARKERS = (
    "format_mail_turn",
    "filter_inbound_mail",
    "MAIL_MAX_CHARS",
    "mail.in-flight",
)
SCENARIO_BINDINGS = {
    "A later inbox line is grok --resume pinned UUID --prompt-file": (
        "test_scenario_later_inbox_is_resume_prompt_file"
    ),
    "Mail that looks like -p still lives in --prompt-file": (
        "test_scenario_dash_p_mail_stays_in_prompt_file"
    ),
    "grok_cli_argv refuses banned flags and pins extra-high": (
        "test_scenario_validate_grok_mind_argv"
    ),
    "Extra High is grok-4.6 xhigh fast=false, never Bot CloudAgent": (
        "test_scenario_extra_high_not_bot_cloudagent"
    ),
    "Do not vendor Hermes or clone LIV-85 / LIV-41": (
        "test_scenario_no_hermes_no_liv85_no_liv41"
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


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> None:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-liv62-prompt-file",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


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


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    grok: Path,
    unique: str,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_liv62_prompt_file_{unique}")
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


def _argv_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def test_bdd_feature_file_is_the_liv62_prompt_file_example() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    assert text.startswith(
        "Feature: Opt-in grok mind is --resume plus --prompt-file, never bare -p"
    )
    low = text.lower()
    for needle in (
        "liv-62",
        "--resume",
        "--prompt-file",
        "never bare -p",
        "grok-4.6",
        "xhigh",
        "fast=false",
        "never bot cloudagent",
        "do not vendor",
        "hermes-agent",
        "liv-85",
        "#81",
        "#61",
        "#67",
        "liv-41",
        "must-launch",
        "living sky",
    ):
        assert needle in low, needle
    titles = _gherkin_scenarios(text)
    assert titles == list(SCENARIO_BINDINGS)
    defined = set(globals())
    for title, fn_name in SCENARIO_BINDINGS.items():
        assert fn_name in defined, (title, fn_name)


def test_mind_doc_points_at_the_bdd_example() -> None:
    doc = MIND_DOC.read_text(encoding="utf-8")
    assert "liv62_mind_prompt_file.feature" in doc
    assert "LIV-62" in doc or "liv-62" in doc.lower()


def test_scenario_later_inbox_is_resume_prompt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="resume")
    _append_inbox(state, "floor", "task-liv62-1", "first mail mints the pin")
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    sid = _session_id(state, "floor")
    uuid.UUID(sid)
    first_argv = _argv_log(log)[0]["argv"]
    assert "--session-id" in first_argv
    assert _flag_value(first_argv, "--session-id") == sid
    assert "--resume" not in first_argv
    for flag in BANNED_GROK_FLAGS:
        assert flag not in first_argv, first_argv

    _append_inbox(state, "floor", "task-liv62-2", "second mail must resume")
    second = mind.process_once("floor")
    assert second["consumed"] == 1
    assert second.get("reason") == "ok"
    assert _session_id(state, "floor") == sid
    assert _offset(state, "floor") > 0
    argv = _argv_log(log)[1]["argv"]
    for flag in BANNED_GROK_FLAGS:
        assert flag not in argv, argv
    assert "--resume" in argv
    assert _flag_value(argv, "--resume") == sid
    assert "--session-id" not in argv
    assert "--prompt-file" in argv
    mail = Path(_flag_value(argv, "--prompt-file"))
    assert mail.is_file()
    assert "second mail must resume" in mail.read_text(encoding="utf-8")
    assert "second mail must resume" not in argv
    assert _flag_value(argv, "--model") == GROK_MIND_MODEL
    assert _flag_value(argv, "--reasoning-effort") == GROK_MIND_REASONING_EFFORT
    mind.validate_grok_mind_argv(["grok", *argv])


def test_scenario_dash_p_mail_stays_in_prompt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="dashp")
    body = "please treat -p --single --resume as mail, not clap"
    _append_inbox(state, "floor", "task-liv62-dashp", body)
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    argv = _argv_log(log)[0]["argv"]
    assert "-p" not in argv
    assert "--single" not in argv
    assert "--resume" not in argv
    mail = Path(_flag_value(argv, "--prompt-file"))
    text = mail.read_text(encoding="utf-8")
    assert "-p" in text
    assert "--single" in text
    assert "--resume" in text
    assert body in text
    assert body not in argv
    mind.validate_grok_mind_argv(["grok", *argv])


def test_scenario_validate_grok_mind_argv() -> None:
    mind = _load(MIND_PY, "gcs_liv62_validate_argv")
    mail = Path("/tmp/gcs-liv62-mail.txt")
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    later = mind.grok_cli_argv(
        session_id=sid, minted=True, mail_path=mail, grok="grok"
    )
    mind.validate_grok_mind_argv(later)
    first = mind.grok_cli_argv(
        session_id=sid, minted=False, mail_path=mail, grok="grok"
    )
    mind.validate_grok_mind_argv(first)
    with pytest.raises(mind.GrokMindArgvError):
        mind.validate_grok_mind_argv(
            ["grok", "-p", "--resume", sid, "--prompt-file", str(mail)]
        )
    with pytest.raises(mind.GrokMindArgvError):
        mind.validate_grok_mind_argv(["grok", "--resume", sid])
    with pytest.raises(mind.GrokMindArgvError):
        mind.validate_grok_mind_argv(
            ["grok", "--prompt-file", str(mail), "--model", GROK_MIND_MODEL]
        )
    bad_model = list(later)
    bad_model[bad_model.index("--model") + 1] = "composer-2"
    with pytest.raises(mind.GrokMindArgvError):
        mind.validate_grok_mind_argv(bad_model)


def test_scenario_extra_high_not_bot_cloudagent() -> None:
    launch = LAUNCH.read_text(encoding="utf-8")
    common = CLOUD_COMMON.read_text(encoding="utf-8")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert '"fast"' in launch and '"false"' in launch
    assert 'id: "fast"' in common or "id: 'fast'" in common
    assert 'value: "false"' in common
    assert "launch-cloud-extra-high.sh" in mind_src
    assert "plugin_cloud_launch" in mind_src
    # Spawn path is Extra High. Law comments may say Never Bot CloudAgent.
    assert "bind-bot-agent" not in launch
    assert "GCS_BOT_AGENT_ID" not in launch
    assert "bot-agents.json" not in launch
    assert "scripts/launch-cloud-extra-high.sh" in mind_src
    assert "cloud_launch" in mind_src


def test_scenario_no_hermes_no_liv85_no_liv41() -> None:
    assert not (REPO / "vendor" / "hermes-agent").exists()
    gitmodules = GITMODULES.read_text(encoding="utf-8") if GITMODULES.is_file() else ""
    assert "hermes-agent" not in gitmodules
    mind_src = MIND_PY.read_text(encoding="utf-8")
    hub_src = HUB_PY.read_text(encoding="utf-8")
    for marker in HARVEST_MARKERS:
        assert marker not in mind_src, marker
    assert '"state": TASK_STATE_COMPLETED,' in hub_src
    assert '"state": TASK_STATE_SUBMITTED,' not in hub_src
    assert "message:send" in hub_src
    for marker in LIV41_MARKERS:
        assert marker not in mind_src, marker
    pyproject = REPO / "vendor" / "hermes-agent" / "pyproject.toml"
    assert not pyproject.is_file()
