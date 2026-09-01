"""LIV-63: grok-bot-like mind plugins (ticket/A2A/cloud) on PR #47.

Executable binding for tests/features/liv63_mind_plugins.feature.

Grok plugin.json for studio-mind, a2a, and cursor-cloud without vendoring
NousResearch/hermes-agent. Mail-is-a-turn stays grok mailbox + pin + stay-up,
not ACP overlay. Does not land harvest #26/#28. Keeps #47 Extra High
cloud_list / cloud_followup. Never Bot CloudAgent.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "liv63_mind_plugins.feature"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
HUB_PY = REPO / "scripts" / "a2a" / "hub.py"
GITMODULES = REPO / ".gitmodules"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
PLUGINS_DOC = REPO / "docs" / "PLUGINS.md"
AGENTS_DOC = REPO / "AGENTS.md"
A2A_DOC = REPO / "docs" / "A2A.md"
PLUGIN_MIND = REPO / "plugins" / "studio-mind"
PLUGIN_A2A = REPO / "plugins" / "a2a"
PLUGIN_CLOUD = REPO / "plugins" / "cursor-cloud"
PRIVATE_GAME = "atebites-hub/" + "palemon"

MIND_GROK_PLUGINS: tuple[tuple[str, Path], ...] = (
    ("studio-mind", PLUGIN_MIND),
    ("a2a", PLUGIN_A2A),
    ("cursor-cloud", PLUGIN_CLOUD),
)

HARVEST_MARKERS = (
    "format_mail_turn",
    "filter_inbound_mail",
    "MAIL_MAX_CHARS",
    "mind/heartbeat",
    "defang",
    "mail envelope",
)
HIVE_CLOUD_TOOLS = ("cloud_list", "cloud_followup")
BANNED_SPAWN = ("Bot CloudAgent", "Grok Bot CloudAgent")

HERMES_DIR_NAMES = frozenset(
    {"hermes-agent", "hermes_agent", "hermes-bots", "NousResearch"}
)
HERMES_FILE_NAMES = frozenset(
    {
        "plugin.yaml",
        "message_agent.py",
        "bot_mode_dm.py",
        "bot_mode_probe.py",
    }
)
HERMES_WALK_SKIP = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        "taskboard",
    }
)

SCENARIO_BINDINGS = {
    "Mind GROK_HOME installs ticket, A2A, and cloud grok plugins": (
        "test_scenario_mind_installs_ticket_a2a_cloud_grok_plugins"
    ),
    "A2A and cloud plugins honor GCS_ROOT when copied into GROK_HOME": (
        "test_scenario_copied_plugins_honor_gcs_root"
    ),
    "Copying a Hermes tree into the repo fails the ship gate": (
        "test_scenario_copied_hermes_tree_fails_the_ship_gate"
    ),
    "Mail-is-a-turn stays grok mailbox, not ACP overlay": (
        "test_scenario_mail_is_a_turn_stays_grok_mailbox"
    ),
}


def find_hermes_tree_hits(root: Path) -> list[str]:
    """Return relative paths that look like a copied Hermes source tree.

    Docs that mention Hermes are allowed. A vendored tree is not:
    hermes-agent directories, Hermes plugin.yaml SDK, message_agent.py,
    hermes_agent package, or a pyproject named hermes-agent.
    """
    hits: list[str] = []
    root = root.resolve()
    gitmodules = root / ".gitmodules"
    if gitmodules.is_file():
        text = gitmodules.read_text(encoding="utf-8", errors="replace").lower()
        if "hermes-agent" in text or "nousresearch/hermes" in text:
            hits.append(".gitmodules")
    vendor = root / "vendor"
    if vendor.is_dir():
        for child in vendor.iterdir():
            if child.name.lower() in {"hermes", "hermes-agent", "hermes_agent"}:
                hits.append(str(child.relative_to(root)))
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        path = Path(dirpath)
        rel_parts = path.relative_to(root).parts if path != root else ()
        dirnames[:] = [
            name
            for name in dirnames
            if name not in HERMES_WALK_SKIP and not name.startswith(".git")
        ]
        for name in list(dirnames):
            if name in HERMES_DIR_NAMES:
                hits.append(str((path / name).relative_to(root)))
        for name in filenames:
            if name in HERMES_FILE_NAMES:
                hits.append(str((path / name).relative_to(root)))
            if name == "pyproject.toml":
                blob = (path / name).read_text(encoding="utf-8", errors="replace")
                low = blob.lower()
                if 'name = "hermes-agent"' in low or "name = 'hermes-agent'" in low:
                    hits.append(str((path / name).relative_to(root)))
        if "hermes_agent" in rel_parts and (path / "__init__.py").is_file():
            hits.append(str(path.relative_to(root)))
    return sorted(set(hits))


def _gherkin_scenarios(text: str) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Scenario:"):
            titles.append(stripped[len("Scenario:") :].strip())
    return titles


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _rpc_plugin(server: Path, env: dict[str, str]) -> dict:
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    proc = subprocess.run(
        ["python3", str(server)],
        cwd=str(server.parent),
        input=msg,
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert proc.stdout.strip(), proc.stderr
    return json.loads(proc.stdout.splitlines()[0])


def _load_plugin_json(plugin_dir: Path) -> dict:
    path = plugin_dir / "plugin.json"
    assert path.is_file(), f"grok plugin.json missing: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_bdd_feature_file_is_the_liv63_plugin_example() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    assert text.startswith("Feature: Grok-bot-like mind plugins")
    low = text.lower()
    for needle in (
        "liv-63",
        "ticket",
        "a2a",
        "cloud",
        "plugin.json",
        "plugin.yaml",
        "hermes-agent",
        "do not vendor",
        "#26",
        "#28",
        "#47",
        "session/prompt",
        "mailbox",
        "cloud_list",
        "cloud_followup",
    ):
        assert needle in low, needle
    assert PRIVATE_GAME not in text
    titles = _gherkin_scenarios(text)
    assert titles == list(SCENARIO_BINDINGS)
    defined = set(globals())
    for title, fn_name in SCENARIO_BINDINGS.items():
        assert fn_name in defined, (title, fn_name)


def test_scenario_mind_installs_ticket_a2a_cloud_grok_plugins(tmp_path: Path) -> None:
    for name, plugin_dir in MIND_GROK_PLUGINS:
        manifest = _load_plugin_json(plugin_dir)
        assert manifest.get("name"), name
        assert manifest.get("mcpServers") in {"./mcp.json", "mcp.json"}
        mcp_ref = str(manifest.get("mcpServers") or "")
        assert ".." not in mcp_ref
        assert not (plugin_dir / "plugin.yaml").exists(), plugin_dir
        mcp = json.loads((plugin_dir / "mcp.json").read_text(encoding="utf-8"))
        servers = mcp.get("mcpServers") or {}
        assert servers, plugin_dir
        for spec in servers.values():
            args = spec.get("args") or []
            joined = " ".join(str(a) for a in args)
            assert ".." not in joined
            assert "${workspaceFolder}" not in joined

    log = tmp_path / "plugin.argv"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        'printf "GROK_HOME=%s\\n" "$GROK_HOME" >> '
        f'"{log}.env"\n'
        "exit 0\n",
    )
    env = {
        "PATH": f"{grok.parent}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GROK_HOME": str(tmp_path / "grok-home"),
        "TASKBOARD_BIN": str(
            _write_exec(tmp_path / "host-bin" / "taskboard", "#!/bin/sh\nexit 0\n")
        ),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_mind_grok_plugins floor
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    argv = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert argv.count("plugin") >= 3, argv
    assert argv.count("install") >= 3, argv
    assert "--trust" in argv, argv
    for name, plugin_dir in MIND_GROK_PLUGINS:
        assert name in argv, (name, argv)
        assert str(plugin_dir) in argv or plugin_dir.name in argv, (plugin_dir, argv)
    assert "-p" not in argv.split(), argv
    assert "--plugin-dir" not in argv, argv
    for name, _plugin_dir in MIND_GROK_PLUGINS:
        assert f"plugin={name}" in blob or name in argv, (name, blob)
        assert "MIND_PLUGIN_OK" in blob, blob
    loop = MIND_LOOP.read_text(encoding="utf-8")
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "install_mind_grok_plugins" in common
    assert "install_studio_mind_plugin" in loop or "install_mind_grok_plugins" in loop
    assert "plugins/a2a" in common
    assert "plugins/cursor-cloud" in common
    assert "install_seat_cloud_cli" in common
    assert "acp_inject" not in loop
    assert "session/prompt" not in loop
    mind = json.loads((PLUGIN_MIND / "plugin.json").read_text(encoding="utf-8"))
    assert "ticket" in json.dumps(mind).lower() or "ticket" in (
        PLUGIN_MIND / "README.md"
    ).read_text(encoding="utf-8").lower()


def test_scenario_copied_plugins_honor_gcs_root(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_MCP_NDJSON": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    copied_a2a = tmp_path / "copied-a2a"
    copied_cloud = tmp_path / "copied-cloud"
    shutil.copytree(PLUGIN_A2A, copied_a2a)
    shutil.copytree(PLUGIN_CLOUD, copied_cloud)
    a2a_reply = _rpc_plugin(copied_a2a / "server.py", env)
    cloud_reply = _rpc_plugin(copied_cloud / "server.py", env)
    a2a_names = {t["name"] for t in a2a_reply["result"]["tools"]}
    cloud_names = {t["name"] for t in cloud_reply["result"]["tools"]}
    assert "a2a_list_seats" in a2a_names
    assert "a2a_send" in a2a_names
    assert "cloud_launch" in cloud_names
    assert "cloud_status" in cloud_names
    assert "cloud_result" in cloud_names
    for hive_tool in HIVE_CLOUD_TOOLS:
        assert hive_tool in cloud_names, hive_tool
        assert hive_tool not in a2a_names, hive_tool
    a2a_src = (PLUGIN_A2A / "server.py").read_text(encoding="utf-8")
    cloud_src = (PLUGIN_CLOUD / "server.py").read_text(encoding="utf-8")
    for src in (a2a_src, cloud_src):
        assert "GCS_ROOT" in src
        assert "plugin.yaml" not in src


def test_studio_mind_keeps_hive_upgrade_cloud_tools() -> None:
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_MCP_NDJSON": "1",
    }
    reply = _rpc_plugin(PLUGIN_MIND / "server.py", env)
    names = {t["name"] for t in reply["result"]["tools"]}
    assert "ticket" in names
    assert "a2a_send" in names
    assert "a2a_list_seats" in names
    assert "cloud_launch" in names
    for hive_tool in HIVE_CLOUD_TOOLS:
        assert hive_tool in names, hive_tool
    src = MIND_PY.read_text(encoding="utf-8")
    assert "def plugin_cloud_list" in src
    assert "def plugin_cloud_followup" in src
    assert '"cloud_list"' in src
    assert '"cloud_followup"' in src


def test_scenario_copied_hermes_tree_fails_the_ship_gate(tmp_path: Path) -> None:
    assert find_hermes_tree_hits(REPO) == []
    dirty = tmp_path / "kit"
    dirty.mkdir()
    (dirty / ".gitmodules").write_text(
        '[submodule "vendor/hermes-agent"]\n'
        "\tpath = vendor/hermes-agent\n"
        "\turl = https://github.com/NousResearch/hermes-agent.git\n",
        encoding="utf-8",
    )
    tree = dirty / "vendor" / "hermes-agent" / "tools"
    tree.mkdir(parents=True)
    (tree / "plugin.yaml").write_text("name: stolen-hermes\n", encoding="utf-8")
    (tree / "message_agent.py").write_text("# vendored Hermes source\n", encoding="utf-8")
    (tree / "bot_mode_dm.py").write_text("def message_agent():\n    return None\n", encoding="utf-8")
    pkg = dirty / "vendor" / "hermes-agent" / "hermes_agent"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("# hermes_agent package\n", encoding="utf-8")
    (dirty / "vendor" / "hermes-agent" / "pyproject.toml").write_text(
        '[project]\nname = "hermes-agent"\nversion = "0.21.0"\n',
        encoding="utf-8",
    )
    hits = find_hermes_tree_hits(dirty)
    assert hits, "scanner must fail when a Hermes tree is copied into the kit"
    blob = "\n".join(hits)
    assert "hermes-agent" in blob or "plugin.yaml" in blob
    assert any("plugin.yaml" in h for h in hits)
    assert any("message_agent.py" in h for h in hits)
    assert ".gitmodules" in hits

    clean_docs = tmp_path / "docs-only"
    clean_docs.mkdir()
    (clean_docs / "README.md").write_text(
        "Do not vendor NousResearch/hermes-agent. Mail is a turn.\n",
        encoding="utf-8",
    )
    assert find_hermes_tree_hits(clean_docs) == []


def test_repo_has_no_hermes_source_tree() -> None:
    hits = find_hermes_tree_hits(REPO)
    assert hits == [], hits
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert not (REPO / "vendor" / "hermes").exists()
    modules = GITMODULES.read_text(encoding="utf-8")
    assert "hermes-agent" not in modules
    assert "tcarac/taskboard" in modules
    for _name, plugin_dir in MIND_GROK_PLUGINS:
        assert (plugin_dir / "plugin.json").is_file()
        assert not (plugin_dir / "plugin.yaml").is_file()


def test_scenario_mail_is_a_turn_stays_grok_mailbox() -> None:
    src = MIND_PY.read_text(encoding="utf-8")
    loop = MIND_LOOP.read_text(encoding="utf-8")
    hub = HUB_PY.read_text(encoding="utf-8")
    for blob in (src, loop):
        assert "acp_inject" not in blob
        assert "session/prompt" not in blob
        assert "session/new" not in blob
        assert "pin-session" not in blob
        assert "HANDOFF" not in blob
        assert PRIVATE_GAME not in blob
        for banned in BANNED_SPAWN:
            assert banned not in blob
    for marker in HARVEST_MARKERS:
        assert marker not in src, marker
        assert marker not in hub, marker
    assert "--prompt-file" in src
    assert "--resume" in src
    assert "--session-id" in src
    assert "grok-4.6" in src
    assert "xhigh" in src
    assert "TASK_STATE_COMPLETED" in hub
    assert "message_agent" not in src
    assert "plugin.yaml" not in src
    assert "def parse_tool_calls" not in src


def test_docs_name_grok_bot_like_plugins() -> None:
    mind_doc = MIND_DOC.read_text(encoding="utf-8")
    plugins_doc = PLUGINS_DOC.read_text(encoding="utf-8")
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    a2a = A2A_DOC.read_text(encoding="utf-8")
    blob = "\n".join((mind_doc, plugins_doc, agents, a2a))
    low = blob.lower()
    assert "liv63_mind_plugins.feature" in blob
    assert "plugins/a2a" in blob
    assert "plugins/cursor-cloud" in blob
    assert "plugins/studio-mind" in blob
    assert "plugin.json" in blob
    assert "install_mind_grok_plugins" in blob
    assert "do not vendor" in low or "does not vendor" in low or "without vendoring" in low
    assert "hermes-agent" in low
    assert "plugin.yaml" in low
    assert PRIVATE_GAME not in mind_doc
    assert PRIVATE_GAME not in plugins_doc
    assert "session/prompt" in mind_doc
    assert "--prompt-file" in mind_doc
    mind_src = MIND_PY.read_text(encoding="utf-8")
    for marker in HARVEST_MARKERS:
        assert marker not in mind_doc, marker
        assert marker not in mind_src, marker


def test_doctor_lists_grok_plugin_manifests() -> None:
    doctor = (REPO / "doctor.sh").read_text(encoding="utf-8")
    assert "plugins/a2a/plugin.json" in doctor
    assert "plugins/cursor-cloud/plugin.json" in doctor
    assert "plugins/studio-mind/plugin.json" in doctor
