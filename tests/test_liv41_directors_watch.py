"""BDD: Grok Build directors monitor Extra High bc-ids (LIV-41).

Scenarios live in docs/studio/bdd/liv41_directors_watch.feature.
Demonstrate, don't theatre: a director turn without watching its own
grunt is FAIL. Waiter FLEET_DONE goes to the owning seat.

Does not remint GCS #75 spawn-only (director_turn_spawn.py / no-spawn).
Never Bot CloudAgent. Never Palemon.
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
FEATURE = REPO / "docs" / "studio" / "bdd" / "liv41_directors_watch.feature"
WATCH_PY = REPO / "scripts" / "directors" / "director_turn_watch.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
LIB_PY = REPO / "scripts" / "a2a" / "lib.py"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
SPAWN_WAITER = REPO / "scripts" / "cloud" / "spawn-waiter.sh"
LAUNCH_SH = REPO / "scripts" / "launch-cloud-extra-high.sh"
SOULS = REPO / "docs" / "studio" / "directors" / "souls"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"
STUDIO_MIND = REPO / "plugins" / "studio-mind" / "server.py"
MCP_PY = REPO / "scripts" / "mcp" / "gcs_mcp.py"
FLEET_PY = REPO / "scripts" / "cloud" / "fleet_ledger.py"
SHEPHERD_PY = REPO / "scripts" / "directors" / "fleet-shepherd.py"
LAUNCH_REL = "scripts/launch-cloud-extra-high.sh"
WAITER_REL = "scripts/cloud/spawn-waiter.sh"
WATCH_REL = "scripts/cloud/watch-cloud-agent.sh"
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
        "contextId": "ctx-liv41-watch",
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
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_mind_liv41_watch_{unique}")
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
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "floor")
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


def _tool_call_cloud_wait(*, bc_id: str = "bc-watch-1") -> str:
    return json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "cloud_wait",
            "arguments": {"id": bc_id},
            "rawInput": {
                "command": f"bash {WAITER_REL} --id {bc_id}",
                "argv": ["bash", WAITER_REL, "--id", bc_id],
            },
        }
    )


def _shell_ls_waiter() -> str:
    return json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {
                "command": f"ls {WAITER_REL}",
                "argv": ["ls", WAITER_REL],
            },
        }
    )


def _spawn_plus_wait(*, name: str = "gcs-liv41-directors-watch") -> str:
    return _tool_call_cloud_launch(name=name) + "\n" + _tool_call_cloud_wait()


# --- Feature file is the example -------------------------------------------------


def test_bdd_feature_file_names_liv41_watch_not_spawn_only() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    low = text.lower()
    assert "Feature: Grok Build directors monitor their own Extra High bc-ids" in text
    assert "LIV-41" in text
    assert LIVING_SKY_HOST in text or "living sky" in low
    assert "never black swan" in low
    assert "demonstrate" in low and "theatre" in low
    assert WAITER_REL in text
    assert "cloud_wait" in text
    assert "wait-notify" in text
    assert "FLEET_DONE" in text
    assert "owning seat" in low
    assert "fail" in low
    assert "no-watch" in low
    assert "donald" in low
    assert "fleet-shepherd" in low or "fleet shepherd" in low
    assert "watch-cloud-agent.sh" in text
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in text
    assert "Bot CloudAgent" in text or "bot cloudagent" in low
    assert PRIVATE_GAME not in text
    assert "director_turn_spawn.py" in text
    assert "does not restack" in low or "do not duplicate" in low or "do not remint" in low
    for scenario in (
        "A director turn without watching its own grunt is FAIL",
        "Spawn plus waiter PASSES",
        "Unwatched ledger grunt on a director turn is FAIL",
        "Waiter FLEET_DONE pings the owning seat",
        "A2A_REPLY and FLEET_DONE collect do not require another watch",
        "PATH cloud_wait wrapper and studio-mind plugin invoke spawn-waiter",
        "Never Bot CloudAgent, pin grok-4.6 xhigh",
    ):
        assert f"Scenario: {scenario}" in text, scenario
    assert WATCH_PY.is_file()
    assert SPAWN_WAITER.is_file()
    assert LAUNCH_SH.is_file()


# --- Judge: theatre vs invoke ---------------------------------------------------


def test_prose_about_watching_is_theatre_not_watch() -> None:
    watch = _load(WATCH_PY, "gcs_director_turn_watch_theatre")
    theatre = (
        "I should call scripts/cloud/spawn-waiter.sh next. "
        "CLOUD_WAITER_SPAWNED would be nice. Prefer the cloud_wait tool."
    )
    assert watch.turn_watched(theatre) is False
    verdict = watch.judge_director_watch(
        mail=LAUNCH_MAIL,
        assistant=_tool_call_cloud_launch() + "\n" + theatre,
        open_bc_ids=[],
    )
    assert verdict["fail"] is True
    assert verdict["reason"] == "no-watch"
    assert verdict["watched"] is False


def test_ls_cat_rg_of_waiter_is_not_watch() -> None:
    watch = _load(WATCH_PY, "gcs_director_turn_watch_inspect")
    assert watch.turn_watched(_shell_ls_waiter()) is False
    cat = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {"command": f"cat {WAITER_REL}", "argv": ["cat", WAITER_REL]},
        }
    )
    rg = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {"command": f"rg spawn-waiter {WAITER_REL}"},
        }
    )
    watch_ls = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {"command": f"ls {WATCH_REL}", "argv": ["ls", WATCH_REL]},
        }
    )
    assert watch.turn_watched(cat) is False
    assert watch.turn_watched(rg) is False
    assert watch.turn_watched(watch_ls) is False
    spawn_only = _tool_call_cloud_launch() + "\n" + _shell_ls_waiter()
    verdict = watch.judge_director_watch(
        mail=LAUNCH_MAIL,
        assistant=spawn_only,
        open_bc_ids=[],
    )
    assert verdict["fail"] is True
    assert verdict["reason"] == "no-watch"


def test_cloud_launch_without_waiter_is_fail_not_spawn_only() -> None:
    """#75 spawn-only would PASS this turn. LIV-41 watch FAILs it."""
    watch = _load(WATCH_PY, "gcs_director_turn_watch_nospawnwatch")
    verdict = watch.judge_director_watch(
        mail=LAUNCH_MAIL,
        assistant=_tool_call_cloud_launch(name="gcs-liv41-directors-watch"),
        open_bc_ids=[],
    )
    assert verdict["fail"] is True
    assert verdict["reason"] == "no-watch"
    assert verdict["has_grunt"] is True
    assert verdict["watched"] is False


