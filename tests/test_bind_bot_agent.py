"""bind-bot-agent.sh upserts Bot seat + skipSeats without printing secrets."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIND = ROOT / "scripts" / "a2a" / "bind-bot-agent.sh"
PLACEHOLDER = "REPLACE_WITH_YOUR_GROK_BOT_AGENT_ID"
BOUND_ID = "11111111-2222-4333-8444-555555555555"
OTHER_REAL_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _gcs_tree(tmp_path: Path) -> Path:
    """Minimal GCS-shaped tree so bind can run against a temp ROOT."""
    docs = tmp_path / "docs" / "a2a"
    _write_json(
        docs / "bot-agents.json",
        {
            "version": "1.0.0",
            "description": "Grok Bot seats on the local A2A bus.",
            "seats": {
                "donald": {
                    "kind": "grok-bot",
                    "agentId": PLACEHOLDER,
                    "inbox": ".a2a-state/donald",
                }
            },
        },
    )
    _write_json(
        docs / "registry.json",
        {
            "version": "1.0.0",
            "hub": "http://127.0.0.1:8732",
            "skipSeats": ["donald"],
            "seats": {
                "donald": {
                    "card": "docs/a2a/cards/donald.json",
                    "endpoint": "http://127.0.0.1:8732/a2a/donald",
                    "wellKnown": "http://127.0.0.1:8732/a2a/donald/.well-known/agent-card.json",
                },
                "floor": {
                    "card": "docs/a2a/cards/floor.json",
                    "endpoint": "http://127.0.0.1:8732/a2a/floor",
                    "wellKnown": "http://127.0.0.1:8732/a2a/floor/.well-known/agent-card.json",
                    "acpPort": 8740,
                },
            },
        },
    )
    _write_json(
        docs / "cards" / "floor.json",
        {"name": "Floor", "description": "queue", "version": "1.0.0"},
    )
    _write_json(
        docs / "cards" / "donald.json",
        {"name": "Donald", "description": "orchestrator bot", "version": "1.0.0"},
    )
    return tmp_path


def _run_bind(
    tree: Path,
    extra_env: dict[str, str] | None = None,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GCS_ROOT": str(tree),
        "GCS_BOT_AGENT_ID": BOUND_ID,
        "GCS_BOT_SEAT": "orchestrator",
        "GCS_BOT_AGENT_NAME": "Studio Orchestrator",
        "GCS_A2A_STATE": str(tree / ".a2a-state"),
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(BIND), *(args or [])],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_bind_script_is_present() -> None:
    assert BIND.is_file(), "missing scripts/a2a/bind-bot-agent.sh"
    text = BIND.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")


def test_bind_updates_agent_id_and_skip_seats(tmp_path: Path) -> None:
    tree = _gcs_tree(tmp_path)
    proc = _run_bind(tree)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "BOT_BIND_OK" in combined
    assert "seat=orchestrator" in combined
    assert BOUND_ID not in combined
    assert "CURSOR_API_KEY" not in combined

    bots = json.loads((tree / "docs" / "a2a" / "bot-agents.json").read_text(encoding="utf-8"))
    seat = bots["seats"]["orchestrator"]
    assert seat["kind"] == "grok-bot"
    assert seat["agentId"] == BOUND_ID
    assert seat["inbox"] == ".a2a-state/orchestrator"

    registry = json.loads((tree / "docs" / "a2a" / "registry.json").read_text(encoding="utf-8"))
    assert "orchestrator" in registry["skipSeats"]
    assert "donald" in registry["skipSeats"]
    orch = registry["seats"]["orchestrator"]
    assert orch["card"] == "docs/a2a/cards/orchestrator.json"
    assert orch["endpoint"] == "http://127.0.0.1:8732/a2a/orchestrator"
    assert "acpPort" not in orch

    card = json.loads((tree / "docs" / "a2a" / "cards" / "orchestrator.json").read_text(encoding="utf-8"))
    assert card["name"]
    assert "orchestrator" in card["supportedInterfaces"][0]["url"]

    bind_state = json.loads((tree / ".a2a-state" / "bot-bind.json").read_text(encoding="utf-8"))
    assert bind_state["seat"] == "orchestrator"
    assert bind_state["agentId"] == BOUND_ID
    assert bind_state["boundAt"]


def test_bind_is_idempotent(tmp_path: Path) -> None:
    tree = _gcs_tree(tmp_path)
    first = _run_bind(tree)
    second = _run_bind(tree)
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    bots = json.loads((tree / "docs" / "a2a" / "bot-agents.json").read_text(encoding="utf-8"))
    assert bots["seats"]["orchestrator"]["agentId"] == BOUND_ID


def test_bind_preserves_real_donald_uuid_when_creating_orchestrator(tmp_path: Path) -> None:
    tree = _gcs_tree(tmp_path)
    bots_path = tree / "docs" / "a2a" / "bot-agents.json"
    _write_json(
        bots_path,
        {
            "version": "1.0.0",
            "seats": {
                "donald": {
                    "kind": "grok-bot",
                    "agentId": OTHER_REAL_ID,
                    "inbox": ".a2a-state/donald",
                }
            },
        },
    )
    proc = _run_bind(tree)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    bots = json.loads(bots_path.read_text(encoding="utf-8"))
    assert bots["seats"]["donald"]["agentId"] == OTHER_REAL_ID
    assert bots["seats"]["orchestrator"]["agentId"] == BOUND_ID


def test_bind_can_update_donald_seat(tmp_path: Path) -> None:
    tree = _gcs_tree(tmp_path)
    proc = _run_bind(tree, extra_env={"GCS_BOT_SEAT": "donald", "GCS_BOT_AGENT_NAME": "Donald"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    bots = json.loads((tree / "docs" / "a2a" / "bot-agents.json").read_text(encoding="utf-8"))
    assert bots["seats"]["donald"]["agentId"] == BOUND_ID
    registry = json.loads((tree / "docs" / "a2a" / "registry.json").read_text(encoding="utf-8"))
    assert "donald" in registry["skipSeats"]
    assert (tree / "docs" / "a2a" / "cards" / "donald.json").is_file()


def test_check_fails_on_placeholder_unless_optional(tmp_path: Path) -> None:
    tree = _gcs_tree(tmp_path)
    env = {
        **os.environ,
        "GCS_ROOT": str(tree),
        "GCS_A2A_STATE": str(tree / ".a2a-state"),
    }
    env.pop("GCS_BOT_BIND_OPTIONAL", None)
    fail = subprocess.run(
        ["bash", str(BIND), "--check"],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert fail.returncode != 0
    assert PLACEHOLDER not in fail.stdout or "placeholder" in (fail.stdout + fail.stderr).lower() or "unbound" in (fail.stdout + fail.stderr).lower() or "ERR" in (fail.stdout + fail.stderr)

    optional = subprocess.run(
        ["bash", str(BIND), "--check"],
        cwd=str(tree),
        env={**env, "GCS_BOT_BIND_OPTIONAL": "1"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert optional.returncode == 0, optional.stdout + optional.stderr
    assert "WARN" in (optional.stdout + optional.stderr)

    bound = _run_bind(tree)
    assert bound.returncode == 0, bound.stdout + bound.stderr
    ok = subprocess.run(
        ["bash", str(BIND), "--check"],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_bind_requires_agent_id(tmp_path: Path) -> None:
    tree = _gcs_tree(tmp_path)
    env = {**os.environ, "GCS_ROOT": str(tree)}
    env.pop("GCS_BOT_AGENT_ID", None)
    proc = subprocess.run(
        ["bash", str(BIND)],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode != 0
    assert BOUND_ID not in proc.stdout + proc.stderr


def test_committed_example_uses_orchestrator_placeholder() -> None:
    bots = json.loads((ROOT / "docs" / "a2a" / "bot-agents.json").read_text(encoding="utf-8"))
    seats = bots["seats"]
    assert "orchestrator" in seats
    assert seats["orchestrator"]["agentId"] == PLACEHOLDER
    assert seats["orchestrator"]["kind"] == "grok-bot"
    registry = json.loads((ROOT / "docs" / "a2a" / "registry.json").read_text(encoding="utf-8"))
    assert "orchestrator" in registry["skipSeats"]
    assert "donald" in registry["skipSeats"]
    assert "orchestrator" in registry["seats"]
    assert (ROOT / "docs" / "a2a" / "cards" / "orchestrator.json").is_file()


def test_doctor_lists_bot_agents_and_honors_optional() -> None:
    doctor = ROOT / "doctor.sh"
    text = doctor.read_text(encoding="utf-8")
    assert "docs/a2a/bot-agents.json" in text
    assert "GCS_BOT_BIND_OPTIONAL" in text
    assert "bind-bot-agent.sh" in text


def test_install_invokes_bind_or_warns() -> None:
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "GCS_BOT_AGENT_ID" in text
    assert "bind-bot-agent.sh" in text
    assert "WARN" in text


def test_secret_scan_still_clean_after_bind_sources() -> None:
    scan = ROOT / "scripts" / "secret_scan.py"
    proc = subprocess.run(
        ["python3", str(scan), "--root", str(ROOT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
