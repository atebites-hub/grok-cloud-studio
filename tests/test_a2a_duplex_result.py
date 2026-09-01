"""FAT: director RESULT is duplex, not success.

Living Sky A2A duplex RESULT. Not LIV-85 hub-ack. Fake grok / no secrets.
RESULT-only / PONG is a documented bug. Never Bot CloudAgent.
Extra High pin: grok-4.6 xhigh fast=false.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
DUPLEX_PY = REPO / "scripts" / "a2a" / "duplex.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
ACP_INJECT = REPO / "scripts" / "directors" / "acp_inject.py"
DISPATCH_PY = REPO / "scripts" / "a2a" / "dispatch.py"
TICKER_PY = REPO / "scripts" / "a2a" / "host-ticker.py"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
A2A_DOC = REPO / "docs" / "A2A.md"
AGENTS_DOC = REPO / "AGENTS.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
FEATURE = REPO / "docs" / "studio" / "bdd" / "a2a_duplex_result.feature"
A2A_RULE = REPO / "plugins" / "a2a" / "rules" / "a2a.mdc"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
LIB_PY = REPO / "scripts" / "a2a" / "lib.py"
SDK_COMMON = REPO / "scripts" / "cloud" / "sdk" / "common.ts"

RESULT_LINE = (
    "RESULT bc-id=bc-fat-1 pr=https://github.com/atebites-hub/grok-cloud-studio/pull/99 "
    "a2a=task-fat-1 notes=launched"
)
PONG_LINE = "PONG"
HUB_ACK = "ACK seat=floor messageId=m-hub-1"
CANONICAL_RESULT = (
    "RESULT bc-id=<id or none> pr=<url or none> a2a=<task-id or none> notes=<one line>"
)
BUG_PHRASE = "RESULT-only / PONG is a bug"
DUPLEX_PHRASE = "RESULT is duplex, not success"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fold(text: str) -> str:
    return " ".join(text.split()).lower()


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _append_inbox(
    state: Path, seat: str, task_id: str, text: str, *, from_seat: str = "ops"
) -> Path:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-fat-1",
        "parts": [
            {"kind": "text", "text": text},
            {"kind": "data", "data": {"from": from_seat}},
        ],
        "from": from_seat,
        "metadata": {"from": from_seat},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def test_feature_file_states_duplex_not_liv85() -> None:
    assert FEATURE.is_file()
    text = FEATURE.read_text(encoding="utf-8")
    low = _fold(text)
    assert "result is duplex, not success" in low
    assert "bc-id=" in text and "pr=" in text and "a2a=" in text and "notes=" in text
    assert "result-only / pong is a bug" in low
    assert "liv-85" in low
    assert "does not clone" in low or "not clone" in low
    assert "hub-ack" in low or "hub ack" in low or "task_state_completed" in low
    assert "never bot cloudagent" in low
    assert "grok-4.6" in low and "xhigh" in low and "fast=false" in low
    assert "living sky" in low
    assert "never black swan" in low


def test_directors_print_canonical_result_line() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    a2a = A2A_DOC.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    rule = A2A_RULE.read_text(encoding="utf-8") if A2A_RULE.is_file() else ""
    lib = LIB_PY.read_text(encoding="utf-8")
    persist = SEAT_COMMON.read_text(encoding="utf-8")
    blob = "\n".join((footer, agents, a2a, mind, rule, persist))
    assert "bc-id=" in footer
    assert "pr=" in footer
    assert "a2a=" in footer
    assert "notes=" in footer
    assert CANONICAL_RESULT in footer
    for needle in ("bc-id=", "pr=", "a2a=", "notes="):
        assert needle in mind, f"MIND.md missing {needle}"
        assert needle in agents or needle in a2a, f"AGENTS/A2A missing {needle}"
    assert "RESULT bc-id=" in footer
    assert re.search(r"RESULT\s+bc-id=", footer)
    assert "duplex" in _fold(footer)
    assert "duplex" in _fold(rule)
    assert "RESULT is optional duplex" in lib or "RESULT is duplex" in lib


def test_result_only_pong_is_documented_as_a_bug() -> None:
    docs = (
        FOOTER.read_text(encoding="utf-8"),
        AGENTS_DOC.read_text(encoding="utf-8"),
        A2A_DOC.read_text(encoding="utf-8"),
        MIND_DOC.read_text(encoding="utf-8"),
        ARCH_DOC.read_text(encoding="utf-8"),
        SEAT_COMMON.read_text(encoding="utf-8"),
        TICKER_PY.read_text(encoding="utf-8"),
        DISPATCH_PY.read_text(encoding="utf-8"),
        LIB_PY.read_text(encoding="utf-8"),
        FEATURE.read_text(encoding="utf-8"),
    )
    joined = "\n".join(docs)
    low = _fold(joined)
    assert BUG_PHRASE.lower() in _fold(FOOTER.read_text(encoding="utf-8"))
    assert BUG_PHRASE.lower() in _fold(TICKER_PY.read_text(encoding="utf-8"))
    assert BUG_PHRASE.lower() in _fold(MIND_DOC.read_text(encoding="utf-8"))
    assert "pong" in low
    assert "hangup" in low or "hang-up" in low or "hangup-only" in low
    assert DUPLEX_PHRASE.lower() in _fold(AGENTS_DOC.read_text(encoding="utf-8"))
    assert DUPLEX_PHRASE.lower() in _fold(A2A_DOC.read_text(encoding="utf-8"))
    assert DUPLEX_PHRASE.lower() in _fold(FOOTER.read_text(encoding="utf-8"))
    assert DUPLEX_PHRASE.lower() in _fold(MIND_DOC.read_text(encoding="utf-8"))


def test_hub_ack_is_not_director_result() -> None:
    """LIV-85 hub COMPLETE / ACK is a receipt. Not this FAT's RESULT line."""
    duplex = _load(DUPLEX_PY, "gcs_duplex_fat_ack")
    assert duplex.extract_result_line(HUB_ACK) is None
    assert duplex.extract_result_line("A2A_SEND_OK") is None
    assert duplex.extract_result_line("TASK_STATE_COMPLETED") is None
    assert duplex.extract_result_line("kind=receipt") is None
    assert duplex.extract_result_line(PONG_LINE) is None
    assert duplex.extract_result_line("ok") is None
    assert duplex.extract_result_line(RESULT_LINE) == RESULT_LINE
    hub_src = (REPO / "scripts" / "a2a" / "hub.py").read_text(encoding="utf-8")
    send_src = (REPO / "scripts" / "a2a" / "send.sh").read_text(encoding="utf-8")
    assert "kind=receipt" not in send_src or "MIND_TURN" not in send_src
    assert "Simple ack hub" in hub_src