def test_cloud_wait_and_spawn_waiter_argv_are_watch() -> None:
    watch = _load(WATCH_PY, "gcs_director_turn_watch_invoke")
    assert watch.turn_watched(_tool_call_cloud_wait()) is True
    argv_only = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {
                "command": f"bash {WAITER_REL} --id bc-watch-1",
                "argv": ["bash", WAITER_REL, "--id", "bc-watch-1"],
            },
        }
    )
    assert watch.turn_watched(argv_only) is True
    wait_notify = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {
                "command": "bash scripts/cloud/sdk/run.sh wait-notify --id bc-watch-1"
            },
        }
    )
    assert watch.turn_watched(wait_notify) is True
    spawned_line = "CLOUD_WAITER_SPAWNED id=bc-watch-1 pid=1234"
    assert watch.turn_watched(spawned_line) is True
    ok = watch.judge_director_watch(
        mail=LAUNCH_MAIL,
        assistant=_spawn_plus_wait(),
        open_bc_ids=[],
    )
    assert ok["fail"] is False
    assert ok["watched"] is True
    assert ok["reason"] == "watched"


def test_waiter_skipped_and_bot_names_do_not_count() -> None:
    watch = _load(WATCH_PY, "gcs_director_turn_watch_names")
    skipped = (
        _tool_call_cloud_launch(name="floor-x")
        + "\n"
        + "CLOUD_WAITER_SKIPPED id=bc-x reason=GCS_SPAWN_WAITER=0"
    )
    assert watch.turn_watched(skipped) is False
    env_skip = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {
                "command": f"GCS_SPAWN_WAITER=0 bash {WAITER_REL} --id bc-x",
            },
        }
    )
    assert watch.turn_watched(env_skip) is False
    donald = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "cloud_wait",
            "arguments": {"id": "bc-x", "seat": "donald"},
        }
    )
    orch = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "cloud_wait",
            "arguments": {"id": "bc-x", "name": "orchestrator"},
        }
    )
    assert watch.turn_watched(donald) is False
    assert watch.turn_watched(orch) is False
    shepherd = json.dumps(
        {
            "sessionUpdate": "tool_call",
            "name": "Shell",
            "rawInput": {"command": "python3 scripts/directors/fleet-shepherd.py"},
        }
    )
    assert watch.turn_watched(shepherd) is False


