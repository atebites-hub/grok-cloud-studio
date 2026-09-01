"""A2A hub send/ack + registry seats."""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "scripts" / "a2a" / "hub.py"
LIB = ROOT / "scripts" / "a2a" / "lib.py"
SEND = ROOT / "scripts" / "a2a" / "send.sh"


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
        "GCS_ROOT": str(ROOT),
        "GCS_A2A_HOST": "127.0.0.1",
        "GCS_A2A_PORT": str(port),
        "GCS_A2A_STATE": str(state),
        "GCS_A2A_HUB": f"http://127.0.0.1:{port}",
    }
    proc = subprocess.Popen(
        ["python3", str(HUB)],
        cwd=str(ROOT),
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


def test_registry_example_seats() -> None:
    seats = subprocess.check_output(["python3", str(LIB), "launch-seats"], cwd=str(ROOT), text=True)
    names = seats.strip().splitlines()
    for seat in (
        "floor",
        "ops",
        "cloud",
        "floor-ops",
        "studio-ops",
        "art",
        "content",
        "systems",
        "qa-a",
        "qa-b",
        "audio",
        "narrative",
    ):
        assert seat in names
    assert "orchestrator" not in names
    assert "donald" not in names


def test_hub_health_and_send_ack(hub: dict) -> None:
    with urllib.request.urlopen(f"{hub['url']}/health", timeout=2) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    assert body["ok"] is True
    assert body["service"] == "gcs-a2a-hub"

    proc = subprocess.run(
        ["bash", str(SEND), "floor", "ping from test"],
        cwd=str(ROOT),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "A2A_SEND_OK" in proc.stdout
    inbox = Path(hub["state"]) / "floor" / "inbox.jsonl"
    assert inbox.is_file()
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert record["parts"][0]["text"] == "ping from test"


def test_hub_send_from_seat(hub: dict) -> None:
    proc = subprocess.run(
        ["bash", str(SEND), "--from", "ops", "floor", "ack via from"],
        cwd=str(ROOT),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    inbox = Path(hub["state"]) / "floor" / "inbox.jsonl"
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert record["parts"][0]["text"] == "ack via from"
    data_parts = [p for p in record["parts"] if p.get("kind") == "data" or "data" in p]
    assert data_parts
    assert data_parts[0]["data"]["from"] == "ops"
    assert record.get("from") == "ops"


def _send(hub: dict, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SEND), *args],
        cwd=str(ROOT),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )


def _task_id_from_send(stdout: str, inbox: Path) -> str:
    for line in stdout.splitlines():
        if line.startswith("A2A_SEND_OK") and "task=" in line:
            for part in line.split():
                if part.startswith("task="):
                    tid = part.split("=", 1)[1].strip()
                    if tid:
                        return tid
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    return str(record["taskId"])


def _get_task(hub: dict, seat: str, task_id: str) -> dict:
    with urllib.request.urlopen(
        f"{hub['url']}/a2a/{seat}/tasks/{task_id}", timeout=2
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_hub_send_stays_submitted_until_mind_not_completed_ack(hub: dict) -> None:
    """Enqueue is not done. send.sh + hub must not fake COMPLETED or HANDOFF."""
    proc = _send(hub, "floor", "queued until mind harvests")
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "A2A_SEND_OK" in proc.stdout
    assert "TASK_STATE_SUBMITTED" in proc.stdout
    assert "TASK_STATE_COMPLETED" not in blob
    assert "HANDOFF" not in blob
    assert "ACP_INJECT_HANDOFF" not in blob

    inbox = Path(hub["state"]) / "floor" / "inbox.jsonl"
    assert inbox.is_file()
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert record["parts"][0]["text"] == "queued until mind harvests"
    task_id = _task_id_from_send(proc.stdout, inbox)
    task = _get_task(hub, "floor", task_id)
    assert (task.get("status") or {}).get("state") == "TASK_STATE_SUBMITTED"
    tasks_path = Path(hub["state"]) / "floor" / "tasks.json"
    on_disk = json.loads(tasks_path.read_text(encoding="utf-8"))
    assert on_disk[task_id]["status"]["state"] == "TASK_STATE_SUBMITTED"


def test_mind_harvest_finish_marks_hub_task_completed(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """COMPLETED only after Grok Build mind harvests and the runner exits 0."""
    proc = _send(hub, "floor", "mind must harvest this")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    inbox = Path(hub["state"]) / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_SUBMITTED"

    grok_log = tmp_path / "grok.argv.json"
    grok = tmp_path / "fake-bin" / "grok"
    grok.parent.mkdir(parents=True, exist_ok=True)
    grok.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(grok_log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:]})\n"
        "log.write_text(json.dumps(rows))\n"
        "sys.stdout.write(json.dumps({'ok': True}))\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    grok.chmod(grok.stat().st_mode | stat.S_IEXEC)

    mind_py = ROOT / "scripts" / "directors" / "mind.py"
    spec = importlib.util.spec_from_file_location("gcs_mind_hub_complete", mind_py)
    assert spec is not None and spec.loader is not None
    mind = importlib.util.module_from_spec(spec)
    sys.modules["gcs_mind_hub_complete"] = mind
    spec.loader.exec_module(mind)
    monkeypatch.setattr(mind, "STATE_DIR", Path(hub["state"]))
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(hub["state"]))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)

    result = mind.process_once("floor")
    assert result.get("consumed") == 1, result
    assert result.get("reason") == "ok"
    assert result.get("task_id") == task_id
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    on_disk = json.loads(
        (Path(hub["state"]) / "floor" / "tasks.json").read_text(encoding="utf-8")
    )
    assert on_disk[task_id]["status"]["state"] == "TASK_STATE_COMPLETED"
    src = mind_py.read_text(encoding="utf-8")
    assert "ACP_INJECT_HANDOFF" not in src
    assert "HANDOFF" not in src


def test_mind_runner_fail_leaves_hub_task_queued(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _send(hub, "floor", "keep queued on fail")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    inbox = Path(hub["state"]) / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)

    grok = tmp_path / "fake-bin" / "grok-fail"
    grok.parent.mkdir(parents=True, exist_ok=True)
    grok.write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.stderr.write('boom\\n')\nraise SystemExit(1)\n",
        encoding="utf-8",
    )
    grok.chmod(grok.stat().st_mode | stat.S_IEXEC)

    mind_py = ROOT / "scripts" / "directors" / "mind.py"
    spec = importlib.util.spec_from_file_location("gcs_mind_hub_fail", mind_py)
    assert spec is not None and spec.loader is not None
    mind = importlib.util.module_from_spec(spec)
    sys.modules["gcs_mind_hub_fail"] = mind
    spec.loader.exec_module(mind)
    monkeypatch.setattr(mind, "STATE_DIR", Path(hub["state"]))
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(hub["state"]))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.setenv("GCS_MIND_RUNNER", "grok")

    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "runner-fail"
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_SUBMITTED"
    offset_path = Path(hub["state"]) / "floor" / "mind" / "offset"
    if offset_path.is_file():
        assert int(offset_path.read_text(encoding="utf-8").strip() or "0") == 0
