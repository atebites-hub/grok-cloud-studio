"""LIV-63 remaining: Grok Build minds are grok-bot-like.

Executable binding for tests/features/liv63_mind_bot_like.feature.

Mailbox harvest must be a disk turn (Bot bot-wake analog) before the runner.
Spawn PATH remaining is Extra High + a2a_send, never Bot CloudAgent.

Does not vendor Hermes. Does not land harvest #26/#28 (envelope, defang,
heartbeat). Does not restack #47 cloud_list / cloud_followup. Does not
remint #61 SUBMITTED/COMPLETE or #41 send pin.

BDD: demonstrate, don't theatre. No LGTM without evidence.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "liv63_mind_bot_like.feature"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
TICKER_PY = REPO / "scripts" / "a2a" / "host-ticker.py"
HUB_PY = REPO / "scripts" / "a2a" / "hub.py"
BOT_LIKE_PY = REPO / "scripts" / "a2a" / "mind_bot_like.py"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
GITMODULES = REPO / ".gitmodules"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
A2A_DOC = REPO / "docs" / "A2A.md"
PRIVATE_GAME = "atebites-hub/" + "palemon"

HARVEST_MARKERS = (
    "format_mail_turn",
    "filter_inbound_mail",
    "MAIL_MAX_CHARS",
    "mind/heartbeat",
    "defang",
    "mail envelope",
)
PR47_RESTACK = ("cloud_list", "cloud_followup", "cloud_result", "cloud_status")
BANNED_SPAWN = ("Bot CloudAgent", "Grok Bot CloudAgent", "session/prompt")
SCENARIO_BINDINGS = {
    "Mailbox harvest writes a Bot-like turn file before the runner": (
        "test_scenario_mailbox_harvest_writes_bot_like_turn_before_runner"
    ),
    "Mind spawn PATH is Extra High, never Bot CloudAgent": (
        "test_scenario_mind_spawn_path_is_extra_high_never_bot_cloudagent"
    ),
    "Stay-up ticker includes opted-in mind seats as mailbox turns": (
        "test_scenario_ticker_includes_mind_seats_as_mailbox_turns"
    ),
    "Mind bus start keep-alives without ACP daemons": (
        "test_scenario_mind_bus_starts_ticker_without_acp_daemons"
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
        "contextId": "ctx-bot-like",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def _gherkin_scenarios(text: str) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Scenario:"):
            titles.append(stripped[len("Scenario:") :].strip())
    return titles


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_liv63_bot_like_{unique}")
    state = tmp_path / f"a2a-state-{unique}"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    return mind, state


def test_bdd_feature_file_is_the_remaining_liv63_example() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    assert text.startswith("Feature: Grok Build minds are grok-bot-like")
    low = text.lower()
    for needle in (
        "liv-63",
        "grok-bot-like",
        "mailbox harvest",
        "bot-wake",
        "extra high",
        "never bot cloudagent",
        "#26",
        "#28",
        "#47",
        "demonstrate",
        "don't theatre",
        "session/prompt",
    ):
        assert needle in low, needle
    assert PRIVATE_GAME not in text
    titles = _gherkin_scenarios(text)
    assert titles == list(SCENARIO_BINDINGS)
    defined = set(globals())
    for title, fn_name in SCENARIO_BINDINGS.items():
        assert fn_name in defined, (title, fn_name)


def test_remaining_module_is_new_not_a_harvest_restack() -> None:
    assert BOT_LIKE_PY.is_file(), (
        "remaining Hermes-port lives in scripts/a2a/mind_bot_like.py "
        "(new file; do not restack #47 mind.py plugins)"
    )
    src = BOT_LIKE_PY.read_text(encoding="utf-8")
    for marker in HARVEST_MARKERS:
        assert marker not in src, marker
    assert "hermes-agent" not in src.lower() or "do not vendor" in src.lower()
    assert "message_agent" not in src
    assert "plugin.yaml" not in src
    for banned in BANNED_SPAWN:
        assert banned not in src
    for restack in PR47_RESTACK:
        assert restack not in src, restack


def test_scenario_mailbox_harvest_writes_bot_like_turn_before_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="mailturn")
    body = "ship the remaining hive mechanic"
    runner_saw: list[dict[str, str]] = []

    def fake(prompt: str, **_kwargs: object) -> dict[str, str]:
        mail = state / "floor" / "mind" / "mail.txt"
        turn = state / "floor" / "mind" / "turn.txt"
        assert mail.is_file(), "mailbox-is-a-turn must write mail.txt before the runner"
        assert turn.is_file(), "grok-bot-like mind must write mind/turn.txt like bot-wake.txt"
        mail_text = mail.read_text(encoding="utf-8")
        turn_text = turn.read_text(encoding="utf-8")
        runner_saw.append({"prompt": prompt, "mail": mail_text, "turn": turn_text})
        return {"text": "ack from fake grok"}

    _append_inbox(state, "floor", "task-bot-like-1", body)
    result = mind.process_once("floor", runner=fake)
    assert result.get("consumed") == 1, result
    assert result.get("reason") == "ok"
    assert runner_saw, "runner must actually run the harvested mail line"
    saw = runner_saw[0]
    assert body in saw["prompt"]
    assert body in saw["mail"]
    assert body in saw["turn"]
    assert saw["prompt"] == saw["mail"].strip() or body in saw["mail"]
    assert "Message from" not in saw["prompt"]
    assert "[filtered]" not in saw["prompt"]
    assert "task=task-bot-like-1" in saw["turn"] or "taskId=task-bot-like-1" in saw["turn"]
    turn_jsonl = state / "floor" / "mind" / "turn.jsonl"
    assert turn_jsonl.is_file()
    row = json.loads(turn_jsonl.read_text(encoding="utf-8").splitlines()[-1])
    assert row.get("taskId") == "task-bot-like-1"
    assert body in str(row.get("text") or "")
    src = MIND_PY.read_text(encoding="utf-8")
    for banned in ("session/prompt", "acp_inject", "session/new"):
        assert banned not in src
    for marker in HARVEST_MARKERS:
        assert marker not in src, marker

    empty = mind.process_once("floor", runner=fake)
    assert empty.get("consumed") == 0
    assert empty.get("reason") == "empty"
    assert not (state / "floor" / "mind" / "session").is_file()
    assert not (state / "floor" / "mind" / "heartbeat").is_file()


def test_empty_harvest_does_not_invent_a_turn_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="emptyturn")
    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "empty"
    assert not (state / "floor" / "mind" / "mail.txt").is_file()
    assert not (state / "floor" / "mind" / "turn.txt").is_file()
    assert not (state / "floor" / "mind" / "turn.jsonl").is_file()
    assert not (state / "floor" / "mind" / "session").is_file()
    assert not (state / "floor" / "mind" / "heartbeat").is_file()


def test_scenario_mind_spawn_path_is_extra_high_never_bot_cloudagent(
    tmp_path: Path,
) -> None:
    assert BOT_LIKE_PY.is_file()
    bot_like = _load(BOT_LIKE_PY, "gcs_liv63_bot_like_spawn")
    grok_home = tmp_path / "grok-home"
    home = tmp_path / "home"
    bot_like.install_mind_spawn_path(root=REPO, grok_home=grok_home, home=home)
    launch_wrap = grok_home / "bin" / "cloud_launch"
    send_wrap = grok_home / "bin" / "a2a_send"
    assert launch_wrap.is_file(), "remaining spawn path: cloud_launch on mind GROK_HOME/bin"
    assert send_wrap.is_file(), "grok-bot-like reply: a2a_send on mind GROK_HOME/bin"
    launch_txt = launch_wrap.read_text(encoding="utf-8")
    send_txt = send_wrap.read_text(encoding="utf-8")
    assert "launch-cloud-extra-high.sh" in launch_txt
    assert "send.sh" in send_txt
    for blob in (launch_txt, send_txt):
        for banned in BANNED_SPAWN:
            assert banned not in blob
        assert "watch-cloud-agent" not in blob
        assert "config.toml" not in blob
        assert ".cursor/mcp.json" not in blob
    for restack in ("cloud_list", "cloud_followup", "cloud_result", "cloud_status", "cloud_watch"):
        assert not (grok_home / "bin" / restack).exists(), restack
    home_launch = home / ".grok" / "bin" / "cloud_launch"
    assert home_launch.is_file()
    assert LAUNCH.is_file()
    launch_src = LAUNCH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch_src
    loop = MIND_LOOP.read_text(encoding="utf-8")
    assert "mind_bot_like.py" in loop
    assert "install-spawn" in loop or "install_mind_spawn_path" in loop
    assert "acp_inject" not in loop
    assert "session/prompt" not in loop


def test_spawn_wrappers_are_executable_and_forward_argv(tmp_path: Path) -> None:
    bot_like = _load(BOT_LIKE_PY, "gcs_liv63_bot_like_argv")
    grok_home = tmp_path / "grok-home"
    home = tmp_path / "home"
    scripts = tmp_path / "scripts"
    _write_exec(
        scripts / "launch-cloud-extra-high.sh",
        "#!/bin/sh\nprintf 'LAUNCH_ARGV:%s\\n' \"$*\"\n",
    )
    _write_exec(
        scripts / "a2a" / "send.sh",
        "#!/bin/sh\nprintf 'SEND_ARGV:%s\\n' \"$*\"\n",
    )
    bot_like.install_mind_spawn_path(root=tmp_path, grok_home=grok_home, home=home)
    launch = subprocess.run(
        ["bash", str(grok_home / "bin" / "cloud_launch"), "--name", "grunt-x", "do the work"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    send = subprocess.run(
        ["bash", str(grok_home / "bin" / "a2a_send"), "--from", "floor", "ops", "ping"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert launch.returncode == 0, launch.stdout + launch.stderr
    assert send.returncode == 0, send.stdout + send.stderr
    assert "LAUNCH_ARGV:--name grunt-x do the work" in launch.stdout
    assert "SEND_ARGV:--from floor ops ping" in send.stdout


def test_scenario_ticker_includes_mind_seats_as_mailbox_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticker = _load(TICKER_PY, "gcs_liv63_bot_like_ticker")
    state = tmp_path / "ticker-state"
    monkeypatch.setattr(ticker, "STATE_DIR", state)
    monkeypatch.setattr(ticker, "ROOT", REPO)
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_MIND_SEATS", "audio")
    monkeypatch.setenv("GCS_GROW_SEATS", "floor")
    monkeypatch.setenv("GCS_ACP_SEATS", "floor")
    monkeypatch.delenv("GCS_WAKE_SEATS", raising=False)
    n = ticker.tick_once()
    assert n >= 1, "default tick set must include opted-in mind seats"
    audio_inbox = state / "audio" / "inbox.jsonl"
    assert audio_inbox.is_file(), "mind seat outside leftover GROW still gets mailbox keep-alive"
    rec = json.loads(audio_inbox.read_text(encoding="utf-8").splitlines()[-1])
    text = ""
    for part in rec.get("parts") or []:
        if isinstance(part, dict) and part.get("text"):
            text += str(part["text"])
    assert "ACP_PING" in text or "STATUS" in text
    assert str(rec.get("kind") or "").lower() != "launch"
    src = TICKER_PY.read_text(encoding="utf-8")
    assert "acp_inject" not in src
    assert "session/prompt" not in src
    assert "mind_seats" in src or "default_tick_seats" in src or "mind_bot_like" in src
    hub = HUB_PY.read_text(encoding="utf-8")
    assert "TASK_STATE_COMPLETED" in hub
    assert "format_mail_turn" not in hub


def test_scenario_mind_bus_starts_ticker_without_acp_daemons() -> None:
    bus = BUS_SH.read_text(encoding="utf-8")
    assert "start_mind_daemons" in bus
    start_parts = bus.split("\n  start)\n", 1)
    assert len(start_parts) == 2, "start-studio-bus.sh start) branch"
    start_body = start_parts[1].split("\n  stop)\n", 1)[0]
    assert "start_mind_daemons" in start_body
    assert "start_host_ticker" in start_body, (
        "grok-bot-like stay-up: ticker must start for mind seats even without --daemons"
    )
    before_daemons, _after = start_body.split("want_daemons", 1)
    assert "start_host_ticker" in before_daemons
    assert "STUDIO_BUS_DAEMONS_SKIP" in start_body


def test_mind_bus_start_live_ticker_pid_without_daemons(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "GCS_MIND_SEATS",
            "GCS_START_SEAT_DAEMONS",
            "GCS_ACP_STOP_WITH_BUS",
            "GCS_MIND_PLUS_ACP_WAKE",
        }
    }
    env.update(
        {
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(state),
            "GCS_MIND_SEATS": "floor",
            "GCS_START_SEAT_DAEMONS": "0",
            "GCS_ACP_STOP_WITH_BUS": "1",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LC_ALL": "C",
            "TERM": "dumb",
        }
    )
    try:
        proc = subprocess.run(
            ["bash", str(BUS_SH), "start"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
        )
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "STUDIO_BUS_TICKER_START" in blob or "STUDIO_BUS_TICKER_ALREADY" in blob
        assert "STUDIO_BUS_DAEMONS_SKIP" in blob
        pid_file = state / "host-ticker.pid"
        assert pid_file.is_file(), blob
        pid = int(pid_file.read_text(encoding="utf-8").strip().split()[0])
        os.kill(pid, 0)
    finally:
        subprocess.run(
            ["bash", str(BUS_SH), "stop"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
        )


def test_do_not_vendor_hermes_or_land_conflicting_harvest() -> None:
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
    plugins = _load(MIND_PY, "gcs_liv63_bot_like_plugins").PLUGINS
    assert "cloud_launch" in plugins
    assert "a2a_send" in plugins
    for restack in PR47_RESTACK:
        assert restack not in plugins, restack
    assert PRIVATE_GAME not in mind
    assert PRIVATE_GAME not in FEATURE.read_text(encoding="utf-8")


def test_docs_name_the_remaining_grok_bot_like_mechanic() -> None:
    mind_doc = MIND_DOC.read_text(encoding="utf-8")
    a2a = A2A_DOC.read_text(encoding="utf-8")
    blob = mind_doc + "\n" + a2a
    assert "liv63_mind_bot_like.feature" in blob or "grok-bot-like" in blob.lower()
    assert "mind/turn.txt" in blob or "Bot-like" in blob or "bot-like" in blob.lower()
    assert "cloud_launch" in blob
    assert PRIVATE_GAME not in mind_doc
    assert "palemon" not in mind_doc.lower()
