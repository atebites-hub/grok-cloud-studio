"""MCP stdio tools/list."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "scripts" / "mcp" / "gcs_mcp.py"


def _rpc(plane: str, method: str, params: dict | None = None) -> dict:
    msg = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    env = {**os.environ, "GCS_ROOT": str(ROOT), "GCS_MCP_NDJSON": "1"}
    proc = subprocess.run(
        ["python3", str(MCP), "--plane", plane, "--ndjson"],
        cwd=str(ROOT),
        input=json.dumps(msg) + "\n",
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.splitlines()[0])


def test_a2a_tools_list() -> None:
    reply = _rpc("a2a", "tools/list")
    names = {t["name"] for t in reply["result"]["tools"]}
    assert names == {"a2a_list_seats", "a2a_send"}


def test_cloud_tools_list() -> None:
    reply = _rpc("cloud", "tools/list")
    names = {t["name"] for t in reply["result"]["tools"]}
    assert names == {"cloud_launch", "cloud_list", "cloud_status", "cloud_result"}


def test_a2a_list_seats_tool() -> None:
    reply = _rpc("a2a", "tools/call", {"name": "a2a_list_seats", "arguments": {}})
    text = reply["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert "floor" in payload["seats"]
    assert "ops" in payload["seats"]


def test_a2a_list_seats_keeps_audio_narrative_under_acp_cap() -> None:
    """Hive kit seats stay listable when GCS_ACP_SEATS is the serve cap."""
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "a2a_list_seats", "arguments": {}},
    }
    env = {**os.environ, "GCS_ROOT": str(ROOT), "GCS_MCP_NDJSON": "1", "GCS_ACP_SEATS": "floor,studio-ops"}
    env.pop("GCS_SKIP_SEATS", None)
    proc = subprocess.run(
        ["python3", str(MCP), "--plane", "a2a", "--ndjson"],
        cwd=str(ROOT),
        input=json.dumps(msg) + "\n",
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    reply = json.loads(proc.stdout.splitlines()[0])
    payload = json.loads(reply["result"]["content"][0]["text"])
    seats = payload["seats"]
    assert "audio" in seats
    assert "narrative" in seats
    assert "floor-ops" in seats
    assert "composer" not in seats
    assert "donald" in payload["skipSeats"]
