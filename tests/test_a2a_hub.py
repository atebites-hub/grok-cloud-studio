"""A2A hub send/ack + registry seats."""
from __future__ import annotations

import json
import os
import socket
import subprocess
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


def test_hub_send_canonicalizes_producer_and_accepts_audio(hub: dict) -> None:
    """CCGS aliases and first-class audio stay hive-real on leftover send."""
    producer = subprocess.run(
        ["bash", str(SEND), "producer", "unstick floor-ops via CCGS alias"],
        cwd=str(ROOT),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert producer.returncode == 0, producer.stdout + producer.stderr
    assert "A2A_SEND_OK" in producer.stdout
    inbox = Path(hub["state"]) / "floor-ops" / "inbox.jsonl"
    assert inbox.is_file()
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert record["parts"][0]["text"] == "unstick floor-ops via CCGS alias"
    assert not (Path(hub["state"]) / "producer" / "inbox.jsonl").exists()

    audio = subprocess.run(
        ["bash", str(SEND), "audio", "mix pass via first-class seat"],
        cwd=str(ROOT),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert audio.returncode == 0, audio.stdout + audio.stderr
    audio_inbox = Path(hub["state"]) / "audio" / "inbox.jsonl"
    assert audio_inbox.is_file()
    arec = json.loads(audio_inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert arec["parts"][0]["text"] == "mix pass via first-class seat"
