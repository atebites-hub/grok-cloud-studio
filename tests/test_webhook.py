"""Webhook HMAC accept/reject."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
from webhook_receiver import verify_signature  # noqa: E402

SECRET = b"unit-test-webhook"


def test_verify_signature_accepts_matching_hex() -> None:
    body = b'{"id":"bc-1","status":"FINISHED"}'
    sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    assert verify_signature(SECRET, body, f"sha256={sig}") is True


def test_verify_signature_rejects_mismatch() -> None:
    body = b'{"id":"bc-1","status":"FINISHED"}'
    assert verify_signature(SECRET, body, "sha256=" + ("ab" * 32)) is False
    assert verify_signature(SECRET, body, "") is False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def receiver(tmp_path: Path):
    port = _free_port()
    env = {
        **os.environ,
        "GCS_ROOT": str(ROOT),
        "GCS_A2A_STATE": str(tmp_path / "state"),
        "GCS_WEBHOOK_HOST": "127.0.0.1",
        "GCS_WEBHOOK_PORT": str(port),
        "GCS_WEBHOOK_SECRET": SECRET.decode("ascii"),
        "GCS_DIRECTOR_SEAT": "ops",
    }
    proc = subprocess.Popen(
        ["python3", str(ROOT / "scripts" / "cloud" / "webhook_receiver.py")],
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
                    yield {"url": url, "env": env}
                    proc.terminate()
                    proc.wait(timeout=3)
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.05)
    proc.kill()
    raise RuntimeError("webhook receiver did not start")


def _post(url: str, body: bytes, header: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        url + "/webhooks/cursor-cloud",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Webhook-Signature": header},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload


def test_receiver_rejects_bad_signature(receiver: dict) -> None:
    body = b'{"id":"bc-x","status":"FINISHED"}'
    code, payload = _post(receiver["url"], body, "sha256=" + ("00" * 32))
    assert code == 401
    assert payload["error"] == "invalid signature"


def test_receiver_accepts_signed_nonterminal(receiver: dict) -> None:
    body = json.dumps({"id": "bc-running", "status": "RUNNING"}).encode("utf-8")
    sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    code, payload = _post(receiver["url"], body, f"sha256={sig}")
    assert code == 202
    assert payload["ignored"] is True
