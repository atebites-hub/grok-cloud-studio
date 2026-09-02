"""LIV-62 remaining: spawn --prompt-file is seat mind/mail.txt.

Executable binding for tests/features/liv62_pinned_mail_spawn.feature.

OPEN #95 owns validate_grok_mind_argv (construction clap). This slice is
the grok_cli_runner spawn hook: pin UUID + mail.txt path identity, refuse
latest-in-cwd and positional --print/-p. Does not remint #95.

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
FEATURE = REPO / "tests" / "features" / "liv62_pinned_mail_spawn.feature"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
GITMODULES = REPO / ".gitmodules"

GROK_MIND_MODEL = "grok-4.6"
GROK_MIND_REASONING_EFFORT = "xhigh"
_LAW_SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

SCENARIO_BINDINGS = {
    "Spawn --prompt-file is seat mind/mail.txt and pin matches session": (
        "test_scenario_spawn_prompt_file_is_seat_mail_txt"
    ),
    "Latest-in-cwd and --print are refused at spawn": (
        "test_scenario_spawn_refuses_latest_in_cwd_and_print"
    ),
}

HARVEST_MARKERS = (
    "format_mail_turn",
    "filter_inbound_mail",
    "MAIL_MAX_CHARS",
    "mail.in-flight",
)
LIV41_MARKERS = (
    "RUNNING >= 8",
    "RUNNING>=8",
    "must-launch",
    "must launch until RUNNING",
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


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> None:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-liv62-spawn-pin",
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


def _argv_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_fake_grok(tmp_path: Path, log: Path) -> Path:
    blob = json.dumps({"ok": True, "role": "assistant", "liv": "62-spawn"})
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
    mind = _load(MIND_PY, f"gcs_liv62_spawn_pin_{unique}")
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


def _law_argv(mail: Path, *, minted: bool, sid: str = _LAW_SID) -> list[str]:
    pin = ["--resume", sid] if minted else ["--session-id", sid]
    return [
        "grok",
        *pin,
        "--prompt-file",
        str(mail),
        "--verbatim",
        "--output-format",
        "json",
        "--always-approve",
        "--permission-mode",
        "bypassPermissions",
        "--max-turns",
        "40",
        "--model",
        GROK_MIND_MODEL,
        "--reasoning-effort",
        GROK_MIND_REASONING_EFFORT,
    ]


def test_bdd_feature_file_is_the_liv62_spawn_pin_example() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    assert text.startswith(
        "Feature: Grok mind spawn pins mind/session onto --prompt-file mail.txt"
    )
    low = text.lower()
    for needle in (
        "liv-62",
        "--prompt-file",
        "mind/mail.txt",
        "mind/session",
        "never bare -p",
        "grok-4.6",
        "xhigh",
        "--continue",
        "--fork-session",
        "--resume=-1",
        "--print",
        "positional",
        "validate_grok_mind_argv",
        "liv-85",
        "#81",
        "#61",
        "#67",
        "liv-41",
        "never bot cloudagent",
        "hermes-agent",
        "#26",
        "#28",
        "living sky",
    ):
        assert needle in low, needle
    titles = _gherkin_scenarios(text)
    assert titles == list(SCENARIO_BINDINGS)
    defined = set(globals())
    for title, fn_name in SCENARIO_BINDINGS.items():
        assert fn_name in defined, (title, fn_name)


def test_mind_doc_points_at_the_spawn_pin_bdd() -> None:
    doc = MIND_DOC.read_text(encoding="utf-8")
    assert "liv62_pinned_mail_spawn.feature" in doc


def test_does_not_vendor_hermes_or_clone_liv41_liv85() -> None:
    assert not (REPO / "vendor" / "hermes-agent").exists()
    gitmodules = GITMODULES.read_text(encoding="utf-8") if GITMODULES.is_file() else ""
    assert "hermes-agent" not in gitmodules
    src = MIND_PY.read_text(encoding="utf-8")
    for marker in HARVEST_MARKERS:
        assert marker not in src, marker
    for marker in LIV41_MARKERS:
        assert marker not in src, marker
    # Do not remint OPEN #95's construction guard name in this spawn slice.
    assert "assert_pinned_prompt_file_spawn" in src
    assert "GrokMindSpawnError" in src


def test_scenario_spawn_prompt_file_is_seat_mail_txt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="mailpath")
    _append_inbox(state, "floor", "task-spawn-1", "first mail mints the pin")
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    sid = _session_id(state, "floor")
    uuid.UUID(sid)
    mail = state / "floor" / "mind" / "mail.txt"
    assert mail.is_file()
    argv = _argv_log(log)[0]["argv"]
    assert "--prompt-file" in argv
    assert Path(_flag_value(argv, "--prompt-file")) == mail.resolve()
    assert "--session-id" in argv
    assert _flag_value(argv, "--session-id") == sid
    assert "--resume" not in argv
    assert "first mail mints the pin" in mail.read_text(encoding="utf-8")
    assert "first mail mints the pin" not in argv
    assert "-p" not in argv
    assert "--print" not in argv
    assert "--continue" not in argv
    assert "--fork-session" not in argv
    mind.assert_pinned_prompt_file_spawn(
        ["grok", *argv], session_id=sid, mail_path=mail
    )

    _append_inbox(state, "floor", "task-spawn-2", "second mail must resume")
    second = mind.process_once("floor")
    assert second["consumed"] == 1
    assert _session_id(state, "floor") == sid
    argv2 = _argv_log(log)[1]["argv"]
    assert Path(_flag_value(argv2, "--prompt-file")) == mail.resolve()
    assert "--resume" in argv2
    assert _flag_value(argv2, "--resume") == sid
    assert "--session-id" not in argv2
    assert "second mail must resume" not in argv2
    mind.assert_pinned_prompt_file_spawn(
        ["grok", *argv2], session_id=sid, mail_path=mail
    )


def test_scenario_spawn_refuses_latest_in_cwd_and_print(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind = _load(MIND_PY, "gcs_liv62_spawn_guard")
    mail = tmp_path / "mind-mail.txt"
    mail.write_text("inbox body\n", encoding="utf-8")
    other = tmp_path / "other.txt"
    other.write_text("not the seat mail\n", encoding="utf-8")
    law = _law_argv(mail, minted=True)
    mind.assert_pinned_prompt_file_spawn(
        law, session_id=_LAW_SID, mail_path=mail
    )
    first = _law_argv(mail, minted=False)
    mind.assert_pinned_prompt_file_spawn(
        first, session_id=_LAW_SID, mail_path=mail
    )

    with pytest.raises(mind.GrokMindSpawnError):
        mind.assert_pinned_prompt_file_spawn(
            law + ["--continue"], session_id=_LAW_SID, mail_path=mail
        )
    with pytest.raises(mind.GrokMindSpawnError):
        mind.assert_pinned_prompt_file_spawn(
            law + ["--fork-session"], session_id=_LAW_SID, mail_path=mail
        )
    with pytest.raises(mind.GrokMindSpawnError):
        mind.assert_pinned_prompt_file_spawn(
            ["grok", "-p", "--resume", _LAW_SID, "--prompt-file", str(mail)],
            session_id=_LAW_SID,
            mail_path=mail,
        )
    with pytest.raises(mind.GrokMindSpawnError):
        mind.assert_pinned_prompt_file_spawn(
            ["grok", "--print", "--resume", _LAW_SID, "--prompt-file", str(mail)],
            session_id=_LAW_SID,
            mail_path=mail,
        )
    glued = [
        "grok",
        f"--resume={_LAW_SID}",
        "--prompt-file",
        str(mail),
        "--model",
        GROK_MIND_MODEL,
        "--reasoning-effort",
        GROK_MIND_REASONING_EFFORT,
    ]
    # Matching glued UUID is ok; glued -1 is latest-in-cwd.
    mind.assert_pinned_prompt_file_spawn(
        glued, session_id=_LAW_SID, mail_path=mail
    )
    with pytest.raises(mind.GrokMindSpawnError):
        mind.assert_pinned_prompt_file_spawn(
            ["grok", "--resume=-1", "--prompt-file", str(mail)],
            session_id=_LAW_SID,
            mail_path=mail,
        )
    with pytest.raises(mind.GrokMindSpawnError):
        mind.assert_pinned_prompt_file_spawn(
            law + ["positional mail leaked onto argv"],
            session_id=_LAW_SID,
            mail_path=mail,
        )
    with pytest.raises(mind.GrokMindSpawnError):
        mind.assert_pinned_prompt_file_spawn(
            _law_argv(other, minted=True),
            session_id=_LAW_SID,
            mail_path=mail,
        )
    with pytest.raises(mind.GrokMindSpawnError):
        mind.assert_pinned_prompt_file_spawn(
            law, session_id="bbbbbbbb-cccc-dddd-eeee-ffffffffffff", mail_path=mail
        )


def test_runner_fail_closes_continue_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="mutcont")
    orig = mind.grok_cli_argv

    def _with_continue(**kwargs):
        return orig(**kwargs) + ["--continue"]

    monkeypatch.setattr(mind, "grok_cli_argv", _with_continue)
    _append_inbox(state, "floor", "task-mut-continue", "do not latest-in-cwd")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert _offset(state, "floor") == 0
    assert _argv_log(log) == []


def test_runner_fail_closes_wrong_prompt_file_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="mutpath")
    decoy = tmp_path / "decoy-mail.txt"
    decoy.write_text("decoy\n", encoding="utf-8")
    orig = mind.grok_cli_argv

    def _wrong_path(**kwargs):
        argv = orig(**kwargs)
        idx = argv.index("--prompt-file")
        argv[idx + 1] = str(decoy)
        return argv

    monkeypatch.setattr(mind, "grok_cli_argv", _wrong_path)
    _append_inbox(state, "floor", "task-mut-path", "mail must stay on mail.txt")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert _offset(state, "floor") == 0
    assert _argv_log(log) == []


def test_runner_fail_closes_positional_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, grok=grok, unique="mutpos")
    orig = mind.grok_cli_argv

    def _with_positional(**kwargs):
        return orig(**kwargs) + ["-p"]

    monkeypatch.setattr(mind, "grok_cli_argv", _with_positional)
    _append_inbox(state, "floor", "task-mut-p", "never bare -p")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert _offset(state, "floor") == 0
    assert _argv_log(log) == []