def test_duplex_writes_result_onto_task_and_skips_pong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplex = _load(DUPLEX_PY, "gcs_duplex_fat_write")
    state = tmp_path / "a2a-state"
    notified: list[tuple[str, str]] = []

    def fake_send(seat: str, text: str) -> bool:
        notified.append((seat, text))
        return True

    record = {
        "taskId": "task-fat-1",
        "contextId": "ctx-fat-1",
        "from": "ops",
        "parts": [{"kind": "data", "data": {"from": "ops"}}],
    }
    pong = duplex.duplex_from_output(
        state_dir=state,
        seat="floor",
        record=record,
        output_text=PONG_LINE,
        send_fn=fake_send,
    )
    assert pong.get("ok") is False
    assert pong.get("reason") == "no-result"
    assert not notified
    assert not (state / "floor" / "runs" / "task-fat-1.duplex").is_file()

    work = (
        "STATUS quoting token tick-1. Working.\n"
        f"{RESULT_LINE}\n"
    )
    out = duplex.duplex_from_output(
        state_dir=state,
        seat="floor",
        record=record,
        output_text=work,
        send_fn=fake_send,
    )
    assert out.get("ok") is True
    assert out.get("skipped") is None
    assert out.get("result") == RESULT_LINE
    assert out.get("caller") == "ops"
    assert out.get("notified") is True
    assert notified and notified[0][0] == "ops"
    assert "A2A_REPLY" in notified[0][1]
    assert RESULT_LINE in notified[0][1]
    marker = state / "floor" / "runs" / "task-fat-1.duplex"
    assert marker.is_file()
    tasks = json.loads((state / "floor" / "tasks.json").read_text(encoding="utf-8"))
    blob = json.dumps(tasks)
    assert RESULT_LINE in blob
    assert "bc-id=bc-fat-1" in blob
    assert "director-result" in blob
    again = duplex.duplex_from_output(
        state_dir=state,
        seat="floor",
        record=record,
        output_text=work,
        send_fn=fake_send,
    )
    assert again.get("skipped") == "already"
    assert len(notified) == 1


def test_result_only_is_hangup_not_inject_success() -> None:
    mod = _load(ACP_INJECT, "gcs_acp_fat_result_only")
    assert mod.seat_produced_work(RESULT_LINE) is False
    assert mod.seat_produced_work(PONG_LINE) is False
    assert mod.stream_is_hangup_only(RESULT_LINE) is True
    assert mod.stream_is_hangup_only(PONG_LINE) is True
    assert mod.prompt_chunk_is_accept_signal(RESULT_LINE) is False
    assert mod.prompt_chunk_is_accept_signal(PONG_LINE) is False
    assert mod.pin_session_ready_to_leave(RESULT_LINE) is False
    assert mod.pin_session_handoff_reason(RESULT_LINE) is None
    src = ACP_INJECT.read_text(encoding="utf-8")
    assert "duplex only" in src.lower() or "not success" in src.lower()
    assert "RESULT-only" in src


