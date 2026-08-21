"""Inbox.jsonl → ACP session/prompt into live grok agent serve.

Pin acp.session. Never grok --resume. Never Agent Kanban. Dispatch does
not own a seat inbox while wake.pid is live.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
WAKE_PY = ROOT / "scripts" / "a2a" / "wake-daemon.py"
SEAT_PROMPT = ROOT / "scripts" / "a2a" / "seat-prompt-acp.sh"
ACP_INJECT = ROOT / "scripts" / "directors" / "acp_inject.py"
DISPATCH_PY = ROOT / "scripts" / "a2a" / "dispatch.py"
BUS_SH = ROOT / "scripts" / "a2a" / "start-studio-bus.sh"
COMMON_SH = ROOT / "scripts" / "directors" / "seat-daemon-common.sh"

SERVE_PID = 4242
ACP_SESSION = "sess-pinned-gcs-1"
LAUNCH_TEXT = (
    "TASK_ASSIGN: launch Extra High for the assigned outcome. Open a PR.\n"
    'scripts/launch-cloud-extra-high.sh "Implement the assigned outcome. Open a PR." "floor-demo"\n'
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
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def _noncomment(src: str) -> str:
    return "\n".join(
        line for line in src.splitlines() if line.strip() and not line.strip().startswith("#")
    )


def _prep_wake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, unique: str
) -> tuple[ModuleType, Path, list[dict]]:
    wake = _load(WAKE_PY, f"gcs_wake_{unique}")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    journal: list[dict] = []
    monkeypatch.setattr(wake, "STATE_DIR", state)
    monkeypatch.setattr(wake, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(ROOT))

    def fake_ensure(seat: str) -> int:
        sd = state / seat
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "daemon.pid").write_text(f"{SERVE_PID}\n", encoding="utf-8")
        (sd / "acp.url").write_text("ws://127.0.0.1:8740/ws\n", encoding="utf-8")
        (sd / "acp.secret").write_text("secret\n", encoding="utf-8")
        sess = sd / "acp.session"
        if not sess.is_file():
            sess.write_text(ACP_SESSION + "\n", encoding="utf-8")
        (sd / "wake.mode").write_text(
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
                    "GCS_DIRECTOR_SEAT": env.get("GCS_DIRECTOR_SEAT", ""),
                    "GCS_A2A_TASK_ID": env.get("GCS_A2A_TASK_ID", ""),
                    "GCS_A2A_FROM": env.get("GCS_A2A_FROM", ""),
                    "GROK_HOME": env.get("GROK_HOME", ""),
                },
            }
        )
        return 0

    monkeypatch.setattr(wake, "ensure_seat_serve", fake_ensure)
    monkeypatch.setattr(wake, "prompt_acp", fake_prompt)
    return wake, state, journal


def test_wake_scripts_exist() -> None:
    assert WAKE_PY.is_file()
    assert SEAT_PROMPT.is_file()
    assert ACP_INJECT.is_file()
    assert WAKE_PY.stat().st_mode & stat.S_IXUSR
    assert SEAT_PROMPT.stat().st_mode & stat.S_IXUSR


def test_seat_prompt_acp_pins_session_and_never_resumes() -> None:
    prompt_sh = SEAT_PROMPT.read_text(encoding="utf-8")
    noncomment = _noncomment(prompt_sh)
    assert "acp_inject.py" in prompt_sh
    assert "--pin-session" in prompt_sh
    assert "--force-new-session" not in noncomment
    assert "--resume" not in noncomment
    assert "agent-kanban" not in prompt_sh.lower()
    assert "ak start" not in noncomment
    assert "ensure_seat_serve" in prompt_sh or "start-seat-daemon" in prompt_sh


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
    assert journal, "wake must ACP-prompt the live serve"
    assert "MESSAGE:" in journal[0]["prompt"] or "TASK_ASSIGN" in journal[0]["prompt"]
    offset = int((state / "floor" / "wake.offset").read_text(encoding="utf-8").strip())
    assert offset > 0
    assert not (state / "floor" / "dispatch.offset").is_file()
    mode = (state / "floor" / "wake.mode").read_text(encoding="utf-8")
    assert "grok-build-serve" in mode
    assert "inbox-acp-prompt" in mode
    assert "acp-serve" in mode

    _append_inbox(state, "floor", "task-wake-2", "STATUS: second ping. Print RESULT.")
    second = wake.process_once("floor")
    assert second["consumed"] == 1
    assert second["serve_pid"] == first["serve_pid"] == SERVE_PID
    assert second["acp_session"] == first["acp_session"] == ACP_SESSION
    assert len(journal) == 2
    src = WAKE_PY.read_text(encoding="utf-8")
    assert "GROK_BIN" not in src
    assert "pin_session_uuid" not in src
    assert "session.uuid" not in src
    assert '"--resume"' not in src
    assert "'--resume'" not in src
    assert "prompt_acp" in src
    assert "ensure_seat_serve" in src
    assert "agent-kanban" not in src.lower()
    assert "ak start" not in src
    assert "AMA-401" not in src


def test_pin_acp_session_never_remints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wake, state, _journal = _prep_wake(tmp_path, monkeypatch, unique="pin")
    seat_dir = state / "ops"
    seat_dir.mkdir(parents=True)
    pinned = "sess-never-remint"
    (seat_dir / "acp.session").write_text(pinned + "\n", encoding="utf-8")
    got = wake.pin_acp_session(seat_dir)
    assert got == pinned
    got2 = wake.pin_acp_session(seat_dir)
    assert got2 == pinned
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == pinned
    missing = wake.pin_acp_session(state / "cloud")
    assert missing == ""
    assert not (state / "cloud" / "acp.session").is_file()


def test_wake_prompt_fail_does_not_consume_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake, state, journal = _prep_wake(tmp_path, monkeypatch, unique="promptfail")
    monkeypatch.setattr(wake, "prompt_acp", lambda *_a, **_k: 1)
    _append_inbox(state, "floor", "task-hang-1", "STATUS: keep working. Print RESULT.")
    first = wake.process_once("floor")
    assert first["consumed"] == 0
    assert first["reason"] == "prompt-fail"
    offset_path = state / "floor" / "wake.offset"
    assert not offset_path.is_file() or int(offset_path.read_text(encoding="utf-8").strip() or "0") == 0
    second = wake.process_once("floor")
    assert second["consumed"] == 0
    assert second["reason"] == "prompt-fail"
    assert journal == []


def test_prompt_output_accepted_advances_on_handoff() -> None:
    wake = _load(WAKE_PY, "gcs_wake_handoff_accept")
    assert wake.prompt_output_accepted(0, "") is True
    assert wake.prompt_output_accepted(1, "ACP_INJECT_OK seat=floor session=s chars=0\n") is True
    assert wake.prompt_output_accepted(1, "ACP_INJECT_HANDOFF seat=floor session=s\n") is True
    assert wake.prompt_output_accepted(1, "ACP_INJECT_TIMEOUT seat=floor timeout=180\n") is False
    assert wake.prompt_output_accepted(1, "ACP_INJECT_FAIL seat=floor err=blocked\n") is False


def test_wake_backoffs_on_prompt_fail() -> None:
    wake = _load(WAKE_PY, "gcs_wake_backoff")
    assert hasattr(wake, "prompt_fail_backoff_sec")
    assert wake.prompt_fail_backoff_sec(1) >= 5
    assert wake.prompt_fail_backoff_sec(2) > wake.prompt_fail_backoff_sec(1)
    assert wake.prompt_fail_backoff_sec(20) <= 120
    src = WAKE_PY.read_text(encoding="utf-8")
    assert "WAKE_BACKOFF" in src
    assert "prompt-fail" in src


def test_dispatch_skips_live_wake_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch = _load(DISPATCH_PY, "gcs_dispatch_wake_skip")
    state = tmp_path / "a2a-state"
    inject_stamp = tmp_path / "inject.extra"
    fake_inject = _write_exec(
        tmp_path / "fake_acp_inject.py",
        "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
        f"Path({str(inject_stamp)!r}).write_text(sys.argv[-1], encoding='utf-8')\n",
    )
    monkeypatch.setattr(dispatch, "STATE_DIR", state)
    monkeypatch.setattr(dispatch, "ACP_INJECT", fake_inject)
    monkeypatch.setattr(dispatch, "_daemon_healthy", lambda _seat: True)
    monkeypatch.setattr(dispatch, "_ensure_daemon", lambda _seat: True)
    monkeypatch.setattr(dispatch, "_CHILDREN", {})
    monkeypatch.setattr(dispatch, "_skip_seats", lambda: frozenset())
    monkeypatch.setattr(dispatch, "_launch_seats", lambda: frozenset({"floor", "ops", "cloud", "qa-a", "qa-b"}))

    _append_inbox(state, "floor", "task-skip-1", LAUNCH_TEXT)
    (state / "floor" / "wake.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    started = dispatch._process_seat("floor", dry_run=False)
    assert started == 0
    assert not inject_stamp.is_file()
    assert not (state / "floor" / "dispatch.offset").is_file()

    src = DISPATCH_PY.read_text(encoding="utf-8")
    assert "wake-owns-inbox" in src
    assert "wake.pid" in src


def test_bus_starts_wake_daemon_with_daemons() -> None:
    bus = BUS_SH.read_text(encoding="utf-8")
    noncomment = _noncomment(bus)
    assert "wake-daemon.py" in bus
    assert "start-seat-daemon.sh" in noncomment
    assert "ak start" not in noncomment.lower() or "never" in bus.lower()
    common = COMMON_SH.read_text(encoding="utf-8")
    assert "ensure_seat_serve" in common


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
    wake = _load(WAKE_PY, "gcs_wake_auth")
    monkeypatch.setattr(wake, "STATE_DIR", state)
    monkeypatch.setattr(wake, "ROOT", ROOT)
    monkeypatch.setenv("GROK_AUTH_JSON", str(src))
    monkeypatch.setenv("HOME", str(tmp_path))
    seat_dir = state / "ops"
    wake.prepare_seat_home("ops", seat_dir)
    dest = seat_dir / "grok-home" / "auth.json"
    assert dest.is_file()
    assert json.loads(dest.read_text(encoding="utf-8")) == auth


def test_studio_ops_alias_uses_ops_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake, state, journal = _prep_wake(tmp_path, monkeypatch, unique="alias")
    _append_inbox(state, "ops", "task-ops-1", "STATUS: studio-ops alias. Print RESULT.")
    result = wake.process_once("studio-ops")
    assert result["consumed"] == 1
    assert journal
    assert journal[0]["seat"] == "ops"
    assert journal[0]["env"]["GCS_DIRECTOR_SEAT"] == "ops"
