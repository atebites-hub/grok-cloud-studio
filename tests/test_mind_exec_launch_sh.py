"""Unique remaining: Grok Build mind Extra High spawn execs the launcher.

Grok Build mind Extra High spawn must exec scripts/launch-cloud-extra-high.sh
(or cloud_launch). Never Bot CloudAgent. Never grok --resume for Cloud create.
Do not vendor Hermes. Do not merge harvest mailbox PRs #26 and #28.
Model grok-4.6 xhigh.

Executable binding for tests/features/mind_exec_launch_sh.feature.
Does not restack LIV-63 mailbox harvest. Does not restack #47 cloud_list.
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
FEATURE = REPO / "tests" / "features" / "mind_exec_launch_sh.feature"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
BOT_LIKE_PY = REPO / "scripts" / "a2a" / "mind_bot_like.py"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
LAUNCH_TS = REPO / "scripts" / "cloud" / "sdk" / "launch.ts"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
AGENTS_DOC = REPO / "AGENTS.md"
GITMODULES = REPO / ".gitmodules"
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
SCENARIO_BINDINGS = {
    "Mailbox wrap names Extra High spawn as launch-cloud-extra-high.sh": (
        "test_scenario_wrap_mind_mail_names_extra_high_spawn"
    ),
    "cloud_launch plugin execs the Extra High launcher": (
        "test_scenario_cloud_launch_plugin_execs_launcher"
    ),
    "Mind spawn PATH wrapper execs the Extra High launcher": (
        "test_scenario_spawn_wrapper_execs_launcher"
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


def _gherkin_scenarios(text: str) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Scenario:"):
            titles.append(stripped[len("Scenario:") :].strip())
    return titles


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> Path:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-exec-launch",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def _git_mode(rel: str) -> str:
    out = subprocess.check_output(
        ["git", "ls-files", "-s", rel],
        cwd=str(REPO),
        text=True,
        timeout=10,
    )
    return out.split()[0] if out.strip() else ""


def test_bdd_feature_file_is_the_remaining_exec_launch_example() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    assert text.startswith(
        "Feature: Grok Build mind Extra High spawn execs launch-cloud-extra-high.sh"
    )
    low = text.lower()
    for needle in (
        "launch-cloud-extra-high.sh",
        "cloud_launch",
        "never bot cloudagent",
        "never grok --resume for cloud create",
        "#26",
        "#28",
        "hermes",
        "grok-4.6",
        "xhigh",
        "demonstrate",
    ):
        assert needle in low, needle
    assert PRIVATE_GAME not in text
    titles = _gherkin_scenarios(text)
    assert titles == list(SCENARIO_BINDINGS)
    defined = set(globals())
    for title, fn_name in SCENARIO_BINDINGS.items():
        assert fn_name in defined, (title, fn_name)


def test_scenario_wrap_mind_mail_names_extra_high_spawn() -> None:
    mind = _load(MIND_PY, "gcs_mind_exec_launch_wrap")
    prompt = mind.wrap_mind_mail("task-exec-1", "ctx-exec-1", "ship Extra High grunt")
    low = prompt.lower()
    assert "cloud_launch" in prompt or "launch-cloud-extra-high.sh" in prompt
    assert "launch-cloud-extra-high.sh" in prompt
    assert "never grok --resume for cloud create" in low
    assert "bot cloudagent" in low
    assert "grok-4.6" in prompt
    assert "xhigh" in low
    assert "ship Extra High grunt" in prompt
    assert "task-exec-1" in prompt
    for marker in HARVEST_MARKERS:
        assert marker not in prompt, marker
    assert "Message from" not in prompt
    assert "[filtered]" not in prompt
    src = MIND_PY.read_text(encoding="utf-8")
    for restack in PR47_RESTACK:
        assert restack not in src, restack


def test_process_once_runner_prompt_includes_spawn_exec_law(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind = _load(MIND_PY, "gcs_mind_exec_launch_once")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    saw: list[str] = []

    def fake(prompt: str, **_kwargs: object) -> dict[str, str]:
        saw.append(prompt)
        return {"text": "ack", "returncode": 0}

    _append_inbox(state, "floor", "task-exec-once", "need an Extra High grunt")
    result = mind.process_once("floor", runner=fake)
    assert result.get("consumed") == 1, result
    assert saw, "runner must receive wrap_mind_mail spawn law"
    blob = saw[0]
    assert "need an Extra High grunt" in blob
    assert "launch-cloud-extra-high.sh" in blob
    assert "never grok --resume for cloud create" in blob.lower()
    assert "bot cloudagent" in blob.lower()


def test_scenario_cloud_launch_plugin_execs_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind = _load(MIND_PY, "gcs_mind_exec_launch_plugin")
    monkeypatch.setattr(mind, "ROOT", tmp_path)
    monkeypatch.setattr(mind, "STATE_DIR", tmp_path / "a2a-state")
    script = _write_exec(
        tmp_path / "scripts" / "launch-cloud-extra-high.sh",
        "#!/bin/sh\necho CLOUD_LAUNCH_OK\n",
    )
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> object:
        captured.append([str(x) for x in cmd])

        class Proc:
            returncode = 0
            stdout = "CLOUD_LAUNCH_OK\n"
            stderr = ""

        return Proc()

    monkeypatch.setattr(mind.subprocess, "run", fake_run)
    out = mind.call_plugin(
        "cloud_launch", {"prompt": "implement Extra High grunt", "name": "floor-x"}
    )
    assert "CLOUD_LAUNCH_OK" in out
    assert captured, "cloud_launch must invoke a subprocess"
    argv = captured[0]
    assert Path(argv[0]).name == "launch-cloud-extra-high.sh", argv
    assert Path(argv[0]) == script, argv
    assert argv[0] != "bash"
    assert "bash" not in argv[:1]
    joined = " ".join(argv)
    assert "grok" not in argv[0]
    assert "--resume" not in argv
    assert "Bot CloudAgent" not in joined
    assert "--name" in argv
    assert "floor-x" in argv
    assert "implement Extra High grunt" in argv


def test_extra_high_spawn_argv_is_the_launcher_not_grok() -> None:
    mind = _load(MIND_PY, "gcs_mind_exec_launch_argv")
    argv = mind.extra_high_spawn_argv("do the work", name="grunt-x")
    assert Path(argv[0]).name == "launch-cloud-extra-high.sh"
    assert argv[0] != "bash"
    assert argv[0] != "grok"
    assert "--resume" not in argv
    assert "--session-id" not in argv
    assert "--name" in argv
    assert "grunt-x" in argv
    assert "do the work" in argv
    grok_argv = mind.grok_cli_argv(
        session_id="11111111-1111-4111-8111-111111111111",
        minted=True,
        mail_path=Path("/tmp/mail.txt"),
    )
    assert "--resume" in grok_argv
    assert grok_argv[0] == "grok" or Path(grok_argv[0]).name == "grok"
    assert argv != grok_argv
    assert "launch-cloud-extra-high.sh" not in " ".join(grok_argv)


def test_scenario_spawn_wrapper_execs_launcher(tmp_path: Path) -> None:
    bot_like = _load(BOT_LIKE_PY, "gcs_mind_exec_launch_wrap_path")
    grok_home = tmp_path / "grok-home"
    home = tmp_path / "home"
    bot_like.install_mind_spawn_path(root=REPO, grok_home=grok_home, home=home)
    wrap = grok_home / "bin" / "cloud_launch"
    assert wrap.is_file()
    text = wrap.read_text(encoding="utf-8")
    assert "launch-cloud-extra-high.sh" in text
    assert "exec bash" not in text
    assert "exec " in text
    exec_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("exec ")
    ]
    assert exec_lines, text
    exec_line = exec_lines[-1]
    assert "launch-cloud-extra-high.sh" in exec_line
    assert " bash " not in f" {exec_line} "
    assert "grok --resume" not in text
    assert "--resume" not in text
    assert "Bot CloudAgent" not in text
    assert "session/prompt" not in text
    mode = _git_mode("scripts/launch-cloud-extra-high.sh")
    assert mode == "100755", mode
    assert LAUNCH.is_file()
    assert os.access(LAUNCH, os.X_OK), "launcher must be executable to exec"


def test_wrapper_runtime_execs_launcher_as_argv0(tmp_path: Path) -> None:
    bot_like = _load(BOT_LIKE_PY, "gcs_mind_exec_launch_runtime")
    grok_home = tmp_path / "grok-home"
    home = tmp_path / "home"
    scripts = tmp_path / "scripts"
    marker = tmp_path / "argv0.txt"
    _write_exec(
        scripts / "launch-cloud-extra-high.sh",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$0" > "{marker}"\n'
        'printf "LAUNCH_ARGV:%s\\n" "$*"\n',
    )
    _write_exec(
        scripts / "a2a" / "send.sh",
        "#!/bin/sh\necho SEND_OK\n",
    )
    bot_like.install_mind_spawn_path(root=tmp_path, grok_home=grok_home, home=home)
    launch = subprocess.run(
        [str(grok_home / "bin" / "cloud_launch"), "--name", "grunt-x", "do the work"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert launch.returncode == 0, launch.stdout + launch.stderr
    assert "LAUNCH_ARGV:--name grunt-x do the work" in launch.stdout
    argv0 = marker.read_text(encoding="utf-8").strip()
    assert argv0.endswith("launch-cloud-extra-high.sh"), argv0
    assert Path(argv0).name == "launch-cloud-extra-high.sh"


def test_launcher_and_sdk_never_grok_resume_for_cloud_create() -> None:
    sh = LAUNCH.read_text(encoding="utf-8")
    ts = LAUNCH_TS.read_text(encoding="utf-8")
    assert "grok --resume" not in sh
    assert "grok --resume" not in ts
    assert "Agent.create" in ts
    assert "grok-4.6" in sh
    assert "xhigh" in sh.lower()
    assert "Bot CloudAgent" in sh
    bot_like = BOT_LIKE_PY.read_text(encoding="utf-8")
    assert "grok --resume" not in bot_like
    assert "Bot CloudAgent" not in bot_like


def test_do_not_vendor_hermes_or_merge_harvest_26_28() -> None:
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert not (REPO / "vendor" / "hermes").exists()
    modules = GITMODULES.read_text(encoding="utf-8")
    assert "hermes-agent" not in modules
    mind = MIND_PY.read_text(encoding="utf-8")
    bot_like = BOT_LIKE_PY.read_text(encoding="utf-8")
    blob = mind + "\n" + bot_like
    for marker in HARVEST_MARKERS:
        assert marker not in blob, marker
    assert "message_agent.py" not in mind
    assert "plugin.yaml" not in bot_like
    plugins = _load(MIND_PY, "gcs_mind_exec_launch_plugins").PLUGINS
    assert "cloud_launch" in plugins
    for restack in PR47_RESTACK:
        assert restack not in plugins, restack
    assert PRIVATE_GAME not in mind
    assert PRIVATE_GAME not in FEATURE.read_text(encoding="utf-8")


def test_docs_name_mind_extra_high_spawn_exec() -> None:
    mind_doc = MIND_DOC.read_text(encoding="utf-8")
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    blob = mind_doc + "\n" + agents
    assert "launch-cloud-extra-high.sh" in blob
    assert "never grok --resume for Cloud create" in blob or (
        "never grok --resume for cloud create" in blob.lower()
    )
    assert "cloud_launch" in blob
    assert PRIVATE_GAME not in mind_doc