def test_a2a_reply_never_launches_bot_cloudagent() -> None:
    dispatch = _load(DISPATCH_PY, "gcs_dispatch_fat_reply")
    reply = (
        "A2A_REPLY seat=floor task=task-fat-1 context=ctx-1 "
        f"{RESULT_LINE}"
    )
    assert "A2A_REPLY" in dispatch._INJECT_ONLY_KINDS
    assert dispatch._is_cloud_launch_message(reply) is False
    extra = dispatch._compose_extra("task-fat-1", "ctx-1", reply)
    low = extra.lower()
    assert "never" in low
    assert "cursor cloud" in low or "launcher" in low
    assert "bot cloudagent" in _fold(A2A_DOC.read_text(encoding="utf-8"))
    assert "bot cloudagent" in _fold(FEATURE.read_text(encoding="utf-8"))
    assert "bot cloudagent" in _fold(MIND_DOC.read_text(encoding="utf-8"))
    footer = _fold(FOOTER.read_text(encoding="utf-8"))
    assert "a2a_reply" in footer
    assert "never launch" in footer
    mind_src = _fold(MIND_PY.read_text(encoding="utf-8"))
    assert "bot cloudagent" in mind_src or "never launch" in mind_src


def test_extra_high_stays_grok_46_xhigh_fast_false() -> None:
    launch = LAUNCH.read_text(encoding="utf-8")
    sdk = SDK_COMMON.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    feature = FEATURE.read_text(encoding="utf-8")
    for blob in (launch, sdk, cloud, feature):
        assert "grok-4.6" in blob
        assert "xhigh" in blob
        assert "fast" in blob and "false" in blob
    assert '"id": "grok-4.6"' in launch or "id: \"grok-4.6\"" in sdk
    assert 'value: "false"' in sdk or '"value": "false"' in launch


def test_mind_wrap_and_duplex_result_after_runner_exit_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind = _load(MIND_PY, "gcs_mind_fat_duplex")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    seen: list[str] = []
    notified: list[tuple[str, str]] = []

    def fake_send(seat: str, text: str) -> bool:
        notified.append((seat, text))
        return True

    monkeypatch.setattr(mind.a2a_duplex, "default_send", fake_send)

    def fake_runner(prompt: str, **_kwargs: Any) -> dict[str, str]:
        seen.append(prompt)
        return {
            "text": f"STATUS quoting token tick-1. Working.\n{RESULT_LINE}\n",
            "returncode": "0",
        }

    monkeypatch.setattr(mind, "DEFAULT_RUNNER", fake_runner)
    _append_inbox(state, "floor", "task-fat-1", "LAUNCH spawn Extra High for playability")
    out = mind.process_once("floor")
    assert out.get("consumed") == 1
    assert out.get("reason") == "ok"
    assert seen
    wrap = seen[0]
    assert "LAUNCH spawn Extra High for playability" in wrap
    assert "bc-id=" in wrap and "pr=" in wrap and "a2a=" in wrap and "notes=" in wrap
    assert BUG_PHRASE in wrap
    assert "duplex, not success" in wrap.lower() or DUPLEX_PHRASE.lower() in wrap.lower()
    assert "Bot CloudAgent" in wrap or "bot cloudagent" in wrap.lower()
    marker = state / "floor" / "runs" / "task-fat-1.duplex"
    assert marker.is_file()
    tasks = json.loads((state / "floor" / "tasks.json").read_text(encoding="utf-8"))
    assert RESULT_LINE in json.dumps(tasks)
    assert notified and notified[0][0] == "ops"
    assert "A2A_REPLY" in notified[0][1]


def test_mind_pong_only_does_not_duplex_and_is_not_result_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind = _load(MIND_PY, "gcs_mind_fat_pong")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    notified: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mind.a2a_duplex, "default_send", lambda seat, text: notified.append((seat, text)) or True
    )

    def fake_runner(prompt: str, **_kwargs: Any) -> dict[str, str]:
        assert BUG_PHRASE in prompt
        return {"text": PONG_LINE, "returncode": "0"}

    monkeypatch.setattr(mind, "DEFAULT_RUNNER", fake_runner)
    _append_inbox(state, "floor", "task-pong-1", "ACP_PING STATUS/CONTINUE")
    out = mind.process_once("floor")
    # Mailbox consume is runner exit 0 (not PONG). PONG is not a RESULT duplex.
    assert out.get("consumed") == 1
    assert out.get("reason") == "ok"
    assert not notified
    assert not (state / "floor" / "runs" / "task-pong-1.duplex").is_file()
    assert not (state / "floor" / "tasks.json").is_file()
