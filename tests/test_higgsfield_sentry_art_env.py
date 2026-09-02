"""Art Higgsfield MCP env/sentry: document knobs, fail-closed on key leaks.

Distinct from WIPE leftover-green / empty GitHub CI. Palemon Linear is Living
Sky (LIV). Never print secret values. Never put API keys in git.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SENTRY = REPO / "scripts" / "studio" / "higgsfield_sentry.py"
SECRET_SCAN = REPO / "scripts" / "secret_scan.py"
DOCTOR = REPO / "doctor.sh"
RECOVER = REPO / "recover.sh"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"
DOT_ENV_EXAMPLE = REPO / ".env.example"
GITIGNORE = REPO / ".gitignore"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
AGENTS = REPO / "AGENTS.md"

HIGGSFIELD_NAMES = (
    "HIGGSFIELD_API_KEY",
    "HIGGSFIELD_SECRET",
)
SENTRY_NAMES = (
    "SENTRY_DSN",
    "GCS_SENTRY_DSN",
)


def _load_sentry():
    assert SENTRY.is_file(), f"missing {SENTRY}"
    spec = importlib.util.spec_from_file_location("gcs_higgsfield_sentry", SENTRY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_higgsfield_key() -> str:
    return "hf_test_" + ("k" * 24)


def _fake_sentry_dsn() -> str:
    return "https://" + ("d" * 16) + "@o0.ingest.sentry.io/9"


def _run(
    script: Path,
    env: dict[str, str],
    *,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _base_env(tmp_path: Path, state: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_MIND_SEATS": "",
        "GCS_BOT_BIND_OPTIONAL": "1",
        "GCS_START_SEAT_DAEMONS": "0",
        "GCS_RECOVER_DRY_RUN": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
    }


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _no_uncommented_assignment(text: str, name: str) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith(name + "="):
            raise AssertionError(f"must not assign {name}: {stripped!r}")


def test_studio_env_example_documents_higgsfield_and_sentry_without_secrets() -> None:
    text = STUDIO_ENV_EXAMPLE.read_text(encoding="utf-8")
    low = text.lower()
    assert "higgsfield" in low
    assert "cursor catalog" in low or "catalog login" in low
    assert "never print" in low or "never commit" in low
    assert "fail-closed" in low or "fail closed" in low
    assert "doctor" in low and "recover" in low
    for name in HIGGSFIELD_NAMES + SENTRY_NAMES:
        assert name in text, name
        _no_uncommented_assignment(text, name)
    assert "mcp.higgsfield.ai" in low or "https://mcp.higgsfield.ai/mcp" in low
    assert "do not copy" in low or "grok-home" in low
    assert "leftover-green" not in low
    assert "empty github ci" not in low
    fake = _fake_higgsfield_key()
    assert fake not in text
    assert _fake_sentry_dsn() not in text
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#") and "=" in stripped:
            _, _, rhs = stripped.partition("=")
            assert "hf_" not in rhs.lower()
            assert "@o" not in rhs.lower() or "sentry" not in rhs.lower()


def test_dot_env_example_names_higgsfield_sentry_without_values() -> None:
    text = DOT_ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "HIGGSFIELD_API_KEY" in text
    assert "SENTRY_DSN" in text or "GCS_SENTRY_DSN" in text
    assert "higgsfield" in text.lower()
    for name in HIGGSFIELD_NAMES + SENTRY_NAMES:
        if name in text:
            _no_uncommented_assignment(text, name)


def test_gitignore_hides_higgsfield_and_sentry_env() -> None:
    ignore = GITIGNORE.read_text(encoding="utf-8")
    assert "higgsfield.env" in ignore
    assert "sentry.env" in ignore


def test_cursor_mcp_json_stays_linear_taskboard_without_higgsfield() -> None:
    raw = CURSOR_MCP.read_text(encoding="utf-8")
    data = json.loads(raw)
    servers = data.get("mcpServers") or {}
    assert set(servers) == {"taskboard", "linear"}, servers
    blob = json.dumps(data).lower()
    assert "higgsfield" not in blob
    assert "sentry" not in blob
    assert "higg" not in blob
    for name in HIGGSFIELD_NAMES + SENTRY_NAMES:
        assert name not in raw


def test_secret_scan_flags_higgsfield_key_without_printing_value(tmp_path: Path) -> None:
    fake = _fake_higgsfield_key()
    poisoned = tmp_path / "leak.env"
    poisoned.write_text("HIGGSFIELD_API_KEY=" + fake + "\n", encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(SECRET_SCAN), "--root", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "higgsfield_key_assignment" in blob
    assert fake not in blob


def test_secret_scan_flags_sentry_dsn_without_printing_value(tmp_path: Path) -> None:
    fake = _fake_sentry_dsn()
    poisoned = tmp_path / "dsn.env"
    poisoned.write_text("SENTRY_DSN=" + fake + "\n", encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(SECRET_SCAN), "--root", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "sentry_dsn_assignment" in blob
    assert fake not in blob
    assert "d" * 16 not in blob


def test_secret_scan_allows_commented_empty_higgsfield_knobs(tmp_path: Path) -> None:
    clean = tmp_path / "studio.env.example"
    clean.write_text(
        "# HIGGSFIELD_API_KEY=\n# HIGGSFIELD_SECRET=\n# SENTRY_DSN=\n# GCS_SENTRY_DSN=\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["python3", str(SECRET_SCAN), "--root", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "secret_scan=clean" in blob


def test_higgsfield_argv_api_key_is_a_leak() -> None:
    mod = _load_sentry()
    text = (
        "[mcp_servers.higgsfield]\n"
        'command = "higgsfield-mcp"\n'
        'args = ["--api-key", "x"]\n'
    )
    hits = mod.scan_mcp_document("grok-home/config.toml", text)
    rules = {h[1] for h in hits}
    assert "higgsfield_argv_key" in rules, hits
    for hit in hits:
        assert len(hit) == 3
        assert "x" not in str(hit[1])


def test_higgsfield_env_expansion_is_not_a_leak() -> None:
    mod = _load_sentry()
    text = (
        "[mcp_servers.higgsfield]\n"
        'url = "https://mcp.higgsfield.ai/mcp"\n'
        "\n"
        "[mcp_servers.higgsfield.env]\n"
        'HIGGSFIELD_API_KEY = "${HIGGSFIELD_API_KEY}"\n'
    )
    hits = mod.scan_mcp_document("grok-home/config.toml", text)
    assert hits == [], hits


def test_higgsfield_literal_env_is_a_leak() -> None:
    mod = _load_sentry()
    fake = _fake_higgsfield_key()
    text = (
        "[mcp_servers.higgsfield.env]\n"
        "HIGGSFIELD_API_KEY = \"" + fake + "\"\n"
    )
    hits = mod.scan_mcp_document("config.toml", text)
    assert any(h[1] == "higgsfield_env_literal" for h in hits), hits
    dumped = json.dumps(hits)
    assert fake not in dumped


def test_json_mcp_higgsfield_argv_and_env_literals() -> None:
    mod = _load_sentry()
    fake = _fake_higgsfield_key()
    payload = {
        "mcpServers": {
            "higgsfield": {
                "command": "npx",
                "args": ["higgsfield-mcp", "--secret", fake],
                "env": {"HIGGSFIELD_SECRET": fake},
            }
        }
    }
    hits = mod.scan_mcp_document("mcp.json", json.dumps(payload))
    rules = {h[1] for h in hits}
    assert "higgsfield_argv_key" in rules or "higgsfield_env_literal" in rules, hits
    assert fake not in json.dumps(hits)


def test_cli_fails_closed_on_state_toml_without_printing_key(tmp_path: Path) -> None:
    fake = _fake_higgsfield_key()
    state = tmp_path / "a2a-state"
    cfg = state / "art" / "grok-home" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "[mcp_servers.higgsfield]\n"
        'command = "higgsfield-mcp"\n'
        'args = ["--api-key", "' + fake + '"]\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["python3", str(SENTRY), "--root", str(tmp_path / "empty-root"), "--state", str(state)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "higgsfield_sentry=FAIL" in blob
    assert "higgsfield_argv_key" in blob
    assert fake not in blob


def test_cli_clean_on_empty_state(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / ".cursor").mkdir(parents=True)
    (root / ".cursor" / "mcp.json").write_text(
        '{"mcpServers": {"taskboard": {"command": "true"}, "linear": {"url": "https://mcp.linear.app/mcp"}}}',
        encoding="utf-8",
    )
    state = tmp_path / "state"
    state.mkdir()
    proc = subprocess.run(
        ["python3", str(SENTRY), "--root", str(root), "--state", str(state)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "higgsfield_sentry=clean" in blob


def test_doctor_and_recover_invoke_sentry_and_never_dump_env() -> None:
    doctor = DOCTOR.read_text(encoding="utf-8")
    recover = RECOVER.read_text(encoding="utf-8")
    assert "higgsfield_sentry.py" in doctor
    assert "higgsfield_sentry.py" in recover
    assert "scripts/studio/higgsfield_sentry.py" in doctor
    recover_sentry_at = recover.find("higgsfield_sentry.py")
    recover_ok_at = recover.find("RECOVER_OK")
    assert recover_sentry_at != -1 and recover_ok_at != -1
    assert recover_sentry_at < recover_ok_at
    for text in (doctor, recover):
        low = text.lower()
        assert "printenv" not in low
        assert "cat studio.env" not in low
        assert "echo \"$HIGGSFIELD_API_KEY\"" not in text
        assert "echo $HIGGSFIELD_API_KEY" not in text
        assert "echo \"$SENTRY_DSN\"" not in text
        assert "set -x" not in text
    assert "higgsfield_sentry.py" in doctor.split("for p in", 1)[-1] or "higgsfield_sentry.py" in doctor


def test_doctor_fails_closed_when_art_mcp_would_leak_key(tmp_path: Path) -> None:
    fake = _fake_higgsfield_key()
    state = tmp_path / "a2a-state"
    cfg = state / "art" / "grok-home" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "[mcp_servers.higgsfield]\n"
        'command = "higgsfield-mcp"\n'
        'args = ["--api-key", "' + fake + '"]\n',
        encoding="utf-8",
    )
    env = _base_env(tmp_path, state)
    env.update({k: v for k, v in os.environ.items() if k not in env})
    proc = _run(DOCTOR, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "doctor: FAIL" in blob or "higgsfield_sentry=FAIL" in blob
    assert fake not in blob
    assert "higgsfield_argv_key" in blob or "higgsfield" in blob.lower()


def test_recover_fails_closed_before_start_when_art_mcp_would_leak(tmp_path: Path) -> None:
    fake = _fake_higgsfield_key()
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    cfg = state / "art" / "grok-home" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "[mcp_servers.higgsfield]\n"
        'command = "higgsfield-mcp"\n'
        'args = ["--token", "' + fake + '"]\n',
        encoding="utf-8",
    )
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    proc = _run(RECOVER, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "RECOVER_OK" not in blob
    assert "start-studio-bus.sh" not in blob
    assert "start-taskboard.sh" not in blob
    assert fake not in blob
    assert "higgsfield_sentry=FAIL" in blob or "higgsfield" in blob.lower()


def test_wipe_higgsfield_step_is_sentry_not_leftover_green() -> None:
    text = WIPE.read_text(encoding="utf-8")
    low = text.lower()
    assert "higgsfield" in low
    assert "studio.env.example" in text
    assert "fail-closed" in low or "fail closed" in low
    assert "higgsfield_sentry" in low or "art tools would leak" in low or "leak" in low
    assert "HIGGSFIELD_API_KEY" in text
    agents = AGENTS.read_text(encoding="utf-8")
    assert "HIGGSFIELD" in agents or "Higgsfield" in agents
    assert "never print" in agents.lower() or "never commit" in agents.lower()
    # Distinct from leftover-green ship-gate folklore in this Higgsfield step.
    step = ""
    for chunk in text.split("\n\n"):
        if "Higgsfield" in chunk or "higgsfield" in chunk.lower():
            step += chunk + "\n"
    assert "leftover-green" not in step.lower()
    assert "empty github" not in step.lower()