def test_unwatched_ledger_grunt_fails_without_waiter() -> None:
    watch = _load(WATCH_PY, "gcs_director_turn_watch_orphan")
    verdict = watch.judge_director_watch(
        mail=ACP_PING,
        assistant="STATUS seat=floor token=tick-1",
        open_bc_ids=["bc-orphan-1"],
    )
    assert verdict["fail"] is True
    assert verdict["reason"] == "no-watch"
    live = watch.judge_director_watch(
        mail=ACP_PING,
        assistant="STATUS seat=floor token=tick-1",
        open_bc_ids=[],
    )
    assert live["fail"] is False
    assert live["reason"] in {"not-required", "already-watched"}


def test_a2a_reply_and_fleet_done_do_not_require_watch() -> None:
    watch = _load(WATCH_PY, "gcs_director_turn_watch_exempt")
    assert watch.watch_required("A2A_REPLY from ops", open_bc_ids=["bc-1"]) is False
    assert watch.watch_required("FLEET_DONE id=bc-1 runStatus=FINISHED", open_bc_ids=[]) is False
    assert watch.watch_required("PR_READY https://example.test/pr/1", open_bc_ids=[]) is False
    for mail in (
        "A2A_REPLY thanks",
        "FLEET_DONE collect the PR",
        "PR_READY hand to QA",
    ):
        verdict = watch.judge_director_watch(
            mail=mail,
            assistant="RESULT bc-id=none pr=none",
            open_bc_ids=["bc-orphan-1"],
        )
        assert verdict["fail"] is False, mail
        assert verdict["reason"] in {"exempt", "not-required"}


def test_generic_mail_without_grunt_does_not_require_watch() -> None:
    watch = _load(WATCH_PY, "gcs_director_turn_watch_generic")
    verdict = watch.judge_director_watch(
        mail="ping from ops",
        assistant="ack ping from ops",
        open_bc_ids=[],
    )
    assert verdict["fail"] is False
    assert verdict["reason"] == "not-required"


# --- process_once wiring --------------------------------------------------------


def test_process_once_spawn_without_watch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    def fake(prompt: str, **_kwargs: object) -> dict:
        seen.append(prompt)
        return {"text": _tool_call_cloud_launch(name="gcs-liv41-directors-watch")}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="nowatch", runner=fake)
    _append_inbox(state, "floor", "task-liv41-w1", LAUNCH_MAIL)
    result = mind.process_once("floor")
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert result["consumed"] == 0
    assert result.get("reason") == "no-watch"
    assert _offset(state, "floor") == 0
    assert "MIND_FAIL" in blob
    assert "no-watch" in blob
    assert seen, "runner never ran"
    wrap = seen[0].lower()
    assert "must" in wrap
    assert "spawn-waiter" in wrap or "cloud_wait" in wrap or "wait-notify" in wrap
    assert "fail" in wrap
    assert "fleet_done" in wrap or "fleet-done" in wrap


def test_process_once_spawn_plus_waiter_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(_prompt: str, **_kwargs: object) -> dict:
        return {"text": _spawn_plus_wait()}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="didwatch", runner=fake)
    _append_inbox(state, "floor", "task-liv41-w2", LAUNCH_MAIL)
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"
    assert _offset(state, "floor") > 0


