"""LIV-71 hive law: each 10-minute studio-ops beat must append a Manning apply-log.

HEALTH_OK is illegal without an APPLY line for that beat. Book titles only;
never copyrighted book text. No Palemon game code.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
APPLY_LOG = REPO / "scripts" / "studio" / "apply_log.py"
HEALTH = REPO / "health_check.sh"
WATCHDOG = REPO / "scripts" / "directors" / "watchdog-studio-ops.sh"
HIVE = REPO / "docs" / "studio" / "HIVE.md"
AGENTS = REPO / "AGENTS.md"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "studio-ops" / "SOUL.md"
PROMPT = REPO / "docs" / "studio" / "directors" / "studio_ops_director_prompt.txt"
DOCTOR = REPO / "doctor.sh"
STUDIO_ENV = REPO / "studio.env.example"

MANNING_MODELS = (
    "Grokking Simplicity",
    "Think Distributed Systems",
    "Looks Good to Me",
    "BDD in Action",
    "Acing the System Design Interview",
)

PRIVATE_GAME = "atebites-hub/" + "palemon"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_apply_log", APPLY_LOG)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(
    script: Path,
    args: list[str],
    env: dict[str, str],
    *,
    timeout: int = 20,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _py(
    args: list[str],
    env: dict[str, str],
    *,
    timeout: int = 20,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(APPLY_LOG), *args],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _base_env(tmp_path: Path, state: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    archive = tmp_path / "studio-archive"
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_STUDIO_ARCHIVE": str(archive),
        "GCS_MIND_SEATS": "",
        "GCS_BOT_BIND_OPTIONAL": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": "test-cursor-api-key-apply-log-not-leaked",
    }


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/health", "/"):
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def _serve() -> tuple[ThreadingHTTPServer, int]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, int(httpd.server_address[1])


def _live_health_env(tmp_path: Path) -> tuple[dict[str, str], list[ThreadingHTTPServer]]:
    hub, hub_port = _serve()
    ui, ui_port = _serve()
    mcp, mcp_port = _serve()
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(hub_port)
    env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
    env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
    env["PATH"] = "/usr/bin:/bin"
    return env, [hub, ui, mcp]


def test_apply_log_module_exists() -> None:
    assert APPLY_LOG.is_file(), "missing scripts/studio/apply_log.py"


def test_health_ok_rejected_without_apply_log_for_beat(tmp_path: Path) -> None:
    """Hive-law gate: live probes alone must not print HEALTH_OK."""
    env, servers = _live_health_env(tmp_path)
    try:
        proc = _run(HEALTH, [], env)
        blob = proc.stdout + proc.stderr
        assert "HEALTH_OK" not in blob, blob
        assert proc.returncode != 0, blob
        assert "APPLY_LOG" in blob, blob
        assert "test-cursor-api-key-apply-log-not-leaked" not in blob
    finally:
        for server in servers:
            server.shutdown()


def test_health_ok_requires_apply_log_line_for_current_beat(tmp_path: Path) -> None:
    env, servers = _live_health_env(tmp_path)
    try:
        append = _py(
            [
                "append",
                "--model",
                "BDD in Action",
                "--change",
                "IaC: live probes up; Palemon: no game code",
            ],
            env,
        )
        assert append.returncode == 0, append.stdout + append.stderr
        proc = _run(HEALTH, [], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "HEALTH_OK" in blob, blob
        assert "APPLY_LOG" in blob
        assert "HEALTH_DOWN" not in blob
        assert "test-cursor-api-key-apply-log-not-leaked" not in blob
    finally:
        for server in servers:
            server.shutdown()


def test_stale_apply_log_from_other_beat_does_not_unlock_health_ok(tmp_path: Path) -> None:
    env, servers = _live_health_env(tmp_path)
    try:
        mod = _load()
        interval = mod.beat_interval_sec()
        now = 1_700_000_000.0
        env["GCS_APPLY_NOW"] = str(int(now))
        stale = mod.beat_id(now - interval, interval=interval)
        append = _py(
            [
                "append",
                "--model",
                "Looks Good to Me",
                "--change",
                "IaC: previous window; Palemon: no game code",
                "--beat",
                stale,
            ],
            env,
        )
        assert append.returncode == 0, append.stdout + append.stderr
        proc = _run(HEALTH, [], env)
        blob = proc.stdout + proc.stderr
        assert "HEALTH_OK" not in blob, blob
        assert proc.returncode != 0, blob
        assert "APPLY_LOG" in blob
    finally:
        for server in servers:
            server.shutdown()


def test_append_writes_dated_studio_archive_log(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    env = _base_env(tmp_path, state)
    env["GCS_APPLY_NOW"] = "1700000000"
    proc = _py(
        [
            "append",
            "--model",
            "Grokking Simplicity",
            "--change",
            "IaC: GCS_TICKER_SEC=600; Palemon: hive-law apply-log path",
        ],
        env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "APPLY_OK" in blob or "APPLY" in blob
    archive = Path(env["GCS_STUDIO_ARCHIVE"])
    logs = list((archive / "log").glob("????-??-??.md"))
    assert len(logs) == 1, logs
    text = logs[0].read_text(encoding="utf-8")
    assert logs[0].name == f"{logs[0].stem}.md"
    assert "APPLY" in text
    assert "Grokking Simplicity" in text
    assert "IaC:" in text
    assert "Palemon:" in text
    assert "beat=" in text
    assert "seat=" in text
    low = text.lower()
    assert "copyright" not in low or "never paste" in low or "no copyrighted" in low
    assert PRIVATE_GAME not in text
    # Book titles only — no dumped chapter body.
    for line in text.splitlines():
        if "APPLY" in line:
            assert len(line) < 400


def test_append_rejects_unknown_model_and_empty_change(tmp_path: Path) -> None:
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    bad_model = _py(
        [
            "append",
            "--model",
            "Not A Manning Book",
            "--change",
            "IaC: x; Palemon: y",
        ],
        env,
    )
    bad_blob = bad_model.stdout + bad_model.stderr
    assert bad_model.returncode != 0
    assert "unknown model" in bad_blob.lower()
    assert "APPLY_OK" not in bad_blob
    empty = _py(
        ["append", "--model", "Think Distributed Systems", "--change", "   "],
        env,
    )
    assert empty.returncode != 0
    assert "APPLY_OK" not in empty.stdout + empty.stderr
    missing_tokens = _py(
        [
            "append",
            "--model",
            "Think Distributed Systems",
            "--change",
            "restarted a process",
        ],
        env,
    )
    miss_blob = missing_tokens.stdout + missing_tokens.stderr
    assert missing_tokens.returncode != 0
    assert "IaC" in miss_blob or "Palemon" in miss_blob
    assert "APPLY_OK" not in miss_blob


def test_append_is_idempotent_per_beat(tmp_path: Path) -> None:
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    args = [
        "append",
        "--model",
        "Acing the System Design Interview",
        "--change",
        "IaC: one beat; Palemon: no game code",
    ]
    first = _py(args, env)
    second = _py(args, env)
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    logs = list((Path(env["GCS_STUDIO_ARCHIVE"]) / "log").glob("*.md"))
    assert len(logs) == 1
    applies = [
        line
        for line in logs[0].read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("- APPLY ")
    ]
    assert len(applies) == 1, applies


def test_beat_subcommand_rotates_allowed_models(tmp_path: Path) -> None:
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    proc = _py(
        ["beat", "--change", "IaC: watchdog loop; Palemon: no game code"],
        env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    text = (Path(env["GCS_STUDIO_ARCHIVE"]) / "log").glob("*.md")
    files = list(text)
    assert files
    body = files[0].read_text(encoding="utf-8")
    assert any(model in body for model in MANNING_MODELS)
    assert "IaC:" in body
    assert "Palemon:" in body


def test_check_fails_closed_without_current_beat_line(tmp_path: Path) -> None:
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    missing = _py(["check"], env)
    assert missing.returncode != 0
    _py(
        [
            "append",
            "--model",
            "Think Distributed Systems",
            "--change",
            "IaC: timeouts first-class; Palemon: no game code",
        ],
        env,
    )
    ok = _py(["check"], env)
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_watchdog_studio_ops_beat_must_append_apply_log() -> None:
    text = WATCHDOG.read_text(encoding="utf-8")
    assert APPLY_LOG.name in text or "apply_log.py" in text
    assert "beat" in text.lower() or "apply_log" in text
    assert "sleep 600" in text or "GCS_TICKER_SEC" in text
    assert "acp_inject.py" not in text


def test_hive_law_documents_manning_apply_log_gate() -> None:
    hive = HIVE.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")
    wipe = WIPE.read_text(encoding="utf-8")
    soul = SOUL.read_text(encoding="utf-8")
    prompt = PROMPT.read_text(encoding="utf-8")
    fold_hive = " ".join(hive.lower().split())
    for title in MANNING_MODELS:
        assert title in hive, title
    assert "studio-archive/log" in hive
    assert "YYYY-MM-DD.md" in hive or "yyyy-mm-dd.md" in fold_hive
    assert "HEALTH_OK" in hive
    assert "apply" in fold_hive
    assert "copyright" in fold_hive
    assert "10-minute" in fold_hive or "10 minute" in fold_hive or "600" in hive
    assert "LIV-71" in hive or "liv-71" in fold_hive
    assert PRIVATE_GAME not in hive
    assert "apply-log" in agents.lower() or "apply log" in agents.lower() or "HIVE.md" in agents
    assert "apply-log" in wipe.lower() or "HIVE.md" in wipe or "apply log" in wipe.lower()
    soul_blob = (soul + "\n" + prompt).lower()
    assert "apply-log" in soul_blob or "apply log" in soul_blob or "manning" in soul_blob


def test_health_check_usage_names_apply_log_gate() -> None:
    text = HEALTH.read_text(encoding="utf-8")
    assert "apply_log" in text or "APPLY_LOG" in text
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    proc = _run(HEALTH, ["--help"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "APPLY" in blob.upper() or "apply-log" in blob.lower()


def test_doctor_and_env_example_name_apply_log() -> None:
    doctor = DOCTOR.read_text(encoding="utf-8")
    env = STUDIO_ENV.read_text(encoding="utf-8")
    assert "apply_log.py" in doctor
    assert "HIVE.md" in doctor
    assert "GCS_STUDIO_ARCHIVE" in env or "apply-log" in env.lower()


def test_apply_log_never_embeds_copyrighted_book_text() -> None:
    src = APPLY_LOG.read_text(encoding="utf-8")
    hive = HIVE.read_text(encoding="utf-8")
    for blob in (src, hive):
        assert PRIVATE_GAME not in blob
        assert "```" not in blob or "APPLY" in blob
        # No long quoted passages that would be book excerpts.
        for line in blob.splitlines():
            if line.strip().startswith(">"):
                assert len(line) < 80
        assert len(blob) < 20_000
    for title in MANNING_MODELS:
        assert title in src or title in hive
