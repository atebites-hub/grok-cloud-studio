#!/usr/bin/env python3
"""Signed Cursor Cloud webhook receiver for Grok Cloud Studio.

HMAC-SHA256 over the raw request body. Header:

  X-Webhook-Signature: sha256=<hex>

Secret from GCS_WEBHOOK_SECRET (never logged). On a terminal Extra High
status, look up the bc-id in the fleet ledger, A2A-ping the owning seat,
and mark notified_by=webhook. The waiter remains the fallback when this
receiver is not running.

Stdlib only. Local studio bind (default 127.0.0.1:8788).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_CLOUD = Path(__file__).resolve().parent
if str(_CLOUD) not in sys.path:
    sys.path.insert(0, str(_CLOUD))
from fleet_ledger import find_by_bc, normalize_run_status, notify_owner  # noqa: E402

HOST = os.environ.get("GCS_WEBHOOK_HOST", "127.0.0.1")
PORT = int(os.environ.get("GCS_WEBHOOK_PORT", "8788"))
TERMINAL = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED"})


def webhook_secret() -> bytes:
    raw = (os.environ.get("GCS_WEBHOOK_SECRET") or os.environ.get("CLOUD_WEBHOOK_SECRET") or "").strip()
    if not raw:
        raise RuntimeError("GCS_WEBHOOK_SECRET is required")
    return raw.encode("utf-8")


def parse_signature_header(header: str) -> str:
    value = (header or "").strip()
    if value.lower().startswith("sha256="):
        return value.split("=", 1)[1].strip()
    return value


def verify_signature(secret: bytes, body: bytes, header: str) -> bool:
    got = parse_signature_header(header)
    if not got:
        return False
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if len(got) != len(expected):
        return False
    return hmac.compare_digest(got, expected)


def extract_bc_id(payload: dict[str, Any]) -> str:
    for key in ("id", "agentId", "bcId", "bc_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    agent = payload.get("agent")
    if isinstance(agent, dict):
        for key in ("id", "agentId"):
            value = agent.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        nested = extract_bc_id(data)
        if nested:
            return nested
    return ""


def extract_status(payload: dict[str, Any]) -> str:
    for key in ("runStatus", "status"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_run_status(value)
    run = payload.get("run")
    if isinstance(run, dict):
        value = run.get("status") or run.get("runStatus")
        if isinstance(value, str) and value.strip():
            return normalize_run_status(value)
    return ""


def normalize_payload(payload: dict[str, Any], bc_id: str) -> dict[str, Any]:
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    git = run.get("git") if isinstance(run, dict) else payload.get("git")
    pr = payload.get("prUrl") or payload.get("pr_url")
    if not pr and isinstance(git, dict):
        for branch in git.get("branches") or []:
            if isinstance(branch, dict) and branch.get("prUrl"):
                pr = branch["prUrl"]
                break
    status = extract_status(payload)
    return {
        "agentId": bc_id,
        "name": payload.get("name") or "",
        "url": payload.get("url") or f"https://cursor.com/agents/{bc_id}",
        "runStatus": status,
        "status": status,
        "prUrl": pr,
        "result": payload.get("result"),
    }


class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "GrokCloudStudioWebhook/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[webhook] {self.address_string()} {fmt % args}")

    def _json(self, code: int, body: dict[str, Any]) -> None:
        blob = json.dumps(body).encode("utf-8") + b"\n"
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/health", "/"):
            self._json(200, {"ok": True, "service": "gcs-webhook"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in ("/webhooks/cursor-cloud", "/v0/statusChange", "/webhook"):
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length) if length else b""
        header = (
            self.headers.get("X-Webhook-Signature")
            or self.headers.get("X-Hub-Signature-256")
            or ""
        )
        try:
            secret = webhook_secret()
        except RuntimeError as exc:
            self._json(500, {"error": str(exc)})
            return
        if not verify_signature(secret, body, header):
            self._json(401, {"error": "invalid signature"})
            return
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            self._json(400, {"error": f"invalid json: {exc}"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "json object required"})
            return
        bc_id = extract_bc_id(payload)
        if not bc_id:
            self._json(400, {"error": "missing agent id"})
            return
        status = extract_status(payload)
        if status not in TERMINAL:
            self._json(202, {"ok": True, "ignored": True, "id": bc_id, "status": status or "unknown"})
            return
        hit = find_by_bc(bc_id)
        seat = hit[0] if hit else os.environ.get("GCS_DIRECTOR_SEAT", "ops")
        normalized = normalize_payload(payload, bc_id)
        try:
            row = notify_owner(bc_id, normalized, notified_by="webhook", seat=seat)
        except RuntimeError as exc:
            self._json(502, {"error": str(exc), "id": bc_id})
            return
        self._json(
            200,
            {
                "ok": True,
                "id": bc_id,
                "seat": seat,
                "notified_by": "webhook",
                "status": status,
                "ledger": {"status": row.get("status"), "notified": row.get("notified")},
            },
        )


def main() -> int:
    try:
        webhook_secret()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    httpd = ThreadingHTTPServer((HOST, PORT), WebhookHandler)
    print(f"gcs-webhook listening on http://{HOST}:{PORT}")
    print("POST /webhooks/cursor-cloud  POST /v0/statusChange  GET /health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
