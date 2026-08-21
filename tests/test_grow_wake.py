"""GROW: persistent grok agent serve + local ACP session/prompt.

Peer mail is inbox.jsonl → wake loop → ACP session/prompt into the live
`grok agent serve` pid. Same serve + same pinned acp.session. NOT grok
--resume. NOT dispatch ACP inject. Host ticker enqueues keep-alives.
Agent Kanban is dead. Fake serve/prompt only — no live grok CLI, no secrets.
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
WAKE_PY = REPO / "scripts" / "a2a" / "wake-daemon.py"
TICKER_PY = REPO / "scripts" / "a2a" / "host-ticker.py"
HOST_CLOCK_SH = REPO / "scripts" / "directors" / "host-clock-ticker.sh"
DISPATCH_PY = REPO / "scripts" / "a2a" / "dispatch.py"
SEND_SH = REPO / "scripts" / "a2a" / "send.sh"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
WATCHDOG = REPO / "scripts" / "directors" / "watchdog-studio-ops.sh"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
START_DAEMON = REPO / "scripts" / "directors" / "start-seat-daemon.sh"
WAKE_LOOP = REPO / "scripts" / "directors" / "seat-wake-loop.sh"
SEAT_PROMPT = REPO / "scripts" / "directors" / "seat-prompt-acp.sh"
ACP_INJECT = REPO / "scripts" / "directors" / "acp_inject.py"
A2A_DOC = REPO / "docs" / "A2A.md"
AGENTS_DOC = REPO / "AGENTS.md"
TASKBOARD = REPO / "docs" / "studio" / "TASKBOARD.md"
SOULS = REPO / "docs" / "studio" / "directors" / "souls"

GROW_SEATS = ("floor", "ops")
SERVE_PID = 4242
ACP_SESSION = "sess-pinned-grow-1"
A2A_REPLY_TEXT = (
    "A2A_REPLY seat=floor task=task-reply-1 context=ctx-1 "
    "RESULT bc-id=none pr=none notes=done"
)
LAUNCH_TEXT = (
    "LAUNCH ONLY\n"
    'scripts/launch-cloud-extra-high.sh --name floor-iac '
    '"Director owns Cursor Cloud launch."\n'
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


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> Path:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-1",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "floor"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def _noncomment(src: str) -> str:
    return "\n".join(
        line for line in src.splitlines() if line.strip() and not line.strip().startswith("#")
    )


def _part_text(rec: dict) -> str:
    text = ""
    for part in rec.get("parts") or []:
        if isinstance(part, dict) and part.get("text"):
            text += str(part["text"])
    return text


def _assert_keepalive_clock_text(text: str) -> None:
    low = text.lower()
    assert "ACP_PING" in text
    assert "STATUS" in text and "CONTINUE" in text
    assert "LAUNCH ONLY" not in text
    assert "Do not use tools" not in text
    assert "do not use tools" not in low
    assert "Do not LAUNCH" not in text
    assert "do not launch" not in low
    assert "quoting token then RESULT" not in text
    assert "do not idle" in low
    assert "result-only" in low
    assert "tools are allowed" in low
    assert "ticket move" in low
    assert "send.sh" in low
    assert "launch-cloud-extra-high.sh" in low


def _prep_wake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, unique: str
) -> tuple[ModuleType, Path, list[dict]]:
    wake = _load(WAKE_PY, f"gcs_wake_{unique}")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    journal: list[dict] = []
    monkeypatch.setattr(wake, "STATE_DIR", state)
    monkeypatch.setattr(wake, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))

    def fake_ensure(seat: str) -> int:
        sd = state / seat
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "daemon.pid").write_text(f"{SERVE_PID}\n", encoding="utf-8")
        (sd / "acp.url").write_text("ws://127.0.0.1:8740/ws\n", encoding="utf-8")
        (sd / "acp.secret").write_text("secret\n", encoding="utf-8")
        sess = sd / "acp.session"
        if not sess.is_file():
            sess.write_text(ACP_SESSION + "\n", encoding="utf-8")
        (sd / "grow.mode").write_text(
            "kind=grok-build-serve\nawake=inbox-acp-prompt\nmode=acp-serve\n",
            encoding="utf-8",
        )
        return SERVE_PID

    def fake_prompt(seat: str, prompt: str, env: dict[str, str]) -> int:
        journal.append(
            {
                "seat": seat,
                "prompt": prompt,
                "env": {
                    "GROK_MEMORY": env.get("GROK_MEMORY", ""),
                    "GROK_HOME": env.get("GROK_HOME", ""),
                    "GCS_DIRECTOR_SEAT": env.get("GCS_DIRECTOR_SEAT", ""),
                    "GCS_A2A_TASK_ID": env.get("GCS_A2A_TASK_ID", ""),
                    "GCS_A2A_FROM": env.get("GCS_A2A_FROM", ""),
                },
            }
        )
        return 0

    monkeypatch.setattr(wake, "ensure_seat_serve", fake_ensure)
    monkeypatch.setattr(wake, "prompt_acp", fake_prompt)
    return wake, state, journal


def test_grow_scripts_exist() -> None:
    assert WAKE_PY.is_file()
    assert TICKER_PY.is_file()
    assert WAKE_LOOP.is_file()
    assert SEAT_PROMPT.is_file()
    assert HOST_CLOCK_SH.is_file()
    for path in (WAKE_PY, TICKER_PY, WAKE_LOOP, SEAT_PROMPT, HOST_CLOCK_SH):
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        assert path.stat().st_mode & stat.S_IXUSR


def test_wake_consumes_inbox_and_acp_prompts_same_serve_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake, state, journal = _prep_wake(tmp_path, monkeypatch, unique="serve")
    _append_inbox(state, "floor", "task-wake-1", LAUNCH_TEXT)
    first = wake.process_once("floor")
    assert first["consumed"] == 1
    assert first["serve_pid"] == SERVE_PID
    assert first["acp_session"] == ACP_SESSION
    pin = (state / "floor" / "acp.session").read_text(encoding="utf-8").strip()
    assert pin == ACP_SESSION
    assert journal
    assert "MESSAGE:" in journal[0]["prompt"] or "LAUNCH ONLY" in journal[0]["prompt"]
    offset = int((state / "floor" / "wake.offset").read_text(encoding="utf-8").strip())
    assert offset > 0
    assert not (state / "floor" / "dispatch.offset").is_file()
    assert not (state / "floor" / "runs").exists()
    grow = (state / "floor" / "grow.mode").read_text(encoding="utf-8")
    assert "grok-build-serve" in grow
    assert "inbox-acp-prompt" in grow
    assert "acp-serve" in grow

    _append_inbox(state, "floor", "task-wake-2", "TASK_ASSIGN: second ping. Open a PR.")
    second = wake.process_once("floor")
    assert second["consumed"] == 1
    assert second["serve_pid"] == first["serve_pid"] == SERVE_PID
    assert second["acp_session"] == first["acp_session"] == ACP_SESSION
    assert len(journal) == 2
    src = WAKE_PY.read_text(encoding="utf-8")
    assert "GROK_BIN" not in src
    assert '"--resume"' not in src
    assert "'--resume'" not in src
    assert "prompt_acp" in src
    assert "ensure_seat_serve" in src
    assert "/runs/" not in src


def test_wake_never_forks_grok_resume_or_dispatch_inject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake, state, journal = _prep_wake(tmp_path, monkeypatch, unique="no-resume")
    prompt_sh = SEAT_PROMPT.read_text(encoding="utf-8")
    loop_sh = WAKE_LOOP.read_text(encoding="utf-8")
    assert "acp_inject.py" in prompt_sh
    assert "--pin-session" in prompt_sh
    assert "--force-new-session" not in _noncomment(prompt_sh)
    assert "ensure_seat_serve" in loop_sh
    assert "wake-daemon.py" in loop_sh
    _append_inbox(state, "ops", "task-mail-1", "STATUS: check PARK then idle. Print RESULT.")
    result = wake.process_once("ops")
    assert result["consumed"] == 1
    assert result["serve_pid"] == SERVE_PID
    assert journal
    blob = journal[0]["prompt"]
    assert "launch-cloud-extra-high.sh" not in blob.split()
    src = WAKE_PY.read_text(encoding="utf-8")
    assert "prompt_acp" in src


def test_named_identity_soul_memory_and_acp_session_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake, state, journal = _prep_wake(tmp_path, monkeypatch, unique="soul")
    for seat in GROW_SEATS:
        soul = SOULS / seat / "SOUL.md"
        assert soul.is_file(), f"missing named identity {soul}"
        text = soul.read_text(encoding="utf-8")
        assert seat.replace("-", " ") in text.lower() or seat in text.lower()
        assert "SOUL" in text or "named identity" in text.lower() or "You are" in text
    _append_inbox(state, "ops", "task-ops-1", "TASK_ASSIGN: bus health. Open a PR.")
    result = wake.process_once("ops")
    assert result["consumed"] == 1
    soul_dst = state / "ops" / "SOUL.md"
    assert soul_dst.is_file()
    mem = state / "ops" / "MEMORY.md"
    assert mem.is_file()
    assert journal
    env0 = journal[-1]["env"]
    assert env0["GROK_MEMORY"] == "1"
    assert env0["GCS_DIRECTOR_SEAT"] == "ops"
    assert "ops" in env0["GROK_HOME"]
    daemon = START_DAEMON.read_text(encoding="utf-8")
    assert "GROK_MEMORY" in daemon
    assert "GROK_HOME" in daemon
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "SOUL.md" in common
    assert "install_seat_identity" in common


def test_pin_acp_session_never_remints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wake, state, _journal = _prep_wake(tmp_path, monkeypatch, unique="pin")
    seat_dir = state / "cloud"
    seat_dir.mkdir(parents=True)
    pinned = "sess-never-remint"
    (seat_dir / "acp.session").write_text(pinned + "\n", encoding="utf-8")
    got = wake.pin_acp_session(seat_dir)
    assert got == pinned
    got2 = wake.pin_acp_session(seat_dir)
    assert got2 == pinned
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == pinned
    missing = wake.pin_acp_session(state / "qa-a")
    assert missing == ""
    assert not (state / "qa-a" / "acp.session").is_file()


def test_dispatch_grow_seat_and_live_wake_pid_skip_acp_inject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch = _load(DISPATCH_PY, "gcs_dispatch_grow_skip")
    state = tmp_path / "a2a-state"
    inject_stamp = tmp_path / "inject.extra"
    fake_inject = _write_exec(
        tmp_path / "fake_acp_inject.py",
        "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
        f"Path({str(inject_stamp)!r}).write_text(sys.argv[-1], encoding='utf-8')\n",
    )
    monkeypatch.setattr(dispatch, "STATE_DIR", state)
    monkeypatch.setattr(dispatch, "ACP_INJECT", fake_inject)
    monkeypatch.setattr(dispatch, "GROW_SEATS", frozenset({"floor", "ops", "studio-ops"}))
    monkeypatch.setattr(dispatch, "_daemon_healthy", lambda seat: True)
    monkeypatch.setattr(dispatch, "_ensure_daemon", lambda seat: True)
    monkeypatch.setattr(dispatch, "_CHILDREN", {})
    _append_inbox(state, "floor", "task-skip-1", LAUNCH_TEXT)
    started = dispatch._process_seat("floor", dry_run=False)
    assert started == 0
    assert not inject_stamp.is_file()
    assert not (state / "floor" / "dispatch.offset").is_file()

    qa = state / "qa-a"
    qa.mkdir(parents=True)
    (qa / "wake.pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    _append_inbox(state, "qa-a", "task-skip-wake", LAUNCH_TEXT)
    started_wake = dispatch._process_seat("qa-a", dry_run=False)
    assert started_wake == 0
    assert not inject_stamp.is_file()

    src = DISPATCH_PY.read_text(encoding="utf-8")
    assert "wake-owns-inbox" in src
    assert "GROW_SEATS" in src
    assert "wake.pid" in src


def test_a2a_reply_classifier_never_launches() -> None:
    dispatch = _load(DISPATCH_PY, "gcs_dispatch_a2a_reply")
    assert "A2A_REPLY" in dispatch._INJECT_ONLY_KINDS
    assert dispatch._is_cloud_launch_message(A2A_REPLY_TEXT) is False
    extra = dispatch._compose_extra("task-reply-1", "ctx-1", A2A_REPLY_TEXT)
    low = extra.lower()
    assert "a2a_reply" in low or "duplex" in low
    assert "never" in low
    assert "--resume" not in extra


def test_a2a_reply_wake_does_not_spawn_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake, state, journal = _prep_wake(tmp_path, monkeypatch, unique="reply")
    _append_inbox(state, "cloud", "task-reply-1", A2A_REPLY_TEXT)
    result = wake.process_once("cloud")
    assert result["consumed"] == 1
    assert result["serve_pid"] == SERVE_PID
    assert journal
    blob = journal[0]["prompt"]
    assert "launch-cloud-extra-high.sh" not in blob.split()
    low = blob.lower()
    assert "a2a_reply" in low or "do not create" in low or "never" in low
    assert "--resume" not in blob


def test_host_ticker_enqueues_inbox_lines_not_launch_only_assigner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticker = _load(TICKER_PY, "gcs_host_ticker")
    state = tmp_path / "a2a-state"
    monkeypatch.setattr(ticker, "STATE_DIR", state)
    monkeypatch.setattr(ticker, "ROOT", REPO)
    n = ticker.tick_once(seats=("floor", "ops"))
    assert n == 2
    for seat in ("floor", "ops"):
        inbox = state / seat / "inbox.jsonl"
        assert inbox.is_file()
        rec = json.loads(inbox.read_text(encoding="utf-8").splitlines()[0])
        text = _part_text(rec)
        _assert_keepalive_clock_text(text)
        assert str(rec.get("kind") or "").lower() != "launch"
    fallback = ticker._tick_text("floor", "tick-floor-1")
    _assert_keepalive_clock_text(fallback)
    src = TICKER_PY.read_text(encoding="utf-8")
    assert "Do not LAUNCH" not in src
    assert "Do not use tools" not in src
    assert "acp_inject" not in src
    assert "floor-manager-assign" not in src
    assigner = REPO / "scripts" / "directors" / "floor-manager-assign.py"
    assert not assigner.exists()
    watchdog = WATCHDOG.read_text(encoding="utf-8")
    assert "acp_inject.py" not in watchdog
    assert "host-ticker" in watchdog
    assert "seat-wake-loop" in watchdog or "start-seat-daemon" in watchdog


def test_host_clock_ticker_enqueues_acp_ping_status_continue_tools_allowed(
    tmp_path: Path,
) -> None:
    assert HOST_CLOCK_SH.is_file()
    src = HOST_CLOCK_SH.read_text(encoding="utf-8")
    assert "enqueue_continue" in src
    assert "ACP_PING" in src
    assert "STATUS" in src and "CONTINUE" in src
    assert "acp_inject" not in src
    assert "Do not use tools" not in src
    assert "Do not LAUNCH" not in src
    assert "LAUNCH ONLY" not in src
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "LC_ALL": "C",
    }
    proc = subprocess.run(
        ["bash", str(HOST_CLOCK_SH), "enqueue_continue", "floor"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    inbox = tmp_path / "a2a-state" / "floor" / "inbox.jsonl"
    assert inbox.is_file(), out
    rec = json.loads(inbox.read_text(encoding="utf-8").splitlines()[0])
    text = _part_text(rec)
    assert text.startswith("ACP_PING")
    _assert_keepalive_clock_text(text)
    kind = str(rec.get("kind") or "")
    assert kind.lower() != "launch"


def test_scripts_clock_copy_does_not_forbid_launch_or_tools() -> None:
    offenders: list[str] = []
    scripts = REPO / "scripts"
    for path in scripts.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".sh", ".txt", ".md"}:
            continue
        blob = path.read_text(encoding="utf-8", errors="replace")
        if "Do not LAUNCH" in blob or "Do not use tools" in blob:
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_bus_starts_serve_and_inbox_wake_loops() -> None:
    bus = BUS_SH.read_text(encoding="utf-8")
    noncomment = _noncomment(bus)
    assert "seat-wake-loop.sh" in bus
    assert "start-seat-daemon.sh" in noncomment
    assert "host-ticker.py" in noncomment
    assert "GCS_ACP_STOP_WITH_BUS" in bus
    assert "floor" in bus and "studio-ops" in bus
    assert "ak-bridge" not in bus
    assert "agent-kanban" not in bus
    loop = WAKE_LOOP.read_text(encoding="utf-8")
    assert "inbox-acp-prompt" in loop or "acp-serve" in loop
    assert "ensure_seat_serve" in loop


def test_send_sh_is_inbox_path_not_result_and_die_inject() -> None:
    send = SEND_SH.read_text(encoding="utf-8")
    assert "acp_inject" not in send
    wake = WAKE_PY.read_text(encoding="utf-8")
    assert "prompt_acp" in wake
    assert "session/prompt" in wake.lower() or "ACP_PROMPT" in wake
    footer = FOOTER.read_text(encoding="utf-8").lower()
    assert "idle for the next inject" not in footer
    assert "session/prompt" in footer or "seat-wake-loop" in footer or "seat-prompt-acp" in footer
    a2a = A2A_DOC.read_text(encoding="utf-8").lower()
    agents = AGENTS_DOC.read_text(encoding="utf-8").lower()
    blob = a2a + "\n" + agents
    assert "session/prompt" in blob
    assert "grok agent serve" in blob
    assert "seat-wake-loop" in blob or "wake-daemon" in blob
    assert "soul.md" in blob
    assert "host ticker" in blob or "host-ticker" in blob


def test_control_plane_does_not_ship_agent_kanban_worker() -> None:
    mint = REPO / "scripts" / "studio" / "agent-kanban" / "mint-floor-ops-worker.sh"
    assert not mint.exists()
    ak_dir = REPO / "scripts" / "studio" / "agent-kanban"
    assert not ak_dir.exists()
    assert not (REPO / "docs" / "studio" / "AGENT_KANBAN.md").exists()
    bus = BUS_SH.read_text(encoding="utf-8")
    assert "mint-floor-ops-worker" not in bus
    assert "AMA-401" not in bus
    assert "ak start" not in bus or "never" in bus.lower()
    ticker = TICKER_PY.read_text(encoding="utf-8")
    footer = FOOTER.read_text(encoding="utf-8")
    taskboard = TASKBOARD.read_text(encoding="utf-8")
    for blob in (bus, ticker, footer, taskboard):
        assert "AMA-401" not in blob
        assert "ak create task" not in blob
    assert "taskboard" in footer.lower()
    assert "tcarac/taskboard" in taskboard.lower()
    assert "Agent Kanban was removed" in footer or "Agent Kanban was removed" in taskboard


def test_seat_grok_home_gets_host_auth_json_cached_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host_grok = tmp_path / "host-grok"
    host_grok.mkdir()
    token = "test-cached-token-not-a-secret"
    auth = {"https://accounts.x.ai/sign-in": {"key": token}}
    src = host_grok / "auth.json"
    src.write_text(json.dumps(auth), encoding="utf-8")
    state = tmp_path / "a2a-state"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GROK_AUTH_JSON": str(src),
        "LC_ALL": "C",
    }
    proc = subprocess.run(
        [
            "bash",
            "-c",
            "source scripts/directors/seat-daemon-common.sh && install_seat_identity floor",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    dest = state / "floor" / "grok-home" / "auth.json"
    assert dest.is_file(), blob
    copied = json.loads(dest.read_text(encoding="utf-8"))
    assert copied == auth
    assert token not in blob
    assert "SEAT_GROK_AUTH_OK" in blob or "auth.json" in blob.lower()

    wake = _load(WAKE_PY, "gcs_wake_auth")
    monkeypatch.setattr(wake, "STATE_DIR", state)
    monkeypatch.setattr(wake, "ROOT", REPO)
    monkeypatch.setenv("GROK_AUTH_JSON", str(src))
    monkeypatch.setenv("HOME", str(tmp_path))
    ops = state / "ops"
    wake.ensure_identity("ops", ops)
    ops_auth = ops / "grok-home" / "auth.json"
    assert ops_auth.is_file()
    assert json.loads(ops_auth.read_text(encoding="utf-8")) == auth

    inject = ACP_INJECT.read_text(encoding="utf-8")
    assert "cached_token" in inject
    assert "authenticate" in inject
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "auth.json" in common
    assert "cached_token" in common or "GROK_AUTH_JSON" in common


def test_wake_backoffs_on_prompt_fail() -> None:
    wake = _load(WAKE_PY, "gcs_wake_backoff")
    assert hasattr(wake, "prompt_fail_backoff_sec")
    assert wake.prompt_fail_backoff_sec(1) >= 5
    assert wake.prompt_fail_backoff_sec(2) > wake.prompt_fail_backoff_sec(1)
    assert wake.prompt_fail_backoff_sec(20) <= 120
    src = WAKE_PY.read_text(encoding="utf-8")
    assert "WAKE_BACKOFF" in src
    assert "prompt-fail" in src
    assert "prompt_fail_backoff_sec" in src


def test_wake_prompt_fail_does_not_consume_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake, state, journal = _prep_wake(tmp_path, monkeypatch, unique="promptfail")
    monkeypatch.setattr(wake, "prompt_acp", lambda *a, **k: 1)
    _append_inbox(state, "floor", "task-hang-1", "PROVE-MIND: read docs then work.")
    first = wake.process_once("floor")
    assert first["consumed"] == 0
    assert first["reason"] == "prompt-fail"
    offset_path = state / "floor" / "wake.offset"
    assert not offset_path.is_file() or int(offset_path.read_text(encoding="utf-8").strip() or "0") == 0
    second = wake.process_once("floor")
    assert second["consumed"] == 0
    assert second["reason"] == "prompt-fail"
    assert journal == []


def test_prompt_output_accepted_advances_offset_before_model_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake = _load(WAKE_PY, "gcs_wake_handoff_accept")
    assert wake.prompt_output_accepted(0, "") is True
    assert wake.prompt_output_accepted(1, "ACP_INJECT_OK seat=floor session=s chars=0\n") is True
    assert wake.prompt_output_accepted(1, "ACP_INJECT_HANDOFF seat=floor session=s\n") is True
    assert wake.prompt_output_accepted(1, "ACP_INJECT_TIMEOUT seat=floor timeout=600\n") is False
    assert wake.prompt_output_accepted(1, "ACP_INJECT_FAIL seat=floor err=blocked\n") is False

    wake, state, journal = _prep_wake(tmp_path, monkeypatch, unique="handoff")
    _append_inbox(state, "floor", "task-handoff-1", "PROVE-MIND: move ticket in_progress.")
    first = wake.process_once("floor")
    assert first["consumed"] == 1
    offset = int((state / "floor" / "wake.offset").read_text(encoding="utf-8").strip())
    assert offset > 0
    second = wake.process_once("floor")
    assert second["consumed"] == 0
    assert second.get("reason") == "empty"
    assert len(journal) == 1
