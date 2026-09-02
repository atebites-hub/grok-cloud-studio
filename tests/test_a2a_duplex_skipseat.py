"""FAT: duplex A2A_REPLY must succeed after Director RESULT.

skipSeat donald has no shipped Agent Card — hub POST /a2a/donald/message:send
404s. Duplex must remap A2A_REPLY to floor-ops (then orchestrator) so notify
does not 404, and must not fail the working-seat task reply if ping is skipped.

Living Sky LIV. Distinct from leftover GCS #133/#99 (do not rebase).
Not LIV-85 / LIV-67 / LIV-41. Never Bot CloudAgent. Never vendor Hermes.
Extra High pin: grok-4.6 xhigh fast=false.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
DUPLEX_PY = REPO / "scripts" / "a2a" / "duplex.py"
DISPATCH_PY = REPO / "scripts" / "a2a" / "dispatch.py"
HUB_PY = REPO / "scripts" / "a2a" / "hub.py"
LIB_PY = REPO / "scripts" / "a2a" / "lib.py"
SEND_SH = REPO / "scripts" / "a2a" / "send.sh"
A2A_DOC = REPO / "docs" / "A2A.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
A2A_RULE = REPO / "plugins" / "a2a" / "rules" / "a2a.mdc"
FEATURE = REPO / "docs" / "studio" / "bdd" / "a2a_duplex_skipseat.feature"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
DONALD_CARD = REPO / "docs" / "a2a" / "cards" / "donald.json"
FLOOR_OPS_CARD = REPO / "docs" / "a2a" / "cards" / "floor-ops.json"
ORCH_CARD = REPO / "docs" / "a2a" / "cards" / "orchestrator.json"

RESULT_LINE = (
    "RESULT bc-id=bc-skip-1 pr=https://github.com/atebites-hub/grok-cloud-studio/pull/1849 "
    "a2a=task-skip-1 notes=duplex-skipseat-donald"
)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fold(text: str) -> str:
    return " ".join(text.split()).lower()


def _record(task_id: str, from_seat: str) -> dict:
    return {
        "taskId": task_id,
        "contextId": "ctx-skip-1",
        "from": from_seat,
        "parts": [{"kind": "data", "data": {"from": from_seat}}],
        "metadata": {"from": from_seat},
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def hub(tmp_path: Path):
    port = _free_port()
    state = tmp_path / "a2a-state"
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_A2A_HOST": "127.0.0.1",
        "GCS_A2A_PORT": str(port),
        "GCS_A2A_STATE": str(state),
        "GCS_A2A_HUB": f"http://127.0.0.1:{port}",
    }
    proc = subprocess.Popen(
        ["python3", str(HUB_PY)],
        cwd=str(REPO),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=0.3) as resp:
                if resp.status == 200:
                    yield {"url": url, "env": env, "state": state, "port": port}
                    proc.terminate()
                    proc.wait(timeout=3)
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.05)
    proc.kill()
    raise RuntimeError("hub did not start")


def test_feature_file_states_skipseat_not_liv85_clone() -> None:
    assert FEATURE.is_file()
    text = FEATURE.read_text(encoding="utf-8")
    low = _fold(text)
    assert "donald" in low
    assert "a2a_reply" in low
    assert "floor-ops" in low
    assert "skipseat" in low or "skipseats" in low
    assert "living sky" in low
    assert "never black swan" in low
    assert "never bot cloudagent" in low
    assert "grok-4.6" in low and "xhigh" in low and "fast=false" in low
    assert "never vendor hermes" in low
    assert "#133" in text or "133" in text
    assert "do not rebase" in low
    assert "liv-85" in low
    assert "does not clone" in low or "not clone" in low or "not a liv-85" in low
    assert "task_state_submitted" in low


def test_docs_name_donald_notify_and_keep_skipseats() -> None:
    a2a = A2A_DOC.read_text(encoding="utf-8")
    arch = ARCH_DOC.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    rule = A2A_RULE.read_text(encoding="utf-8") if A2A_RULE.is_file() else ""
    low = _fold("\n".join((a2a, arch, mind, rule)))
    assert "donald" in _fold(a2a)
    assert "floor-ops" in low or "orchestrator" in low
    assert "a2a_reply" in low
    assert "skipseats" in low or "skipseat" in low
    assert "receipt" in low
    duplex_src = DUPLEX_PY.read_text(encoding="utf-8")
    assert "floor-ops" in duplex_src
    assert "donald" in duplex_src
    assert "TASK_STATE_SUBMITTED" in duplex_src
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    skip = registry.get("skipSeats") or []
    assert "donald" in skip
    assert "orchestrator" in skip
    assert not DONALD_CARD.is_file()
    assert FLOOR_OPS_CARD.is_file()
    assert ORCH_CARD.is_file()


def test_resolve_notify_seat_maps_donald_to_floor_ops_then_orchestrator(
    tmp_path: Path,
) -> None:
    duplex = _load(DUPLEX_PY, "gcs_duplex_skip_resolve")
    assert duplex.resolve_notify_seat("donald") == "floor-ops"
    assert duplex.resolve_notify_seat("orchestrator") == "orchestrator"
    assert duplex.resolve_notify_seat("ops") == "ops"
    assert duplex.resolve_notify_seat("floor") == "floor"
    assert duplex.resolve_notify_seat("donald", working_seat="floor-ops") == "orchestrator"
    assert duplex.resolve_notify_seat("donald", working_seat="floor") == "floor-ops"

    root = tmp_path / "repo"
    cards = root / "docs" / "a2a" / "cards"
    cards.mkdir(parents=True)
    (cards / "orchestrator.json").write_text("{}\n", encoding="utf-8")
    assert duplex.resolve_notify_seat("donald", root=root) == "orchestrator"
    empty = tmp_path / "empty"
    (empty / "docs" / "a2a" / "cards").mkdir(parents=True)
    assert duplex.resolve_notify_seat("donald", root=empty) is None
    assert duplex.resolve_notify_seat("no-such-seat", root=empty) is None


def test_duplex_maps_donald_a2a_reply_to_floor_ops(tmp_path: Path) -> None:
    duplex = _load(DUPLEX_PY, "gcs_duplex_skip_map")
    state = tmp_path / "a2a-state"
    notified: list[tuple[str, str]] = []

    def fake_send(seat: str, text: str) -> bool:
        notified.append((seat, text))
        return True

    out = duplex.duplex_from_output(
        state_dir=state,
        seat="floor",
        record=_record("task-skip-1", "donald"),
        output_text=RESULT_LINE,
        send_fn=fake_send,
    )
    assert out.get("ok") is True
    assert out.get("caller") == "donald"
    assert out.get("notified") is True
    assert out.get("notify_seat") == "floor-ops"
    assert out.get("notify_skipped") in (None, "")
    assert notified and notified[0][0] == "floor-ops"
    assert "donald" not in {s for s, _ in notified}
    assert "A2A_REPLY" in notified[0][1]
    assert RESULT_LINE in notified[0][1]
    tasks = json.loads((state / "floor" / "tasks.json").read_text(encoding="utf-8"))
    blob = json.dumps(tasks)
    assert "director-result" in blob
    assert RESULT_LINE in blob
    assert (state / "floor" / "runs" / "task-skip-1.duplex").is_file()


def test_duplex_skips_notify_without_failing_when_no_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplex = _load(DUPLEX_PY, "gcs_duplex_skip_nocard")
    empty = tmp_path / "empty-root"
    (empty / "docs" / "a2a" / "cards").mkdir(parents=True)
    monkeypatch.setattr(duplex, "ROOT", empty)
    state = tmp_path / "a2a-state"
    notified: list[tuple[str, str]] = []

    def fake_send(seat: str, text: str) -> bool:
        notified.append((seat, text))
        raise AssertionError(f"must not send to {seat}")

    out = duplex.duplex_from_output(
        state_dir=state,
        seat="cloud",
        record=_record("task-skip-2", "donald"),
        output_text=RESULT_LINE,
        send_fn=fake_send,
        root=empty,
    )
    assert out.get("ok") is True
    assert out.get("notified") is False
    assert out.get("notify_skipped") == "skipSeat"
    assert not notified
    tasks = json.loads((state / "cloud" / "tasks.json").read_text(encoding="utf-8"))
    assert RESULT_LINE in json.dumps(tasks)
    assert "director-result" in json.dumps(tasks)
    assert (state / "cloud" / "runs" / "task-skip-2.duplex").is_file()


def test_unknown_caller_without_card_is_no_card_not_skipseat(tmp_path: Path) -> None:
    duplex = _load(DUPLEX_PY, "gcs_duplex_skip_unknown")
    empty = tmp_path / "empty"
    (empty / "docs" / "a2a" / "cards").mkdir(parents=True)
    state = tmp_path / "a2a-state"
    notified: list[tuple[str, str]] = []

    def fake_send(seat: str, text: str) -> bool:
        notified.append((seat, text))
        raise AssertionError(f"must not send to {seat}")

    out = duplex.duplex_from_output(
        state_dir=state,
        seat="art",
        record=_record("task-skip-unknown", "no-such-seat"),
        output_text=RESULT_LINE,
        send_fn=fake_send,
        root=empty,
    )
    assert out.get("ok") is True
    assert out.get("notified") is False
    assert out.get("notify_skipped") == "no-card"
    assert not notified
    tasks = json.loads((state / "art" / "tasks.json").read_text(encoding="utf-8"))
    assert RESULT_LINE in json.dumps(tasks)


def test_duplex_send_fail_does_not_fail_task_reply(tmp_path: Path) -> None:
    duplex = _load(DUPLEX_PY, "gcs_duplex_skip_sendfail")
    state = tmp_path / "a2a-state"
    notified: list[tuple[str, str]] = []

    def fake_send(seat: str, text: str) -> bool:
        notified.append((seat, text))
        return False

    out = duplex.duplex_from_output(
        state_dir=state,
        seat="systems",
        record=_record("task-skip-3", "donald"),
        output_text=RESULT_LINE,
        send_fn=fake_send,
    )
    assert out.get("ok") is True
    assert out.get("notified") is False
    assert out.get("notify_skipped") == "send-fail"
    assert notified and notified[0][0] != "donald"
    tasks = json.loads((state / "systems" / "tasks.json").read_text(encoding="utf-8"))
    assert RESULT_LINE in json.dumps(tasks)
    assert "director-result" in json.dumps(tasks)


def test_hub_donald_404s_but_duplex_notify_uses_floor_ops(
    hub: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hub has no donald card (404). Duplex A2A_REPLY must land on floor-ops."""
    env = hub["env"]
    proc = subprocess.run(
        ["bash", str(SEND_SH), "--from", "duplex", "donald", "should-404"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode != 0
    assert "404" in proc.stderr or "unknown seat" in proc.stderr
    assert "A2A_SEND_OK" not in proc.stdout

    duplex = _load(DUPLEX_PY, "gcs_duplex_skip_hub")
    monkeypatch.setenv("GCS_A2A_HUB", hub["url"])
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(hub["state"]))
    monkeypatch.setattr(duplex, "ROOT", REPO)
    monkeypatch.setattr(duplex, "HUB", hub["url"])
    monkeypatch.setattr(duplex, "STATE_DIR", Path(hub["state"]))

    out = duplex.duplex_from_output(
        state_dir=Path(hub["state"]),
        seat="floor",
        record=_record("task-skip-hub", "donald"),
        output_text=RESULT_LINE,
    )
    assert out.get("ok") is True
    assert out.get("notified") is True
    assert out.get("caller") == "donald"
    assert out.get("notify_seat") == "floor-ops"
    floor_ops_inbox = Path(hub["state"]) / "floor-ops" / "inbox.jsonl"
    donald_inbox = Path(hub["state"]) / "donald" / "inbox.jsonl"
    assert floor_ops_inbox.is_file()
    rec = json.loads(floor_ops_inbox.read_text(encoding="utf-8").splitlines()[-1])
    text = rec["parts"][0]["text"]
    assert "A2A_REPLY" in text
    assert RESULT_LINE in text
    assert not donald_inbox.exists()
    tasks = json.loads(
        (Path(hub["state"]) / "floor" / "tasks.json").read_text(encoding="utf-8")
    )
    task = tasks["task-skip-hub"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert "director-result" in json.dumps(task)


def test_hub_enqueue_is_submitted_receipt_not_director_result(hub: dict) -> None:
    """LIV-85 enqueue ACK is SUBMITTED. Not this FAT's RESULT line. Do not clone."""
    proc = subprocess.run(
        ["bash", str(SEND_SH), "floor-ops", "ping receipt only"],
        cwd=str(REPO),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "A2A_SEND_OK" in proc.stdout
    assert "TASK_STATE_SUBMITTED" in proc.stdout
    assert "TASK_STATE_COMPLETED" not in proc.stdout
    duplex = _load(DUPLEX_PY, "gcs_duplex_skip_receipt")
    assert duplex.extract_result_line("TASK_STATE_COMPLETED") is None
    assert duplex.extract_result_line("TASK_STATE_SUBMITTED") is None
    assert duplex.extract_result_line("A2A_SEND_OK") is None
    assert duplex.extract_result_line("ACK seat=floor-ops messageId=m1") is None
    assert duplex.extract_result_line("QUEUED seat=floor-ops messageId=m1") is None
    inbox = Path(hub["state"]) / "floor-ops" / "inbox.jsonl"
    rec = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["parts"][0]["text"] == "ping receipt only"


def test_donald_orchestrator_remain_skip_seats_not_launchable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GCS_ACP_SEATS", raising=False)
    monkeypatch.delenv("GCS_SKIP_SEATS", raising=False)
    skipped = subprocess.check_output(
        ["python3", str(LIB_PY), "skip-seats"], cwd=str(REPO), text=True
    )
    launch = subprocess.check_output(
        ["python3", str(LIB_PY), "launch-seats"], cwd=str(REPO), text=True
    )
    skip_names = skipped.strip().splitlines()
    launch_names = launch.strip().splitlines()
    assert "donald" in skip_names
    assert "orchestrator" in skip_names
    assert "donald" not in launch_names
    assert "orchestrator" not in launch_names
    assert "floor-ops" in launch_names
    dispatch = _load(DISPATCH_PY, "gcs_dispatch_skip_reply")
    reply = f"A2A_REPLY seat=floor task=task-skip-1 context=ctx-1 {RESULT_LINE}"
    assert "A2A_REPLY" in dispatch._INJECT_ONLY_KINDS
    assert dispatch._is_cloud_launch_message(reply) is False
