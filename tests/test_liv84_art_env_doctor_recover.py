"""LIV-84 art env: doctor/recover fail-closed on Cursor catalog merge / remint.

Leftover #143 is argv/literal leak sentry (Higgsfield keys on MCP argv/env).
Leftover #137 is LIV-93 catalog docs (no doctor/recover hook). This slice is
the remaining runtime gate: Extra High Higgsfield is LIV-84 cloud-env snapshot
login; Sentry DSN is Secrets/env. doctor.sh and recover.sh refuse when the
Cursor catalog already contains Higgsfield/Sentry MCP even with ${VAR}
expansions (not a leak), when `.cursor/environment.json` remints cloud-env,
or when `cloud-env` is added as a registry seat.

Grok-home Higgsfield stays grok-only and is not a Cursor merge. Never print
secret values. Living Sky (LIV) only. Never Bot CloudAgent. Never vendor Hermes.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "scripts" / "studio" / "liv84_art_env.py"
DOCTOR = REPO / "doctor.sh"
RECOVER = REPO / "recover.sh"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
AGENTS = REPO / "AGENTS.md"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"

HIGGSFIELD_MCP_URL = "https://mcp.higgsfield.ai/mcp"
FAKE_HF_KEY = "hf_test_" + ("k" * 24)
FAKE_DSN = "https://" + ("d" * 16) + "@o0.ingest.sentry.io/9"


def _load_gate():
    assert GATE.is_file(), f"missing {GATE}"
    spec = importlib.util.spec_from_file_location("gcs_liv84_art_env", GATE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    env = {
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
    env.update({k: v for k, v in os.environ.items() if k not in env})
    return env


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _linear_taskboard_mcp() -> dict:
    return {
        "mcpServers": {
            "taskboard": {
                "command": "bash",
                "args": ["${workspaceFolder}/scripts/studio/taskboard/run-mcp.sh"],
            },
            "linear": {
                "url": "https://mcp.linear.app/mcp",
                "headers": {"Authorization": "Bearer ${LINEAR_API_KEY}"},
            },
        }
    }


def _merged_higgsfield_mcp(*, literal: bool = False) -> dict:
    payload = _linear_taskboard_mcp()
    auth = FAKE_HF_KEY if literal else "${HIGGSFIELD_API_KEY}"
    payload["mcpServers"]["higgsfield"] = {
        "url": HIGGSFIELD_MCP_URL,
        "headers": {"Authorization": "Bearer " + auth},
    }
    return payload


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _mini_root(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    _write_json(root / ".cursor" / "mcp.json", _linear_taskboard_mcp())
    _write_json(
        root / "docs" / "a2a" / "registry.json",
        {"seats": {"art": {"card": "docs/a2a/cards/art.json"}}},
    )
    return root


def test_gate_script_exists() -> None:
    assert GATE.is_file(), "scripts/studio/liv84_art_env.py is the remaining LIV-84 doctor/recover gate"


def test_cursor_mcp_higgsfield_expansion_is_catalog_merge_not_a_leak() -> None:
    """#143 leak sentry would allow ${HIGGSFIELD_API_KEY}; this gate must not."""
    mod = _load_gate()
    hits = mod.scan_cursor_mcp(".cursor/mcp.json", json.dumps(_merged_higgsfield_mcp()))
    rules = {h[1] for h in hits}
    assert "cursor_catalog_merged" in rules, hits
    dumped = json.dumps(hits)
    assert FAKE_HF_KEY not in dumped
    assert "${HIGGSFIELD_API_KEY}" not in dumped


def test_expansion_merge_is_clean_for_leak_sentry_but_not_liv84() -> None:
    """Remaining slice after #143: env expansions are not leaks, still catalog merge."""
    sentry_path = REPO / "scripts" / "studio" / "higgsfield_sentry.py"
    assert sentry_path.is_file()
    spec = importlib.util.spec_from_file_location("gcs_higgsfield_sentry", sentry_path)
    assert spec is not None and spec.loader is not None
    leak = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(leak)
    payload = json.dumps(_merged_higgsfield_mcp())
    leak_hits = leak.scan_mcp_document(".cursor/mcp.json", payload)
    assert leak_hits == [], leak_hits
    merge_hits = _load_gate().scan_cursor_mcp(".cursor/mcp.json", payload)
    assert any(h[1] == "cursor_catalog_merged" for h in merge_hits), merge_hits


