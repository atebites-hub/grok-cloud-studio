"""Cursor Cloud statusChange webhook: FLEET_DONE without get_agent_run polling.

Official payload: https://cursor.com/docs/cloud-agent/api/webhooks
HMAC X-Webhook-Signature sha256=<hex>. Waiter 429 (#35) and fleet notify
dedupe (#34) are out of scope. Never Bot CloudAgent.
"""
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
from fleet_ledger import load_entries, register  # noqa: E402
from webhook_receiver import (  # noqa: E402
    extract_bc_id,
    extract_status,
    normalize_payload,
    verify_signature,
)

SECRET = b"unit-test-webhook"
PR_URL = "https://github.com/atebites-hub/grok-cloud-studio/pull/99"
HUB = ROOT / "scripts" / "a2a" / "hub.py"


def official_status_change(
    *,
    agent_id: str = "bc-hook-1",
    status: str = "FINISHED",
    pr_url: str | None = PR_URL,
) -> dict:
    target: dict = {
        "url": f"https://cursor.com/agents?id={agent_id}",
        "branchName": "cursor/liv-41-hook",
    }
    if pr_url:
        target["prUrl"] = pr_url
    return {
        "event": "statusChange",
        "timestamp": "2024-01-15T10:30:00Z",
        "id": agent_id,
        "status": status,
        "source": {
            "repository": "https://github.com/atebites-hub/grok-cloud-studio",
            "ref": "main",
        },
        "target": target,
        "summary": "Opened a PR",
    }


def test_verify_signature_accepts_matching_hex() -> None:
    body = b'{"id":"bc-1","status":"FINISHED"}'
    sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    assert verify_signature(SECRET, body, f"sha256={sig}") is True


def test_verify_signature_rejects_mismatch() -> None:
    body = b'{"id":"bc-1","status":"FINISHED"}'
    assert verify_signature(SECRET, body, "sha256=" + ("ab" * 32)) is False
    assert verify_signature(SECRET, body, "") is False


def test_normalize_official_status_change_uses_target_pr() -> None:
    """Cursor docs put prUrl and agent url under target, not top-level prUrl."""
    payload = official_status_change()
    assert extract_bc_id(payload) == "bc-hook-1"
    assert extract_status(payload) == "FINISHED"
    norm = normalize_payload(payload, "bc-hook-1")
    assert norm["prUrl"] == PR_URL
    assert "bc-hook-1" in str(norm["url"])
    assert norm["runStatus"] == "FINISHED"
    assert norm["status"] == "FINISHED"
    assert "Opened a PR" in str(norm.get("result") or "")


def test_webhook_receiver_does_not_poll_get_agent_run() -> None:
    src = (ROOT / "scripts" / "cloud" / "webhook_receiver.py").read_text(encoding="utf-8")
    assert "/v1/agents" not in src
    assert "getRun" not in src
    assert "listRuns" not in src
    assert "Bot CloudAgent" not in src
    assert "Grok Bot CloudAgent" not in src


def test_studio_bus_optionally_starts_webhook_receiver() -> None:
    src = (ROOT / "scripts" / "a2a" / "start-studio-bus.sh").read_text(encoding="utf-8")
    assert "GCS_WEBHOOK_SECRET" in src
    assert "webhook_receiver.py" in src
    assert "STUDIO_BUS_WEBHOOK" in src


