#!/usr/bin/env python3
"""HTTP gateway in front of `taskboard --db $DB mcp` (stdio JSON-RPC).

Binds 127.0.0.1:3011 by default. POST /mcp (also /) forwards one JSON-RPC
message to the child using MCP Content-Length framing. GET /health.
Never prints credentials. Does not vendor the taskboard binary.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


class StdioChild:
    """One long-lived stdio MCP child. Sequential RPC under a lock."""

    def __init__(self, argv: list[str]) -> None:
        self._argv = argv
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            try:
                proc.kill()
            except OSError:
                pass

    def _spawn(self) -> subprocess.Popen[bytes]:
        proc = subprocess.Popen(
            self._argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("child stdio not piped")
        return proc

    def _ensure(self) -> subprocess.Popen[bytes]:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            if proc is not None:
                try:
                    proc.wait(timeout=0.1)
                except (subprocess.TimeoutExpired, OSError):
                    pass
            proc = self._spawn()
            self._proc = proc
        return proc

    @staticmethod
    def _write(proc: subprocess.Popen[bytes], obj: dict[str, Any]) -> None:
        blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(blob)}\r\n\r\n".encode("ascii")
        assert proc.stdin is not None
        proc.stdin.write(header + blob)
        proc.stdin.flush()

    @staticmethod
    def _read(proc: subprocess.Popen[bytes]) -> dict[str, Any] | None:
        assert proc.stdout is not None
        headers: dict[str, str] = {}
        while True:
            raw = proc.stdout.readline()
            if not raw:
                return None
            if raw in (b"\r\n", b"\n"):
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                break
            if ":" not in line:
                return json.loads(line)
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length") or "0")
        body = proc.stdout.read(length) if length else b"{}"
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def rpc(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            proc = self._ensure()
            try:
                self._write(proc, msg)
            except BrokenPipeError:
                self.close()
                proc = self._ensure()
                self._write(proc, msg)
            if msg.get("id") is None:
                return None
            reply = self._read(proc)
            if reply is None:
                self.close()
                raise RuntimeError("taskboard MCP child closed stdout")
            return reply


def make_handler(child: StdioChild) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("MCP_HTTP " + (fmt % args) + "\n")

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(blob)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path in ("/health", "/"):
                self._send_json(200, {"ok": True, "service": "gcs-taskboard-mcp-http"})
                return
            self._send_json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path not in ("/", "/mcp"):
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                msg = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError as exc:
                self._send_json(400, {"ok": False, "error": f"invalid json: {exc}"})
                return
            if not isinstance(msg, dict):
                self._send_json(400, {"ok": False, "error": "json-rpc object required"})
                return
            try:
                reply = child.rpc(msg)
            except RuntimeError as exc:
                self._send_json(502, {"ok": False, "error": str(exc)})
                return
            if reply is None:
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._send_json(200, reply)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HTTP gateway for taskboard stdio MCP")
    parser.add_argument("--host", default=env_first("GCS_TASKBOARD_MCP_HOST", default="127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(env_first("GCS_TASKBOARD_MCP_PORT", default="3011")))
    parser.add_argument("--db", default=env_first("GCS_TASKBOARD_DB", "TASKBOARD_DB"))
    parser.add_argument("--bin", default=env_first("TASKBOARD_BIN", default="taskboard"))
    args = parser.parse_args(argv)
    if not args.db:
        print("error: --db or GCS_TASKBOARD_DB is required", file=sys.stderr)
        return 2
    child_argv = [args.bin, "--db", args.db, "mcp"]
    child = StdioChild(child_argv)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(child))
    print(
        f"TASKBOARD_MCP_HTTP_LISTEN host={args.host} port={args.port} db={args.db}",
        flush=True,
    )

    def _shutdown(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        child.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
