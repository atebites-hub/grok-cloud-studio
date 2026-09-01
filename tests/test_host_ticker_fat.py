"""FAT: host-ticker.py enqueues ACP_PING STATUS/CONTINUE work turns.

Tools allowed. Never RESULT-only / PONG keep-alives. Never a LAUNCH kind.
Distinct from LIV-85 hub-COMPLETE-is-receipt (#61/#67/#83/#106).
Does not start bot-bridge. Never Bot CloudAgent. Fake grok / no secrets.
Extra High pin: grok-4.6 xhigh fast=false. Palemon Linear is Living Sky LIV.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
TICKER_PY = REPO / "scripts" / "a2a" / "host-ticker.py"
CLOCK_SH = REPO / "scripts" / "directors" / "host-clock-ticker.sh"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
HUB_PY = REPO / "scripts" / "a2a" / "hub.py"
SEND_SH = REPO / "scripts" / "a2a" / "send.sh"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
SDK_COMMON = REPO / "scripts" / "cloud" / "sdk" / "common.ts"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
WATCHDOG = REPO / "scripts" / "directors" / "watchdog-studio-ops.sh"
A2A_DOC = REPO / "docs" / "A2A.md"
AGENTS_DOC = REPO / "AGENTS.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
FEATURE = REPO / "tests" / "features" / "host_ticker_acp_ping_work_turn.feature"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"

BUG_PHRASE = "RESULT-only / PONG is a bug"
PONG_ONLY_RE = re.compile(r"^\s*(PONG|pong|ok|OK)\s*$")
RESULT_ONLY_RE = re.compile(r"^\s*RESULT\b", re.I)
LIV85_SIBLINGS = ("#61", "#67", "#83", "#106")


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fold(text: str) -> str:
    return " ".join(text.split()).lower()


def _part_text(rec: dict) -> str:
    text = ""
    for part in rec.get("parts") or []:
        if isinstance(part, dict) and part.get("text"):
            text += str(part["text"])
    return text


def _inbox_records(inbox: Path) -> list[dict]:
    assert inbox.is_file(), f"missing inbox {inbox}"
    rows: list[dict] = []
    for line in inbox.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    assert rows, f"empty inbox {inbox}"
    return rows


def _ticker_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "LC_ALL": "C",
        "TERM": "dumb",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _assert_work_turn(rec: dict, *, seat: str) -> str:
    """Inbox record is an ACP_PING STATUS/CONTINUE work turn, not hang-up / LAUNCH."""
    text = _part_text(rec)
    low = text.lower()
    kind = str(rec.get("kind") or "")
    assert kind.lower() != "launch", rec
    assert kind.lower() == "message", rec
    assert rec.get("role") == "user", rec
    assert rec.get("contextId") == "host-clock", rec
    assert "ACP_PING" in text
    assert "STATUS" in text and "CONTINUE" in text
    assert f"seat={seat}" in text
    assert text.startswith("ACP_PING")
    assert "tools are allowed" in low
    assert "taskboard ticket move" in low
    assert "send.sh" in low
    assert "launch-cloud-extra-high.sh" in low
    assert BUG_PHRASE.lower() in low
    assert "do not idle" in low
    assert "quote token" in low
    assert "LAUNCH ONLY" not in text
    assert "Do not use tools" not in text
    assert "Do not LAUNCH" not in text
    stripped = text.strip()
    assert PONG_ONLY_RE.match(stripped) is None, text
    assert RESULT_ONLY_RE.match(stripped) is None, text
    assert "TASK_STATE_COMPLETED" not in text
    assert "A2A_SEND_OK" not in text
    assert "kind=receipt" not in low
    return text


def _assert_no_bot_bridge(state: Path) -> None:
    assert not (state / "bot-bridge.pid").is_file()
    assert not (state / "bot-bridge.log").is_file()
    assert not (state / "bot-bridge.offset").is_file()
    for path in state.rglob("bot-wake.txt"):
        raise AssertionError(f"ticker must not write bot-wake {path}")
    for path in state.rglob("bot-wake.jsonl"):
        raise AssertionError(f"ticker must not write bot-wake {path}")


def test_fat_gherkin_names_work_turn_not_liv85_not_pong() -> None:
    assert FEATURE.is_file()
    text = FEATURE.read_text(encoding="utf-8")
    low = _fold(text)
    assert "acp_ping" in low and "status/continue" in low
    assert "tools allowed" in low or "tools are allowed" in low
    assert "result-only" in low and "pong" in low
    assert "launch" in low
    assert "never bot cloudagent" in low
    assert "grok-4.6" in low and "xhigh" in low and "fast=false" in low
    assert "living sky" in low
    assert "never black swan" in low
    assert "liv-85" in low
    assert "does not clone" in low or "not clone" in low
    assert "task_state_completed" in low
    assert "bot-bridge" in low
    for sibling in LIV85_SIBLINGS:
        assert sibling in text, sibling
    assert "host-ticker.py" in text


def test_fat_host_ticker_once_enqueues_work_turns_not_pong_or_launch(
    tmp_path: Path,
) -> None:
    env = _ticker_env(tmp_path)
    state = Path(env["GCS_A2A_STATE"])
    proc = subprocess.run(
        [
            sys.executable,
            str(TICKER_PY),
            "--once",
            "--seats",
            "floor,ops",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "TICKER_ENQUEUE" in proc.stdout or "HOST_CLOCK_ENQUEUE" in blob, blob
    assert "BOT_BRIDGE" not in blob
    _assert_no_bot_bridge(state)
    for seat in ("floor", "ops"):
        recs = _inbox_records(state / seat / "inbox.jsonl")
        assert len(recs) == 1, recs
        _assert_work_turn(recs[0], seat=seat)
        assert str(recs[0].get("kind") or "").lower() != "launch"
    assert not (state / "floor" / "mail.txt").is_file()
    assert not (state / "ops" / "mail.txt").is_file()
    assert not (state / "floor" / "mind").exists()


def test_fat_host_clock_enqueue_continue_same_work_turn(tmp_path: Path) -> None:
    env = _ticker_env(tmp_path)
    state = Path(env["GCS_A2A_STATE"])
    proc = subprocess.run(
        ["bash", str(CLOCK_SH), "enqueue_continue", "floor"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    recs = _inbox_records(state / "floor" / "inbox.jsonl")
    assert len(recs) == 1
    _assert_work_turn(recs[0], seat="floor")
    _assert_no_bot_bridge(state)


def test_fat_ticker_fallback_tick_text_when_clock_script_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticker = _load(TICKER_PY, "gcs_host_ticker_fat_fallback")
    state = tmp_path / "a2a-state"
    monkeypatch.setattr(ticker, "STATE_DIR", state)
    monkeypatch.setattr(ticker, "ROOT", REPO)
    monkeypatch.setattr(ticker, "CLOCK_SH", tmp_path / "missing-host-clock.sh")
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    n = ticker.tick_once(seats=("floor",), now=1_700_000_000.0)
    assert n == 1
    recs = _inbox_records(state / "floor" / "inbox.jsonl")
    text = _assert_work_turn(recs[0], seat="floor")
    assert "tick-floor-1700000000" in text or recs[0].get("taskId")
    fallback = ticker._tick_text("floor", "tick-floor-1")
    rec = {
        "kind": "message",
        "role": "user",
        "contextId": "host-clock",
        "parts": [{"kind": "text", "text": fallback}],
    }
    _assert_work_turn(rec, seat="floor")
    _assert_no_bot_bridge(state)


def test_fat_ticker_does_not_start_bot_bridge_or_clone_liv85() -> None:
    ticker_src = TICKER_PY.read_text(encoding="utf-8")
    clock_src = CLOCK_SH.read_text(encoding="utf-8")
    bus_src = BUS_SH.read_text(encoding="utf-8")
    for blob, label in ((ticker_src, "host-ticker.py"), (clock_src, "host-clock-ticker.sh")):
        assert "ACP_PING STATUS/CONTINUE" in blob, label
        assert "Tools are allowed" in blob, label
        assert BUG_PHRASE in blob, label
        assert "bot-bridge" not in blob, label
        assert "acp_inject" not in blob, label
        assert "TASK_STATE_COMPLETED" not in blob, label
        assert "mail.txt" not in blob, label
        assert "LAUNCH ONLY" not in blob, label
        assert "Do not use tools" not in blob, label
        assert "Bot CloudAgent" not in blob or "never" in blob.lower()
    assert "not a LAUNCH kind" in ticker_src or "not a LAUNCH" in ticker_src
    ticker_fn = bus_src.split("start_host_ticker() {", 1)[1].split("stop_host_ticker()", 1)[0]
    assert "TICKER_PY" in ticker_fn
    assert "host-ticker.py" in bus_src
    assert "bot-bridge" not in ticker_fn
    assert "BOT_BRIDGE" not in ticker_fn
    hub_src = HUB_PY.read_text(encoding="utf-8")
    send_src = SEND_SH.read_text(encoding="utf-8")
    assert "TASK_STATE_COMPLETED" in hub_src
    assert "A2A_SEND_OK" in send_src
    feature = FEATURE.read_text(encoding="utf-8")
    for sibling in LIV85_SIBLINGS:
        assert sibling in feature
    assert "does not clone" in _fold(feature) or "not clone" in _fold(feature)


def test_fat_docs_work_turn_living_sky_not_black_swan() -> None:
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    a2a = A2A_DOC.read_text(encoding="utf-8")
    arch = ARCH_DOC.read_text(encoding="utf-8")
    footer = FOOTER.read_text(encoding="utf-8")
    taskboard = TASKBOARD_DOC.read_text(encoding="utf-8")
    feature = FEATURE.read_text(encoding="utf-8")
    watchdog = WATCHDOG.read_text(encoding="utf-8")
    for blob, label in (
        (agents, "AGENTS.md"),
        (a2a, "docs/A2A.md"),
        (arch, "docs/ARCHITECTURE.md"),
        (footer, "common_footer.txt"),
    ):
        assert "ACP_PING" in blob, label
        assert "STATUS" in blob and "CONTINUE" in blob, label
    assert "Not PONG" in a2a or "not PONG" in a2a.lower()
    assert "LAUNCH kind" in a2a or "not a LAUNCH" in a2a
    assert "tools allowed" in _fold(a2a) or "tools are allowed" in _fold(a2a)
    assert BUG_PHRASE in footer
    assert "not a LAUNCH assigner" in taskboard or "not a LAUNCH" in taskboard
    assert "host-ticker" in watchdog
    assert "acp_inject.py" not in watchdog
    assert "living sky" in _fold(feature)
    assert "never black swan" in _fold(feature)
    assert "linear.app/livingsky" in _fold(feature)
    mind = MIND_DOC.read_text(encoding="utf-8")
    assert "Bot CloudAgent" in a2a or "Bot CloudAgent" in mind
    assert "Do not launch Bot CloudAgent" in a2a


def test_fat_extra_high_stays_grok_46_xhigh_fast_false_never_bot() -> None:
    launch = LAUNCH.read_text(encoding="utf-8")
    sdk = SDK_COMMON.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    feature = FEATURE.read_text(encoding="utf-8")
    for blob in (launch, sdk, cloud, feature):
        assert "grok-4.6" in blob
        assert "xhigh" in blob
        assert "fast" in blob and "false" in blob
    assert '"id": "grok-4.6"' in launch or 'id: "grok-4.6"' in sdk
    assert 'value: "false"' in sdk or '"value": "false"' in launch
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    skip = {str(s) for s in registry.get("skipSeats") or []}
    assert "orchestrator" in skip
    ticker_src = TICKER_PY.read_text(encoding="utf-8")
    assert "launch-cloud-extra-high.sh" in ticker_src
    assert "cursor-grok" not in ticker_src
    assert "Bot CloudAgent" not in ticker_src
    hermes = REPO / "vendor" / "hermes-agent"
    assert not hermes.exists()
