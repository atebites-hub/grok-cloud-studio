"""Cloud auth path: never print CURSOR_API_KEY; redact agent.env dumps.

Does not remint doctor #51. Does not spawn Extra High or Bot CloudAgent.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
COMMON = CLOUD / "_common.sh"
AUTH = CLOUD / "auth.sh"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
LIST = CLOUD / "list.sh"
DOCTOR = REPO / "doctor.sh"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"

FAKE_KEY = "test-cursor-api-key-agent-env-dump-not-leaked"
BOT_CLOUDAGENT = "Bot" + " CloudAgent"
EXAMPLE_REPO = "https://github.com/example/control-plane"


def _base_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    drop = {
        "CURSOR_API_KEY",
        "CURSOR_AGENT_ENV",
        "GCS_CLOUD_REPO",
        "CLOUD_REPO_URL",
        "CURSOR_CLOUD_REPO",
    }
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(
        {
            "HOME": str(home),
            "TMPDIR": str(tmp_path / "tmp"),
            "GCS_ROOT": str(REPO),
            "LC_ALL": "C",
            "TERM": "dumb",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GCS_SPAWN_WAITER": "0",
            "CLOUD_SPAWN_WAITER": "0",
        }
    )
    (tmp_path / "tmp").mkdir(parents=True, exist_ok=True)
    env.update(extra)
    return env


def _write_agent_env(path: Path, key: str = FAKE_KEY) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"export CURSOR_API_KEY={key}\n", encoding="utf-8")
    return path


def _assert_key_absent(blob: str) -> None:
    assert FAKE_KEY not in blob
    assert f"CURSOR_API_KEY={FAKE_KEY}" not in blob


def _run_bash(
    script: str,
    env: dict[str, str],
    *,
    stdin: str | None = None,
    xtrace: bool = False,
    timeout: int = 20,
) -> subprocess.CompletedProcess[str]:
    argv = ["bash"]
    if xtrace:
        argv.append("-x")
    argv.extend(["-c", script])
    return subprocess.run(
        argv,
        cwd=str(REPO),
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_auth_path_files_exist() -> None:
    assert COMMON.is_file()
    assert AUTH.is_file()
    assert LAUNCH.is_file()
    assert LIST.is_file()


def test_auth_and_common_never_echo_key_or_bot_cloudagent() -> None:
    blob = COMMON.read_text(encoding="utf-8") + "\n" + AUTH.read_text(encoding="utf-8")
    assert "cloud_load_auth" in blob
    assert "cloud_redact_stream" in blob
    assert "echo \"$CURSOR_API_KEY\"" not in blob
    assert "echo $CURSOR_API_KEY" not in blob
    for line in blob.splitlines():
        if "CURSOR_API_KEY=" not in line:
            continue
        assert "<redacted>" in line or "[redacted]" in line, line
    assert BOT_CLOUDAGENT not in blob
    assert "set +x" in AUTH.read_text(encoding="utf-8")
    doctor = DOCTOR.read_text(encoding="utf-8")
    assert "WARN CURSOR_API_KEY" in doctor
    assert "bad \"CURSOR_API_KEY" not in doctor
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast" in launch and "false" in launch


def test_cloud_redact_stream_redacts_agent_env_dump_without_env_key(
    tmp_path: Path,
) -> None:
    dump = f"export CURSOR_API_KEY={FAKE_KEY}\n# ~/.config/cursor/agent.env\n"
    env = _base_env(tmp_path)
    proc = _run_bash(
        f'source "{COMMON}" && cloud_redact_stream',
        env,
        stdin=dump,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    _assert_key_absent(blob)
    assert "CURSOR_API_KEY=<redacted>" in proc.stdout or "CURSOR_API_KEY=[redacted]" in proc.stdout
    assert "agent.env" in proc.stdout


def test_cloud_load_auth_xtrace_from_agent_env_does_not_print_key(
    tmp_path: Path,
) -> None:
    env = _base_env(tmp_path)
    _write_agent_env(Path(env["HOME"]) / ".config" / "cursor" / "agent.env")
    proc = _run_bash(
        f'source "{COMMON}" && cloud_load_auth && printf "AUTH_OK\\n"',
        env,
        xtrace=True,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "AUTH_OK" in proc.stdout
    _assert_key_absent(blob)


def test_cloud_load_auth_xtrace_cursor_agent_env_override_does_not_print_key(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "cursor-agent.env"
    _write_agent_env(env_file)
    env = _base_env(tmp_path, CURSOR_AGENT_ENV=str(env_file))
    proc = _run_bash(
        f'source "{COMMON}" && cloud_load_auth && printf "AUTH_OK\\n"',
        env,
        xtrace=True,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "AUTH_OK" in proc.stdout
    _assert_key_absent(blob)


def test_list_from_agent_env_xtrace_does_not_print_key(tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            if parts == ["v1", "agents"]:
                payload = json.dumps(
                    {
                        "items": [
                            {
                                "id": "bc-1",
                                "status": "ACTIVE",
                                "name": "one",
                                "url": "https://cursor.com/agents/bc-1",
                                "latestRunId": "run-1",
                            }
                        ]
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        env = _base_env(tmp_path, CURSOR_API_BASE=base, GCS_CLOUD_REPO=EXAMPLE_REPO)
        _write_agent_env(Path(env["HOME"]) / ".config" / "cursor" / "agent.env")
        proc = subprocess.run(
            ["bash", "-x", str(LIST)],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "bc-1" in proc.stdout
    _assert_key_absent(blob)
    assert BOT_CLOUDAGENT not in blob
    assert "CLOUD_LAUNCH_OK" not in blob


def test_http_error_body_redacts_agent_env_dump(tmp_path: Path) -> None:
    dump = f"export CURSOR_API_KEY={FAKE_KEY}\n"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            body = dump.encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        env = _base_env(tmp_path, CURSOR_API_BASE=base)
        _write_agent_env(Path(env["HOME"]) / ".config" / "cursor" / "agent.env")
        proc = subprocess.run(
            ["bash", str(LIST)],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    _assert_key_absent(blob)
    assert "CURSOR_API_KEY=<redacted>" in blob or "CURSOR_API_KEY=[redacted]" in blob


def test_docs_cover_auth_redact_not_doctor_remint() -> None:
    readme = CLOUD_README.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    blob = f"{readme}\n{cloud}"
    assert "never print" in blob.lower()
    assert "agent.env" in blob
    assert "redact" in blob.lower()
    assert "dump" in blob.lower()
    assert "bash -x" in blob.lower()
    assert "grok-4.6" in blob
    assert "xhigh" in blob
    assert "fast=false" in blob or "fast" in blob
    assert "Bot CloudAgent" in cloud
    doctor = DOCTOR.read_text(encoding="utf-8")
    assert "WARN GCS_CLOUD_REPO" in doctor or "WARN GCS_CLOUD_REPO unset" in doctor
    assert "WARN CURSOR_API_KEY" in doctor
