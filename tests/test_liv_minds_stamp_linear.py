"""BDD: Grok Build minds stamp Living Sky Linear themselves (LIV-82 / LIV-43).

Scenarios live in docs/studio/bdd/liv_minds_stamp_linear.feature.
Linear MCP on Grok Build AND Cursor Cloud. Do not have Donald DIY Linear.
NEVER Black Swan. Never Bot CloudAgent. Extra High stays grok-4.6 xhigh fast=false.

Does not remint harvest PRs, cloud capacity, or Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "docs" / "studio" / "bdd" / "liv_minds_stamp_linear.feature"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
SOULS = REPO / "docs" / "studio" / "directors" / "souls"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
SEAT_MCP = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
LINEAR_KEY = REPO / "scripts" / "directors" / "linear_key.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
LIB_PY = REPO / "scripts" / "a2a" / "lib.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
AGENTS = REPO / "AGENTS.md"
ARCHITECTURE = REPO / "docs" / "ARCHITECTURE.md"
ORCH_CARD = REPO / "docs" / "a2a" / "cards" / "orchestrator.json"
FLOOR_OPS_SOUL = SOULS / "floor-ops" / "SOUL.md"
SECRET_SCAN = REPO / "scripts" / "secret_scan.py"
GITIGNORE = REPO / ".gitignore"
DOT_ENV_EXAMPLE = REPO / ".env.example"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LIVING_SKY_HOST = "linear.app/livingsky"
BLACK_SWAN = "Black Swan"
BLACK_SWAN_MONEY = "Black Swan Money"
PRIVATE_GAME = "atebites-hub/" + "palemon"
WORKSPACE_FOLDER_TOKEN = "${" + "workspaceFolder}"
BANNED_GROK_CATALOG = (
    "higgsfield",
    "studio-mind",
    "chrome-devtools",
    "GROK_HOME",
    "config.toml",
    "mcp_servers",
)

LIV_STAMP_NEEDLES = (
    "Living Sky",
    "linear.app/livingsky",
    "Livingsky",
    "LIV-*",
    "Black Swan",
)

REQUIRED_SOULS = (
    "floor",
    "floor-ops",
    "studio-ops",
    "ops",
    "art",
    "content",
    "systems",
    "qa-a",
    "qa-b",
    "audio",
    "narrative",
    "cloud",
)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _soul_paths() -> list[Path]:
    paths = sorted(SOULS.glob("*/SOUL.md"))
    assert paths, f"no SOUL.md under {SOULS}"
    return paths


def _assert_liv_stamp_law(text: str, *, label: str) -> None:
    assert text, label
    for needle in LIV_STAMP_NEEDLES:
        assert needle in text, f"{label} missing {needle!r}"
    low = text.lower()
    assert "stamp" in low, f"{label} missing stamp"
    assert "every mind turn" in low, f"{label} missing every mind turn"
    assert "never black swan" in low, f"{label} must forbid Black Swan"
    assert PRIVATE_GAME not in text, f"{label} leaked private game repo"


# --- Feature file is the example -------------------------------------------------


def test_bdd_feature_file_names_liv82_liv43_and_donald_not_diy() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    low = text.lower()
    assert "Feature: Grok Build minds stamp Living Sky Linear themselves" in text
    assert "LIV-82" in text
    assert "LIV-43" in text
    assert LIVING_SKY_HOST in text
    assert "NEVER Black Swan" in text or "never black swan" in low
    assert "do not have donald diy linear" in low
    assert "grok build" in low and "cursor cloud" in low
    assert LINEAR_MCP_URL in text
    assert "skipSeats" in text or "skip seats" in low
    assert "Bot CloudAgent" in text or "bot cloudagent" in low
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in text
    for scenario in (
        "Grok Build mind has Linear MCP in GROK_HOME",
        "Cursor Cloud Extra High has Linear MCP in checkout mcp.json",
        "A mind turn stamps Living Sky itself",
        "Donald does not DIY Linear",
        "Never Bot CloudAgent, pin grok-4.6 xhigh",
    ):
        assert f"Scenario: {scenario}" in text, scenario
    assert PRIVATE_GAME not in text


# --- Scenario: Grok Build mind has Linear MCP in GROK_HOME ----------------------


def test_grok_home_install_writes_linear_http_catalog(tmp_path: Path) -> None:
    binary = _write_exec(tmp_path / "host-bin" / "taskboard", "#!/bin/sh\necho tb\n")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GROK_HOME": str(tmp_path / "grok-home"),
        "TASKBOARD_BIN": str(binary),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    proc = subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail; source scripts/directors/seat-daemon-common.sh; "
            "install_seat_identity floor",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    cfg = Path(env["GROK_HOME"]) / "config.toml"
    text = cfg.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    linear = parsed["mcp_servers"]["linear"]
    assert linear["url"] == LINEAR_MCP_URL
    assert "${LINEAR_API_KEY}" in text
    assert "Bearer" in text
    assert parsed["compat"]["cursor"]["mcps"] is False
    assert "[mcp_servers.taskboard]" in text
    assert WORKSPACE_FOLDER_TOKEN not in text
    assert ".cursor/mcp.json" not in text
    linear_section = text.split("[mcp_servers.linear]", 1)[1].split("[", 1)[0]
    assert "command =" not in linear_section
    assert text.count("[mcp_servers.linear]") == 1
    assert "lin_api_" not in text.lower()


def test_linear_toml_merge_is_idempotent() -> None:
    mod = _load(SEAT_MCP, "gcs_seat_grok_mcp_liv")
    poisoned = (
        "[cli]\nuse_leader = true\n\n"
        "[mcp_servers.linear]\n"
        'url = "https://mcp.linear.app/sse"\n'
        "# gcs-seat-linear-mcp\n"
        "[mcp_servers.linear]\n"
        'url = "https://example.invalid/mcp"\n'
        "# gcs-seat-linear-mcp-end\n"
    )
    out = mod.merge_seat_taskboard_mcp(poisoned, "/bin/taskboard", "/tmp/db")
    parsed = tomllib.loads(out)
    assert parsed["mcp_servers"]["linear"]["url"] == LINEAR_MCP_URL
    assert parsed["mcp_servers"]["taskboard"]["command"] == "/bin/taskboard"
    assert out.count("[mcp_servers.linear]") == 1
    assert out.count("[mcp_servers.taskboard]") == 1
    assert "${LINEAR_API_KEY}" in out
    again = mod.merge_seat_taskboard_mcp(out, "/bin/taskboard", "/tmp/db")
    assert tomllib.loads(again)["mcp_servers"]["linear"]["url"] == LINEAR_MCP_URL
    assert again.count("[mcp_servers.linear]") == 1


# --- Scenario: Cursor Cloud Extra High has Linear MCP ---------------------------


def test_cursor_mcp_json_is_linear_plus_taskboard_only() -> None:
    data = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") or {}
    assert set(servers) == {"taskboard", "linear"}, servers
    linear = servers["linear"]
    assert linear.get("url") == LINEAR_MCP_URL
    headers = linear.get("headers") or {}
    auth = str(headers.get("Authorization") or headers.get("authorization") or "")
    assert "Bearer" in auth
    assert "${LINEAR_API_KEY}" in auth
    blob = json.dumps(servers)
    low = blob.lower()
    for banned in BANNED_GROK_CATALOG:
        assert banned.lower() not in low, banned
    assert "lin_api_" not in low
    assert BLACK_SWAN_MONEY.lower() not in low
    assert "ak" not in servers
    taskboard = servers["taskboard"]
    joined = " ".join(
        str(x) for x in ([taskboard.get("command", "")] + list(taskboard.get("args") or []))
    )
    assert "run-mcp.sh" in joined or "run-mcp.sh" in blob


def test_mcp_json_never_hardcodes_linear_api_key() -> None:
    raw = CURSOR_MCP.read_text(encoding="utf-8")
    assert "LINEAR_API_KEY=" not in raw
    assert "${LINEAR_API_KEY}" in raw
    for line in raw.splitlines():
        stripped = line.strip()
        if "LINEAR_API_KEY" in stripped and "${LINEAR_API_KEY}" not in stripped:
            raise AssertionError("LINEAR_API_KEY must only appear as ${LINEAR_API_KEY}")


# --- Scenario: A mind turn stamps Living Sky itself -----------------------------


def test_footer_requires_self_stamp_via_linear_mcp_not_donald() -> None:
    text = FOOTER.read_text(encoding="utf-8")
    _assert_liv_stamp_law(text, label="common_footer.txt")
    low = text.lower()
    assert "donald diy linear" in low or "do not have donald diy" in low
    assert "save_comment" in low
    assert "save_issue" in low
    assert "liv=<LIV-" in text or "liv=<LIV-*" in text
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in text
    assert "Bot CloudAgent" in text or "Grok Bot CloudAgent" in text
    assert "LINEAR_API_KEY" not in text
    assert "send.sh donald" not in low or "not" in low
    assert LINEAR_MCP_URL not in text


def test_director_souls_require_self_stamp_and_forbid_donald_diy() -> None:
    souls = _soul_paths()
    names = {path.parent.name for path in souls}
    for required in REQUIRED_SOULS:
        assert required in names, required
    for path in souls:
        text = path.read_text(encoding="utf-8")
        label = str(path.relative_to(REPO))
        _assert_liv_stamp_law(text, label=label)
        low = text.lower()
        assert "donald diy" in low or "do not have donald" in low, label
        assert "LINEAR_API_KEY" not in text
        assert LINEAR_MCP_URL not in text


def test_architecture_points_footer_at_liv_self_stamp() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "scripts/directors/common_footer.txt" in text
    assert "Living Sky" in text
    assert "LIV-*" in text
    assert BLACK_SWAN in text
    assert PRIVATE_GAME not in text


# --- Scenario: Donald does not DIY Linear ---------------------------------------


def test_donald_and_orchestrator_are_skip_seats_not_mind_seats() -> None:
    proc = subprocess.run(
        ["python3", str(LIB_PY), "mind-seats"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
        env={
            **os.environ,
            "GCS_MIND_SEATS": "floor,ops,donald,orchestrator,floor-ops",
        },
    )
    assert proc.returncode == 0, proc.stderr
    seats = {s.strip() for s in proc.stdout.splitlines() if s.strip()}
    assert "donald" not in seats
    assert "orchestrator" not in seats
    assert "floor" in seats
    assert "floor-ops" in seats


def test_process_once_donald_does_not_stamp_linear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake(_prompt: str, **_kwargs: object) -> dict:
        calls.append("ran")
        return {"text": "should not run"}

    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    mind = _load(MIND_PY, "gcs_mind_donald_diy")
    mind.STATE_DIR = tmp_path / "a2a-state"
    mind.ROOT = REPO
    inbox = tmp_path / "a2a-state" / "donald" / "inbox.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text(
        json.dumps(
            {
                "taskId": "t1",
                "parts": [{"kind": "text", "text": "stamp LIV-82 for me"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = mind.process_once("donald", runner=fake)
    assert result["consumed"] == 0
    assert "skip" in str(result.get("reason", "")).lower()
    assert calls == []


def test_orchestrator_card_does_not_diy_linear() -> None:
    card = json.loads(ORCH_CARD.read_text(encoding="utf-8"))
    blob = json.dumps(card).lower()
    assert "linear" in blob
    assert "diy" in blob or "does not stamp" in blob or "not" in blob
    assert "liv" in blob or "living sky" in blob


def test_floor_ops_mind_still_stamps_itself() -> None:
    text = FLOOR_OPS_SOUL.read_text(encoding="utf-8")
    _assert_liv_stamp_law(text, label="floor-ops/SOUL.md")
    low = text.lower()
    assert "donald-clone" in low or "donald clone" in low
    assert "stamp" in low
    assert "donald diy" in low or "do not have donald" in low


# --- Docs: two catalogs, Living Sky, never Black Swan ---------------------------


def test_docs_split_linear_catalogs_living_sky_never_black_swan() -> None:
    mind = MIND_DOC.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    wipe = WIPE.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")
    blob = "\n".join((mind, cloud, wipe, agents))
    low = blob.lower()
    assert "living sky" in low
    assert LIVING_SKY_HOST in low or "livingsky" in low
    assert "never" in low and BLACK_SWAN.lower() in low
    assert "do not copy" in mind.lower()
    assert "GROK_HOME" in mind
    assert LINEAR_MCP_URL in mind or "mcp.linear.app/mcp" in mind
    assert "save_comment" in mind.lower()
    assert "save_issue" in mind.lower()
    assert ".cursor/mcp.json" in mind
    assert ".cursor/mcp.json" in cloud
    assert "LINEAR_API_KEY" in mind
    assert "cannot scrape" in cloud.lower() or "cannot scrape" in mind.lower()
    assert "donald diy" in low or "do not have donald" in low
    assert PRIVATE_GAME not in blob


def test_secret_scan_flags_hardcoded_linear_api_key(tmp_path: Path) -> None:
    fake = "lin_" + ("a" * 24)
    poisoned = tmp_path / "leak.env"
    poisoned.write_text("LINEAR_API_KEY=" + fake + "\n", encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(SECRET_SCAN), "--root", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "linear_key_assignment" in blob
    assert fake not in blob


def test_gitignore_and_env_examples_document_linear_secret_without_value() -> None:
    ignore = GITIGNORE.read_text(encoding="utf-8")
    assert "linear.env" in ignore
    for path in (DOT_ENV_EXAMPLE, STUDIO_ENV_EXAMPLE):
        text = path.read_text(encoding="utf-8")
        assert "LINEAR_API_KEY" in text
        assert "livingsky" in text.lower() or "living sky" in text.lower()
        assert BLACK_SWAN in text
        assert "never" in text.lower()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("LINEAR_API_KEY=") and not stripped.startswith("#"):
                raise AssertionError(f"{path.name} must not assign LINEAR_API_KEY")


def test_linear_key_file_loads_without_printing_secret(tmp_path: Path) -> None:
    mod = _load(LINEAR_KEY, "gcs_linear_key")
    secret = "lin_api_" + ("x" * 24)
    key_file = tmp_path / "a2a-state" / "linear.env"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(f"LINEAR_API_KEY={secret}\n", encoding="utf-8")
    env: dict[str, str] = {}
    applied = mod.apply_linear_key_env(
        env,
        state_dir=tmp_path / "a2a-state",
        key_file=key_file,
    )
    assert applied is True
    assert env["LINEAR_API_KEY"] == secret
    dumped = json.dumps(mod.__dict__, default=str)
    assert secret not in dumped


def test_seat_common_sources_linear_key_without_echo() -> None:
    text = SEAT_COMMON.read_text(encoding="utf-8")
    assert "load_linear_api_key" in text
    assert "linear.env" in text
    assert 'echo "$LINEAR_API_KEY"' not in text
    assert "echo $LINEAR_API_KEY" not in text
    assert LINEAR_MCP_URL in text
    identity = text.split("install_seat_identity() {", 1)[1]
    assert "install_seat_grok_mcp" in identity
    assert "load_linear_api_key" in identity
