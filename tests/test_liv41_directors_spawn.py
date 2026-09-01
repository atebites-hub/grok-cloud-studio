"""BDD: Grok Build directors spawn Extra High themselves (LIV-41).

Scenarios live in docs/studio/bdd/liv41_directors_spawn.feature.
Demonstrate, don't theatre: a director turn without a spawn when
RUNNING < 8 per repo is FAIL. Minds invoke launch-cloud-extra-high.sh
or cloud_launch. Do not have Donald DIY Extra High.

Does not remint harvest PRs #26/#28, Hermes #47, send-pin #41,
mail-is-turn #61, CI #62, Linear #64, browser #63, refuse-same-name #59,
count-running #55, or the finished gcs-liv41-mind-must-launch helper.
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
FEATURE = REPO / "docs" / "studio" / "bdd" / "liv41_directors_spawn.feature"
SPAWN_PY = REPO / "scripts" / "directors" / "director_turn_spawn.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
LIB_PY = REPO / "scripts" / "a2a" / "lib.py"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
LAUNCH_SH = REPO / "scripts" / "launch-cloud-extra-high.sh"
SOULS = REPO / "docs" / "studio" / "directors" / "souls"
FLOOR_OPS_SOUL = SOULS / "floor-ops" / "SOUL.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
STUDIO_MIND = REPO / "plugins" / "studio-mind" / "server.py"
RESERVED_NAME = "gcs-liv41-mind-must-launch"
LAUNCH_REL = "scripts/launch-cloud-extra-high.sh"
PRIVATE_GAME = "atebites-hub/" + "palemon"
LIVING_SKY_HOST = "linear.app/livingsky"

REQUIRED_SOULS = (
    "floor",
    "floor-ops",
    "studio-ops",
    "ops",
    "art",
    "content",
    "systems",
    "qa-a",
    "qa-b",
    "audio",
    "narrative",
    "cloud",
)

ACP_PING = (
    "ACP_PING STATUS/CONTINUE seat=floor token=tick-1. "
    "Keep-alive turn: do work, do not idle. Tools are allowed."
)
LAUNCH_MAIL = "LAUNCH ONLY: playability hitboxes. Open a PR."
TASK_ASSIGN = "TASK_ASSIGN: playability camera juice. Spawn Extra High."


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
        "contextId": "ctx-liv41",
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


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
    runner=None,
    running: str | None = "0",
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_mind_liv41_{unique}")
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
    monkeypatch.setenv("GCS_CLOUD_MIN_RUNNING", "8")
    if running is None:
        monkeypatch.delenv("GCS_CLOUD_RUNNING", raising=False)
    else:
        monkeypatch.setenv("GCS_CLOUD_RUNNING", running)
    if runner is not None:
        monkeypatch.setattr(mind, "DEFAULT_RUNNER", runner)
    return mind, state


def _tool_call_cloud_launch(*, name: str = "floor-juice") -> str:
    return json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "cloud_launch",
            "rawInput": {
                "command": f"bash {LAUNCH_REL} --name {name} playability juice",
                "argv": ["bash", LAUNCH_REL, "--name", name, "playability juice"],
            },
        }
    )


def _shell_ls_launcher() -> str:
    return json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {
                "command": f"ls {LAUNCH_REL}",
                "argv": ["ls", LAUNCH_REL],
            },
        }
    )


# --- Feature file is the example -------------------------------------------------


def test_bdd_feature_file_names_liv41_and_demonstrate_not_theatre() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    low = text.lower()
    assert "Feature: Grok Build directors spawn Extra High themselves" in text
    assert "LIV-41" in text
    assert LIVING_SKY_HOST in text or "living sky" in low
    assert "never black swan" in low
    assert "demonstrate" in low and "theatre" in low
    assert LAUNCH_REL in text
    assert "cloud_launch" in text
    assert "8" in text
    assert "running" in low
    assert "donald" in low
    assert "fail" in low
    assert RESERVED_NAME in text
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in text
    assert "Bot CloudAgent" in text or "bot cloudagent" in low
    assert PRIVATE_GAME not in text
    for scenario in (
        "Under floor, a director turn without a spawn is FAIL",
        "Under floor, an actual launcher or plugin invoke PASSES",
        "At floor, a director turn without a spawn is not FAIL",
        "Donald does not spawn Extra High",
        "A2A_REPLY and FLEET_DONE do not require a spawn",
        "PATH cloud_launch wrapper and studio-mind plugin invoke the launcher",
        "Never Bot CloudAgent, pin grok-4.6 xhigh",
    ):
        assert f"Scenario: {scenario}" in text, scenario
    assert SPAWN_PY.is_file()
    assert LAUNCH_SH.is_file()


# --- Judge: theatre vs invoke ---------------------------------------------------


def test_prose_about_launching_is_theatre_not_spawn() -> None:
    spawn = _load(SPAWN_PY, "gcs_director_turn_spawn_theatre")
    theatre = (
        "I should call scripts/launch-cloud-extra-high.sh next. "
        "CLOUD_LAUNCH_OK would be nice. Prefer the cloud_launch tool."
    )
    assert spawn.turn_spawned(theatre) is False
    assert spawn.turn_spawned("STATUS seat=floor token=tick-1") is False
    verdict = spawn.judge_director_turn(
        mail=ACP_PING,
        assistant=theatre,
        running_count=0,
    )
    assert verdict["fail"] is True
    assert verdict["reason"] == "no-spawn"
    assert verdict["spawned"] is False


def test_ls_cat_rg_of_launcher_is_not_spawn() -> None:
    spawn = _load(SPAWN_PY, "gcs_director_turn_spawn_inspect")
    assert spawn.turn_spawned(_shell_ls_launcher()) is False
    cat = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {"command": f"cat {LAUNCH_REL}", "argv": ["cat", LAUNCH_REL]},
        }
    )
    rg = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {"command": f"rg launch-cloud-extra-high {LAUNCH_REL}"},
        }
    )
    assert spawn.turn_spawned(cat) is False
    assert spawn.turn_spawned(rg) is False


def test_cloud_launch_tool_call_and_launcher_argv_are_spawn() -> None:
    spawn = _load(SPAWN_PY, "gcs_director_turn_spawn_invoke")
    assert spawn.turn_spawned(_tool_call_cloud_launch()) is True
    argv_only = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {
                "command": f"bash {LAUNCH_REL} --name floor-iac playability",
                "argv": ["bash", LAUNCH_REL, "--name", "floor-iac", "playability"],
            },
        }
    )
    assert spawn.turn_spawned(argv_only) is True
    plugin_name = json.dumps({"name": "cloud_launch", "arguments": {"prompt": "x"}})
    assert spawn.turn_spawned(plugin_name) is True


def test_reserved_finished_name_and_bot_names_do_not_count() -> None:
    spawn = _load(SPAWN_PY, "gcs_director_turn_spawn_names")
    reserved = _tool_call_cloud_launch(name=RESERVED_NAME)
    donald = _tool_call_cloud_launch(name="donald")
    orch = _tool_call_cloud_launch(name="orchestrator")
    assert spawn.turn_spawned(reserved) is False
    assert spawn.turn_spawned(donald) is False
    assert spawn.turn_spawned(orch) is False
    ok = spawn.judge_director_turn(
        mail=LAUNCH_MAIL,
        assistant=_tool_call_cloud_launch(name="gcs-liv41-directors-spawn"),
        running_count=1,
    )
    assert ok["fail"] is False
    assert ok["spawned"] is True


def test_at_eight_running_no_spawn_is_not_fail() -> None:
    spawn = _load(SPAWN_PY, "gcs_director_turn_spawn_floor")
    assert spawn.DEFAULT_MIN_RUNNING == 8
    assert spawn.under_floor(7) is True
    assert spawn.under_floor(8) is False
    assert spawn.under_floor(8, cap=8) is False
    verdict = spawn.judge_director_turn(
        mail=ACP_PING,
        assistant="STATUS seat=floor token=tick-1",
        running_count=8,
    )
    assert verdict["fail"] is False
    assert verdict["reason"] == "at-floor"


def test_a2a_reply_and_fleet_done_do_not_require_spawn() -> None:
    spawn = _load(SPAWN_PY, "gcs_director_turn_spawn_exempt")
    assert spawn.spawn_required("A2A_REPLY from ops") is False
    assert spawn.spawn_required("FLEET_DONE id=bc-1 runStatus=FINISHED") is False
    assert spawn.spawn_required("PR_READY https://example.test/pr/1") is False
    assert spawn.spawn_required(ACP_PING) is True
    assert spawn.spawn_required(LAUNCH_MAIL) is True
    assert spawn.spawn_required(TASK_ASSIGN) is True
    assert spawn.spawn_required("ping from ops") is False
    for mail in (
        "A2A_REPLY thanks",
        "FLEET_DONE collect the PR",
        "PR_READY hand to QA",
    ):
        verdict = spawn.judge_director_turn(
            mail=mail,
            assistant="RESULT bc-id=none pr=none",
            running_count=0,
        )
        assert verdict["fail"] is False, mail
        assert verdict["reason"] in {"exempt", "not-required"}


# --- process_once wiring --------------------------------------------------------


def test_process_once_under_floor_without_spawn_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    def fake(prompt: str, **_kwargs: object) -> dict:
        seen.append(prompt)
        return {"text": "I will think about launching Extra High. STATUS token=tick-1"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="nolaunch", runner=fake)
    _append_inbox(state, "floor", "task-liv41-1", ACP_PING)
    result = mind.process_once("floor")
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert result["consumed"] == 0
    assert result.get("reason") == "no-spawn"
    assert _offset(state, "floor") == 0
    assert "MIND_FAIL" in blob
    assert "no-spawn" in blob
    assert seen, "runner never ran"
    wrap = seen[0].lower()
    assert "must" in wrap
    assert "launch-cloud-extra-high" in wrap or "cloud_launch" in wrap
    assert "fail" in wrap
    assert RESERVED_NAME in seen[0]


def test_process_once_under_floor_with_spawn_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(_prompt: str, **_kwargs: object) -> dict:
        return {"text": _tool_call_cloud_launch(name="gcs-liv41-directors-spawn")}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="didlaunch", runner=fake)
    _append_inbox(state, "floor", "task-liv41-2", LAUNCH_MAIL)
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"
    assert _offset(state, "floor") > 0


def test_process_once_generic_mail_does_not_require_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(_prompt: str, **_kwargs: object) -> dict:
        return {"text": "ack ping from ops"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="generic", runner=fake)
    _append_inbox(state, "floor", "task-liv41-3", "ping from ops")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"


def test_process_once_donald_does_not_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake(_prompt: str, **_kwargs: object) -> dict:
        calls.append("ran")
        return {"text": "should not run"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="donald", runner=fake)
    _append_inbox(state, "donald", "task-liv41-d", ACP_PING)
    result = mind.process_once("donald")
    assert result["consumed"] == 0
    assert "skip" in str(result.get("reason", "")).lower()
    assert calls == []


def test_mind_seats_never_include_donald_or_orchestrator() -> None:
    proc = subprocess.run(
        ["python3", str(LIB_PY), "mind-seats"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
        env={
            **os.environ,
            "GCS_MIND_SEATS": "floor,ops,donald,orchestrator,floor-ops",
        },
    )
    assert proc.returncode == 0, proc.stderr
    seats = {s.strip() for s in proc.stdout.splitlines() if s.strip()}
    assert "donald" not in seats
    assert "orchestrator" not in seats
    assert "floor" in seats
    assert "floor-ops" in seats


# --- PATH wrapper + plugin ------------------------------------------------------


def test_seat_identity_installs_cloud_launch_wrapper_that_execs_launcher(
    tmp_path: Path,
) -> None:
    overlay = tmp_path / "overlay"
    launch_log = overlay / "launch.argv"
    fake_launch = _write_exec(
        overlay / "scripts" / "launch-cloud-extra-high.sh",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{launch_log}"\n'
        "echo CLOUD_LAUNCH_OK id=bc-wrap\n",
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GROK_HOME": str(tmp_path / "grok-home"),
        "GCS_LAUNCH_OVERLAY": str(overlay),
        "LC_ALL": "C",
        "TERM": "dumb",
        "TASKBOARD_BIN": str(
            _write_exec(tmp_path / "host-bin" / "taskboard", "#!/bin/sh\necho tb\n")
        ),
    }
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_cloud_launch_cli floor
export PATH="${GROK_HOME}/bin:${HOME}/.grok/bin"
command -v cloud_launch
GCS_ROOT="${GCS_LAUNCH_OVERLAY}" cloud_launch --name floor-wrap "playability juice"
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    wrap = Path(env["GROK_HOME"]) / "bin" / "cloud_launch"
    assert wrap.is_file(), blob
    assert "launch-cloud-extra-high.sh" in wrap.read_text(encoding="utf-8")
    argv = launch_log.read_text(encoding="utf-8") if launch_log.is_file() else ""
    assert "--name" in argv, argv or blob
    assert "floor-wrap" in argv, argv or blob
    assert "playability juice" in argv, argv or blob
    assert fake_launch.is_file()


def test_studio_mind_plugin_cloud_launch_is_the_launcher() -> None:
    mind = _load(MIND_PY, "gcs_mind_liv41_plugin")
    assert "cloud_launch" in mind.PLUGINS
    src = mind.plugin_cloud_launch.__doc__ or ""
    assert "launch-cloud-extra-high.sh" in src
    impl = MIND_PY.read_text(encoding="utf-8")
    assert "scripts" in impl and "launch-cloud-extra-high.sh" in impl
    plugin = STUDIO_MIND.read_text(encoding="utf-8")
    assert "cloud_launch" in plugin or "PLUGINS" in plugin
    launch = LAUNCH_SH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast=false" in launch


# --- Footer / souls / docs ------------------------------------------------------


def test_footer_and_souls_require_directors_spawn_not_donald() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    low = footer.lower()
    assert LAUNCH_REL in footer
    assert "cloud_launch" in footer
    assert "8" in footer
    assert "running" in low
    assert "fail" in low
    assert "donald" in low
    assert RESERVED_NAME in footer
    assert "grok-4.6" in footer
    assert "xhigh" in footer
    assert "fast=false" in footer.replace(" ", "")
    assert "Bot CloudAgent" in footer or "bot cloudagent" in low
    assert PRIVATE_GAME not in footer
    souls = sorted(SOULS.glob("*/SOUL.md"))
    names = {path.parent.name for path in souls}
    for required in REQUIRED_SOULS:
        assert required in names, required
    for path in souls:
        text = path.read_text(encoding="utf-8")
        label = str(path.relative_to(REPO))
        assert LAUNCH_REL in text, label
        assert "fail" in text.lower() or "MUST" in text, label
        assert PRIVATE_GAME not in text
        assert "LINEAR_API_KEY" not in text


def test_floor_ops_spawns_itself_donald_does_not_diy() -> None:
    text = FLOOR_OPS_SOUL.read_text(encoding="utf-8")
    low = text.lower()
    assert "donald-clone" in low or "donald clone" in low
    assert LAUNCH_REL in text
    assert "donald diy" in low or "do not have donald" in low
    assert "fail" in low or "MUST" in text


def test_docs_pin_directors_spawn_law_living_sky() -> None:
    mind = MIND_DOC.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    blob = "\n".join((mind, cloud))
    low = blob.lower()
    assert "liv-41" in low or "LIV-41" in blob
    assert LAUNCH_REL in blob
    assert "cloud_launch" in blob
    assert "8" in blob
    assert "running" in low
    assert "fail" in low
    assert "theatre" in low or "demonstrate" in low
    assert "donald" in low
    assert "living sky" in low
    assert "never" in low and "black swan" in low
    assert "grok-4.6" in blob
    assert "xhigh" in blob
    assert "fast=false" in blob.replace(" ", "")
    assert RESERVED_NAME in blob
    assert PRIVATE_GAME not in blob
    assert "directors_spawn.py" not in blob
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "install_seat_cloud_launch_cli" in common
    identity = common.split("install_seat_identity() {", 1)[1]
    assert "install_seat_cloud_launch_cli" in identity