def test_cursor_mcp_linear_taskboard_is_clean() -> None:
    mod = _load_gate()
    hits = mod.scan_cursor_mcp(".cursor/mcp.json", json.dumps(_linear_taskboard_mcp()))
    assert hits == [], hits


def test_sentry_mcp_in_cursor_catalog_is_fail_closed() -> None:
    mod = _load_gate()
    payload = _linear_taskboard_mcp()
    payload["mcpServers"]["sentry"] = {
        "url": "https://sentry.io/api/0/",
        "env": {"SENTRY_DSN": "${SENTRY_DSN}"},
    }
    hits = mod.scan_cursor_mcp(".cursor/mcp.json", json.dumps(payload))
    rules = {h[1] for h in hits}
    assert "cursor_catalog_merged" in rules or "sentry_in_cursor_catalog" in rules, hits
    assert FAKE_DSN not in json.dumps(hits)


def test_grok_home_higgsfield_expansion_is_not_cursor_merge(tmp_path: Path) -> None:
    root = _mini_root(tmp_path)
    state = tmp_path / "state"
    cfg = state / "art" / "grok-home" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "[mcp_servers.higgsfield]\n"
        f'url = "{HIGGSFIELD_MCP_URL}"\n'
        "\n"
        "[mcp_servers.higgsfield.env]\n"
        'HIGGSFIELD_API_KEY = "${HIGGSFIELD_API_KEY}"\n',
        encoding="utf-8",
    )
    mod = _load_gate()
    hits = mod.collect_hits(root=root, state=state)
    assert hits == [], hits


def test_environment_json_remints_liv84(tmp_path: Path) -> None:
    root = _mini_root(tmp_path)
    env_json = root / ".cursor" / "environment.json"
    env_json.write_text(
        json.dumps({"snapshot": "liv-84", "SENTRY_DSN": FAKE_DSN}) + "\n",
        encoding="utf-8",
    )
    mod = _load_gate()
    hits = mod.collect_hits(root=root, state=None)
    rules = {h[1] for h in hits}
    assert "cloud_env_remint" in rules, hits
    blob = mod.format_report(hits)
    assert FAKE_DSN not in blob
    assert "d" * 16 not in blob


def test_cloud_env_registry_seat_is_remint(tmp_path: Path) -> None:
    root = _mini_root(tmp_path)
    _write_json(
        root / "docs" / "a2a" / "registry.json",
        {"seats": {"art": {}, "cloud-env": {"card": "docs/a2a/cards/cloud-env.json"}}},
    )
    mod = _load_gate()
    hits = mod.collect_hits(root=root, state=None)
    rules = {h[1] for h in hits}
    assert "cloud_env_registry_seat" in rules, hits


