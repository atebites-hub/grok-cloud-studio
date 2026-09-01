"""BDD binding: bind Grok Bot orchestrator; Bot is not ACP or CloudAgent.

Scenarios live in tests/bdd/bind_bot_orchestrator.feature.
Living Sky (LIV). Never Bot CloudAgent. Distinct from GCS #36/#74/#77.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "bdd" / "bind_bot_orchestrator.feature"
LIB = REPO / "scripts" / "a2a" / "lib.py"
START_DAEMON = REPO / "scripts" / "directors" / "start-seat-daemon.sh"
SEAT_PROMPT = REPO / "scripts" / "directors" / "seat-prompt-acp.sh"
LAUNCH_DIRECTOR = REPO / "scripts" / "directors" / "launch-director.sh"
LAUNCH_SH = REPO / "scripts" / "launch-cloud-extra-high.sh"
INSTALL_SH = REPO / "install.sh"
BOT_BRIDGE = REPO / "scripts" / "a2a" / "bot-bridge.py"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"

SCENARIO_BINDINGS = {
    "Bind upserts the Bot seat into skipSeats without printing the id": (
        "test_bind_upserts_skip_seats_without_printing_id"
    ),
    "Bind strips acpPort so the Bot cannot become an ACP target": (
        "test_bind_strips_acp_port_and_port_cli_refuses_bot"
    ),
    "ACP serve and inject refuse Bot skipSeats": (
        "test_acp_serve_and_inject_refuse_bot_skip_seats"
    ),
    "Extra High refuses a Bot CloudAgent name": (
        "test_extra_high_refuses_bot_cloudagent_name"
    ),
    "Allowed Extra High names stay grok-4.6 xhigh fast=false": (
        "test_allowed_extra_high_name_stays_grok_46_xhigh"
    ),
}


def _load_py(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bind_helpers() -> ModuleType:
    return _load_py(REPO / "tests" / "test_bind_bot_agent.py", "test_bind_bot_agent")


def _cloud_helpers() -> ModuleType:
    return _load_py(REPO / "tests" / "test_cloud_launch.py", "test_cloud_launch")


def feature_scenarios(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if raw.startswith("Scenario:"):
            names.append(raw[len("Scenario:") :].strip())
    return names


def test_feature_file_binds_every_scenario() -> None:
    assert FEATURE.is_file()
    names = feature_scenarios(FEATURE)
    assert names == list(SCENARIO_BINDINGS)
    text = FEATURE.read_text(encoding="utf-8")
    assert "Living Sky" in text
    assert "Never Bot CloudAgent" in text
    assert "#36" in text and "#74" in text and "#77" in text
    assert "bot-bridge" in text
    for name, fn in SCENARIO_BINDINGS.items():
        assert callable(globals()[fn]), name


def test_this_slice_does_not_clone_bot_bridge_prs() -> None:
    """Guard: this FAT is bind/ACP/CloudAgent refuse, not bot-bridge harvest."""
    common = (REPO / "scripts" / "directors" / "seat-daemon-common.sh").read_text(
        encoding="utf-8"
    )
    lib = LIB.read_text(encoding="utf-8")
    bus = BUS_SH.read_text(encoding="utf-8")
    bridge = BOT_BRIDGE.read_text(encoding="utf-8")
    assert "refuse_bot_acp_seat" in common
    assert "bot-not-acp-target" in common
    assert "cloudagent_name_ok" in lib
    assert "BOT_CLOUDAGENT_NAMES" in lib
    # #77 stale-pidfile tombstone is a different slice (do not remint here).
    assert "bot-bridge.standby" not in bus
    assert "bot-bridge.standby" not in bridge
    assert "STUDIO_BUS_BOT_BRIDGE_STALE" not in bus


def test_install_invokes_bind_not_cloudagent() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "GCS_BOT_AGENT_ID" in text
    assert "bind-bot-agent.sh" in text
    assert "launch-cloud-extra-high.sh" not in text
    assert "start-seat-daemon.sh" not in text


def test_bind_upserts_skip_seats_without_printing_id(tmp_path: Path) -> None:
    helpers = _bind_helpers()
    tree = helpers._gcs_tree(tmp_path)
    proc = helpers._run_bind(tree)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "BOT_BIND_OK" in combined
    assert "seat=orchestrator" in combined
    assert helpers.BOUND_ID not in combined
    assert "CURSOR_API_KEY" not in combined
    bots = json.loads((tree / "docs" / "a2a" / "bot-agents.json").read_text(encoding="utf-8"))
    seat = bots["seats"]["orchestrator"]
    assert seat["kind"] == "grok-bot"
    assert seat["agentId"] == helpers.BOUND_ID
    registry = json.loads((tree / "docs" / "a2a" / "registry.json").read_text(encoding="utf-8"))
    assert "orchestrator" in registry["skipSeats"]
    assert "donald" in registry["skipSeats"]


def test_bind_strips_acp_port_and_port_cli_refuses_bot(tmp_path: Path) -> None:
    helpers = _bind_helpers()
    tree = helpers._gcs_tree(tmp_path)
    registry_path = tree / "docs" / "a2a" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["seats"]["orchestrator"] = {
        "card": "docs/a2a/cards/orchestrator.json",
        "endpoint": "http://127.0.0.1:8732/a2a/orchestrator",
        "wellKnown": "http://127.0.0.1:8732/a2a/orchestrator/.well-known/agent-card.json",
        "acpPort": 8740,
    }
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    proc = helpers._run_bind(tree)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    bound = json.loads(registry_path.read_text(encoding="utf-8"))
    orch = bound["seats"]["orchestrator"]
    assert "acpPort" not in orch, orch

    env = {**os.environ, "GCS_ROOT": str(tree)}
    port = subprocess.run(
        ["python3", str(LIB), "port", "orchestrator"],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert port.returncode != 0, port.stdout + port.stderr
    combined = port.stdout + port.stderr
    assert "8740" not in combined
    assert "not an ACP" in combined or "bot" in combined.lower()

    shipped = subprocess.run(
        ["python3", str(LIB), "port", "orchestrator"],
        cwd=str(REPO),
        env={**os.environ, "GCS_ROOT": str(REPO)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert shipped.returncode != 0, shipped.stdout + shipped.stderr
    assert "8740" not in shipped.stdout


def test_acp_serve_and_inject_refuse_bot_skip_seats(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "state"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    for seat in ("orchestrator", "donald", "ORCHESTRATOR"):
        daemon = subprocess.run(
            ["bash", str(START_DAEMON), seat],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        combined = daemon.stdout + daemon.stderr
        assert daemon.returncode != 0, combined
        assert "bot-not-acp-target" in combined
        assert "SEAT_DAEMON_SKIP" in combined or "ACP_PROMPT_SKIP" in combined
        assert "SEAT_DAEMON_ALREADY" not in combined
        assert "grok agent serve" not in combined.lower()

        prompt = subprocess.run(
            ["bash", str(SEAT_PROMPT), seat, "ping"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        pcomb = prompt.stdout + prompt.stderr
        assert prompt.returncode != 0, pcomb
        assert "bot-not-acp-target" in pcomb
        assert "ACP_PROMPT_SKIP" in pcomb or "SEAT_DAEMON_SKIP" in pcomb

    director = subprocess.run(
        ["bash", str(LAUNCH_DIRECTOR), "orchestrator"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    dcomb = director.stdout + director.stderr
    assert director.returncode != 0, dcomb
    assert "skipSeats" in dcomb

    env_cap = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_ACP_SEATS": "orchestrator,donald,floor",
    }
    launched = subprocess.run(
        ["python3", str(LIB), "launch-seats"],
        cwd=str(REPO),
        env=env_cap,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert launched.returncode == 0, launched.stderr
    seats = {s.strip() for s in launched.stdout.splitlines() if s.strip()}
    assert "orchestrator" not in seats
    assert "donald" not in seats
    assert "floor" in seats


@pytest.mark.parametrize("bot_name", ["donald", "orchestrator", "grok-bot", "bot", "Donald"])
def test_extra_high_refuses_bot_cloudagent_name(tmp_path: Path, bot_name: str) -> None:
    cloud = _cloud_helpers()
    with cloud.MockCursorAPI(create_http=201) as api:
        proc = cloud._run(
            cloud.LAUNCH,
            ["--name", bot_name, "Implement the assigned outcome. Open a PR."],
            cloud._script_env(tmp_path, api.base, CURSOR_API_KEY=cloud.FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    assert "Bot CloudAgent" in combined or "bot-cloudagent" in combined.lower()
    assert not api.posts
    assert cloud.FAKE_KEY not in combined
    assert "never" in combined.lower()


def test_allowed_extra_high_name_stays_grok_46_xhigh(tmp_path: Path) -> None:
    cloud = _cloud_helpers()
    with cloud.MockCursorAPI(create_http=201) as api:
        proc = cloud._run(
            cloud.LAUNCH,
            ["--name", "gcs-bind-bot-fat", "Implement the assigned outcome. Open a PR."],
            cloud._script_env(tmp_path, api.base, CURSOR_API_KEY=cloud.FAKE_KEY),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    body = api.posts[0]["body"]
    assert body["model"]["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params
    assert body["autoCreatePR"] is True
    assert body["name"] == "gcs-bind-bot-fat"


def test_lib_cloudagent_ok_cli() -> None:
    env = {**os.environ, "GCS_ROOT": str(REPO)}
    allowed = subprocess.run(
        ["python3", str(LIB), "cloudagent-ok", "gcs-bind-bot-fat"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    forbidden = subprocess.run(
        ["python3", str(LIB), "cloudagent-ok", "orchestrator"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert forbidden.returncode != 0
    empty = subprocess.run(
        ["python3", str(LIB), "cloudagent-ok", ""],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert empty.returncode == 0, empty.stdout + empty.stderr