def test_docs_describe_optional_status_change_hook() -> None:
    cloud_readme = (ROOT / "scripts" / "cloud" / "README.md").read_text(encoding="utf-8")
    docs_cloud = (ROOT / "docs" / "CLOUD.md").read_text(encoding="utf-8")
    blob = cloud_readme + "\n" + docs_cloud
    assert "statusChange" in blob
    assert "X-Webhook-Signature" in blob
    assert "get_agent_run" in blob
    assert "GCS_WEBHOOK_SECRET" in blob
    assert "Bot CloudAgent" not in blob


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(url: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=0.3) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.05)
    raise RuntimeError(f"health check failed for {url}")


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
    try:
        _wait_health(url)
        yield {"url": url, "env": env, "state": tmp_path / "state"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def hub_and_receiver(tmp_path: Path):
    """Hub + signed receiver sharing GCS_A2A_STATE so FLEET_DONE lands in inbox."""
    hub_port = _free_port()
    hook_port = _free_port()
    state = tmp_path / "a2a-state"
    env = {
        **os.environ,
        "GCS_ROOT": str(ROOT),
        "GCS_A2A_STATE": str(state),
        "GCS_A2A_HOST": "127.0.0.1",
        "GCS_A2A_PORT": str(hub_port),
        "GCS_A2A_HUB": f"http://127.0.0.1:{hub_port}",
        "GCS_WEBHOOK_HOST": "127.0.0.1",
        "GCS_WEBHOOK_PORT": str(hook_port),
        "GCS_WEBHOOK_SECRET": SECRET.decode("ascii"),
        "GCS_DIRECTOR_SEAT": "ops",
        "CLOUD_OWNER_SEAT": "ops",
    }
    hub_proc = subprocess.Popen(
        ["python3", str(HUB)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    hook_proc = subprocess.Popen(
        ["python3", str(ROOT / "scripts" / "cloud" / "webhook_receiver.py")],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    hub_url = f"http://127.0.0.1:{hub_port}"
    hook_url = f"http://127.0.0.1:{hook_port}"
    try:
        _wait_health(hub_url)
        _wait_health(hook_url)
        yield {"hub": hub_url, "url": hook_url, "env": env, "state": state}
    finally:
        for proc in (hook_proc, hub_proc):
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def _post(url: str, body: bytes, header: str, path: str = "/webhooks/cursor-cloud") -> tuple[int, dict]:
    req = urllib.request.Request(
        url + path,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": header,
            "X-Webhook-Event": "statusChange",
            "User-Agent": "Cursor-Agent-Webhook/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw}
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


def test_official_finished_pings_fleet_done_without_get_agent_run(hub_and_receiver: dict) -> None:
    """statusChange FINISHED A2A-pings FLEET_DONE/PR_READY; no Cursor run poll."""
    env = hub_and_receiver["env"]
    os.environ["GCS_ROOT"] = env["GCS_ROOT"]
    os.environ["GCS_A2A_STATE"] = env["GCS_A2A_STATE"]
    os.environ["GCS_DIRECTOR_SEAT"] = "ops"
    register("bc-hook-1", seat="ops", run_id="run-1", name="liv-41-hook")
    payload = official_status_change()
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    code, reply = _post(hub_and_receiver["url"], body, f"sha256={sig}")
    assert code == 200, reply
    assert reply.get("notified_by") == "webhook"
    assert reply.get("ok") is True
    inbox = Path(env["GCS_A2A_STATE"]) / "ops" / "inbox.jsonl"
    assert inbox.is_file(), "FLEET_DONE must land on the owning seat inbox"
    text = inbox.read_text(encoding="utf-8")
    assert "FLEET_DONE" in text
    assert "PR_READY" in text
    assert "bc-hook-1" in text
    assert PR_URL in text
    rows = load_entries(Path(env["GCS_A2A_STATE"]) / "ops" / "fleet.jsonl")
    row = next(r for r in rows if r.get("bc_id") == "bc-hook-1")
    assert row["notified_by"] == "webhook"
    assert row["notified"] is True
    assert row["status"] == "closed"


def test_official_error_on_v0_status_change_path(hub_and_receiver: dict) -> None:
    env = hub_and_receiver["env"]
    os.environ["GCS_ROOT"] = env["GCS_ROOT"]
    os.environ["GCS_A2A_STATE"] = env["GCS_A2A_STATE"]
    os.environ["GCS_DIRECTOR_SEAT"] = "ops"
    register("bc-hook-err", seat="ops", name="liv-41-err")
    payload = official_status_change(agent_id="bc-hook-err", status="ERROR", pr_url=None)
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    code, reply = _post(
        hub_and_receiver["url"],
        body,
        f"sha256={sig}",
        path="/v0/statusChange",
    )
    assert code == 200, reply
    inbox = Path(env["GCS_A2A_STATE"]) / "ops" / "inbox.jsonl"
    text = inbox.read_text(encoding="utf-8")
    assert "FLEET_DONE" in text
    assert "runStatus=ERROR" in text
    assert "PR_READY" not in text
    assert "bc-hook-err" in text