def test_cli_fails_closed_on_live_cursor_mcp_merge_without_printing_key(
    tmp_path: Path,
) -> None:
    root = _mini_root(tmp_path)
    state = tmp_path / "state"
    live = state / "extra-high" / ".cursor" / "mcp.json"
    _write_json(live, _merged_higgsfield_mcp(literal=True))
    proc = subprocess.run(
        ["python3", str(GATE), "--root", str(root), "--state", str(state)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "liv84_art_env=FAIL" in blob
    assert "cursor_catalog_merged" in blob
    assert FAKE_HF_KEY not in blob


def test_cli_clean_on_linear_taskboard_checkout(tmp_path: Path) -> None:
    root = _mini_root(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    proc = subprocess.run(
        ["python3", str(GATE), "--root", str(root), "--state", str(state)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "liv84_art_env=clean" in blob


def test_repo_cursor_mcp_is_not_already_merged() -> None:
    raw = CURSOR_MCP.read_text(encoding="utf-8")
    data = json.loads(raw)
    servers = data.get("mcpServers") or {}
    assert set(servers) == {"taskboard", "linear"}, servers
    blob = json.dumps(data).lower()
    assert "higgsfield" not in blob
    assert "sentry" not in blob
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    seats = registry.get("seats") or {}
    assert "cloud-env" not in seats
    assert not (REPO / ".cursor" / "environment.json").exists()


def test_doctor_and_recover_invoke_liv84_gate_before_ok() -> None:
    doctor = DOCTOR.read_text(encoding="utf-8")
    recover = RECOVER.read_text(encoding="utf-8")
    assert "liv84_art_env.py" in doctor
    assert "liv84_art_env.py" in recover
    assert "scripts/studio/liv84_art_env.py" in doctor
    recover_gate_at = recover.find("liv84_art_env.py")
    recover_ok_at = recover.find("RECOVER_OK")
    assert recover_gate_at != -1 and recover_ok_at != -1
    assert recover_gate_at < recover_ok_at
    for text in (doctor, recover):
        low = text.lower()
        assert "printenv" not in low
        assert "echo \"$HIGGSFIELD_API_KEY\"" not in text
        assert "echo $HIGGSFIELD_API_KEY" not in text
        assert "echo \"$SENTRY_DSN\"" not in text
        assert "set -x" not in text
    assert "liv84_art_env.py" in doctor.split("for p in", 1)[-1]
    assert "higgsfield_sentry.py" in doctor
    assert "higgsfield_sentry.py" in recover


def test_doctor_fails_closed_when_live_cursor_catalog_merges(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    live = state / ".cursor" / "mcp.json"
    _write_json(live, _merged_higgsfield_mcp())
    env = _base_env(tmp_path, state)
    proc = _run(DOCTOR, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "doctor: FAIL" in blob or "liv84_art_env=FAIL" in blob
    assert FAKE_HF_KEY not in blob
    assert "${HIGGSFIELD_API_KEY}" not in blob
    assert "liv84" in blob.lower() or "catalog" in blob.lower() or "higgsfield" in blob.lower()


def test_recover_fails_closed_before_start_when_cursor_catalog_merges(
    tmp_path: Path,
) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    live = state / "art" / ".cursor" / "mcp.json"
    _write_json(live, _merged_higgsfield_mcp(literal=True))
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
    assert FAKE_HF_KEY not in blob
    assert "liv84_art_env=FAIL" in blob or "liv84" in blob.lower() or "catalog" in blob.lower()


def test_wipe_and_agents_name_liv84_catalog_gate_not_leak_sentry() -> None:
    wipe = WIPE.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")
    studio = STUDIO_ENV_EXAMPLE.read_text(encoding="utf-8")
    for label, text in (("WIPE.md", wipe), ("AGENTS.md", agents), ("studio.env.example", studio)):
        low = text.lower()
        assert "liv-84" in low or "liv84" in low, label
        assert "higgsfield" in low, label
        assert "sentry" in low, label
        assert "fail-closed" in low or "fail closed" in low, label
        assert "doctor" in low and "recover" in low, label
        assert "leftover-green" not in low, label
        assert "empty github" not in low, label
        assert FAKE_HF_KEY not in text
        assert FAKE_DSN not in text
    assert "catalog" in wipe.lower() or "mcp.json" in wipe
    assert "do not remint" in (wipe + agents + studio).lower()
    # #143 leak sentry is on main; this PR adds the catalog/remint gate beside it.
    assert (REPO / "scripts" / "studio" / "higgsfield_sentry.py").is_file()
    assert GATE.is_file()
    # Do not clone leftover #137 ART_ENV pack.
    assert not (REPO / "docs" / "studio" / "art" / "ART_ENV.md").exists()
    assert not (REPO / "scripts" / "art" / "sentry_env.py").exists()
    for name in ("HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET", "SENTRY_DSN", "GCS_SENTRY_DSN"):
        for line in studio.splitlines():
            stripped = line.strip()
            if stripped.startswith(name + "="):
                raise AssertionError(f"must not assign {name}: {stripped!r}")