def test_process_once_orphan_without_watch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(_prompt: str, **_kwargs: object) -> dict:
        return {"text": "STATUS seat=floor token=tick-1"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="orphan", runner=fake)
    fleet = state / "floor" / "fleet.jsonl"
    fleet.parent.mkdir(parents=True, exist_ok=True)
    fleet.write_text(
        json.dumps(
            {
                "bc_id": "bc-orphan-floor",
                "seat": "floor",
                "status": "open",
                "notified": False,
                "waiter_pid": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _append_inbox(state, "floor", "task-liv41-w3", ACP_PING)
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "no-watch"
    assert _offset(state, "floor") == 0


def test_process_once_generic_mail_does_not_require_watch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(_prompt: str, **_kwargs: object) -> dict:
        return {"text": "ack ping from ops"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="generic", runner=fake)
    _append_inbox(state, "floor", "task-liv41-w4", "ping from ops")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"


def test_process_once_donald_does_not_watch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake(_prompt: str, **_kwargs: object) -> dict:
        calls.append("ran")
        return {"text": "should not run"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="donald", runner=fake)
    _append_inbox(state, "donald", "task-liv41-wd", ACP_PING)
    result = mind.process_once("donald")
    assert result["consumed"] == 0
    assert "skip" in str(result.get("reason", "")).lower()
    assert calls == []


# --- Waiter FLEET_DONE to owning seat ----------------------------------------


def test_notify_text_is_fleet_done_for_owning_seat() -> None:
    sys.path.insert(0, str(REPO / "scripts" / "cloud"))
    import fleet_ledger as ledger

    finished = ledger.notify_text(
        "bc-own-1",
        {
            "runStatus": "FINISHED",
            "prUrl": "https://example.test/pr/2",
            "name": "floor-x",
        },
    )
    assert "FLEET_DONE" in finished
    assert "PR_READY" in finished
    assert "bc-own-1" in finished
    assert "result-cloud-agent.sh" in finished
    assert "donald" not in finished.lower()
    errored = ledger.notify_text(
        "bc-own-1",
        {"runStatus": "ERROR", "prUrl": None, "name": "floor-x"},
    )
    assert "FLEET_DONE" in errored
    assert "PR_READY" not in errored


def test_notify_owner_pings_owning_seat_not_donald(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sys.path.insert(0, str(REPO / "scripts" / "cloud"))
    import fleet_ledger as ledger

    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "floor")
    pinged: list[tuple[str, str]] = []

    def fake_ping(seat: str, text: str) -> bool:
        pinged.append((seat, text))
        return True

    monkeypatch.setattr(ledger, "ping_seat", fake_ping)
    ledger.register("bc-own-2", seat="floor", name="floor-x")
    row = ledger.notify_owner(
        "bc-own-2",
        {"runStatus": "FINISHED", "prUrl": "https://example.test/pr/3", "name": "floor-x"},
        notified_by="waiter",
        seat="floor",
    )
    assert pinged, "owning seat was not pinged"
    assert pinged[0][0] == "floor"
    assert pinged[0][0] != "donald"
    assert pinged[0][0] != "orchestrator"
    assert "FLEET_DONE" in pinged[0][1]
    assert row.get("notified_by") == "waiter"


def test_shepherd_is_orphan_only_not_the_monitor() -> None:
    src = SHEPHERD_PY.read_text(encoding="utf-8")
    low = src.lower()
    assert "orphan" in low
    assert "waiter" in low
    assert "primary" in low or "safety net" in low


def test_spawn_waiter_dry_does_not_hang(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GCS_DIRECTOR_SEAT": "floor",
        "CLOUD_WAITER_DRY": "1",
        "LC_ALL": "C",
    }
    proc = subprocess.run(
        ["bash", str(SPAWN_WAITER), "--id", "bc-dry-1", "--name", "floor-dry"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_WAITER_DRY" in blob
    assert "bc-dry-1" in blob


# --- PATH wrapper + plugin ------------------------------------------------------


def test_seat_identity_installs_spawn_waiter_wrapper(
    tmp_path: Path,
) -> None:
    overlay = tmp_path / "overlay"
    launch_log = overlay / "waiter.argv"
    fake_waiter = _write_exec(
        overlay / "scripts" / "cloud" / "spawn-waiter.sh",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{launch_log}"\n'
        "echo CLOUD_WAITER_SPAWNED id=bc-wrap pid=1\n",
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
install_seat_spawn_waiter_cli floor
export PATH="${GROK_HOME}/bin:${HOME}/.grok/bin"
command -v cloud_wait
GCS_ROOT="${GCS_LAUNCH_OVERLAY}" cloud_wait --id bc-wrap-1 --name floor-wrap
command -v spawn_waiter
GCS_ROOT="${GCS_LAUNCH_OVERLAY}" spawn_waiter --id bc-wrap-2
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
    wrap = Path(env["GROK_HOME"]) / "bin" / "cloud_wait"
    assert wrap.is_file(), blob
    assert "spawn-waiter.sh" in wrap.read_text(encoding="utf-8")
    argv = launch_log.read_text(encoding="utf-8") if launch_log.is_file() else ""
    assert "--id" in argv, argv or blob
    assert "bc-wrap-1" in argv, argv or blob
    assert fake_waiter.is_file()


def test_studio_mind_and_mcp_cloud_wait_is_spawn_waiter() -> None:
    mind = _load(MIND_PY, "gcs_mind_liv41_watch_plugin")
    assert "cloud_wait" in mind.PLUGINS
    src = mind.plugin_cloud_wait.__doc__ or ""
    assert "spawn-waiter.sh" in src
    impl = MIND_PY.read_text(encoding="utf-8")
    assert "spawn-waiter.sh" in impl
    plugin = STUDIO_MIND.read_text(encoding="utf-8")
    assert "cloud_wait" in plugin or "PLUGINS" in plugin
    mcp = MCP_PY.read_text(encoding="utf-8")
    assert "cloud_wait" in mcp
    assert "spawn-waiter.sh" in mcp
    launch = LAUNCH_SH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast=false" in launch
    waiter = SPAWN_WAITER.read_text(encoding="utf-8")
    assert "wait-notify" in waiter
    assert "FLEET_DONE" in waiter or "wait-notify" in waiter


def test_cloud_wait_plugin_invokes_spawn_waiter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "waiter.argv"
    _write_exec(
        tmp_path / "scripts" / "cloud" / "spawn-waiter.sh",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'echo CLOUD_WAITER_SPAWNED id="$2"\n',
    )
    mind = _load(MIND_PY, "gcs_mind_liv41_watch_call")
    monkeypatch.setattr(mind, "ROOT", tmp_path)
    monkeypatch.setattr(mind, "STATE_DIR", tmp_path / "a2a-state")
    out = mind.call_plugin("cloud_wait", {"id": "bc-plug-1", "name": "floor-x"})
    assert "CLOUD_WAITER_SPAWNED" in out
    argv = log.read_text(encoding="utf-8")
    assert "--id" in argv
    assert "bc-plug-1" in argv


# --- Footer / souls / docs ------------------------------------------------------


def test_footer_and_souls_require_directors_watch() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    low = footer.lower()
    assert WAITER_REL in footer or "spawn-waiter" in footer
    assert "cloud_wait" in footer
    assert "fleet_done" in low or "fleet-done" in low or "FLEET_DONE" in footer
    assert "fail" in low
    assert "no-watch" in low or "without watching" in low or "watch" in low
    assert "donald" in low
    assert "watch-cloud-agent" in footer
    assert "grok-4.6" in footer
    assert "xhigh" in footer
    assert PRIVATE_GAME not in footer
    souls = sorted(SOULS.glob("*/SOUL.md"))
    names = {path.parent.name for path in souls}
    for required in REQUIRED_SOULS:
        assert required in names, required
    for path in souls:
        text = path.read_text(encoding="utf-8")
        label = str(path.relative_to(REPO))
        assert "spawn-waiter" in text or "waiter" in text.lower() or "watch" in text.lower(), label
        assert "fail" in text.lower() or "MUST" in text or "monitor" in text.lower(), label
        assert PRIVATE_GAME not in text
        assert "LINEAR_API_KEY" not in text


def test_docs_pin_directors_watch_law_living_sky() -> None:
    mind = MIND_DOC.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    arch = ARCH_DOC.read_text(encoding="utf-8")
    blob = "\n".join((mind, cloud, arch))
    low = blob.lower()
    assert "liv-41" in low or "LIV-41" in blob
    assert WAITER_REL in blob or "spawn-waiter" in blob
    assert "cloud_wait" in blob
    assert "fleet_done" in low or "FLEET_DONE" in blob
    assert "fail" in low
    assert "theatre" in low or "demonstrate" in low
    assert "owning seat" in low or "owning-seat" in low
    assert "living sky" in low
    assert "never" in low and "black swan" in low
    assert "grok-4.6" in blob
    assert "xhigh" in blob
    assert PRIVATE_GAME not in blob
    assert "director_turn_spawn.py" not in blob
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "install_seat_spawn_waiter_cli" in common
    identity = common.split("install_seat_identity() {", 1)[1]
    assert "install_seat_spawn_waiter_cli" in identity


def test_does_not_duplicate_spawn_only_helper() -> None:
    watch_src = WATCH_PY.read_text(encoding="utf-8")
    assert "reason=no-spawn" not in watch_src
    assert "no-watch" in watch_src
    assert "from director_turn_spawn import" not in watch_src
    assert "gcs-liv41-mind-must-launch" not in watch_src
    mind_src = MIND_PY.read_text(encoding="utf-8")
    assert "director_turn_watch" in mind_src
    assert "from director_turn_spawn import" not in mind_src
