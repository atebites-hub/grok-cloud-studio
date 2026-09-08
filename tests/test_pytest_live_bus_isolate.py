"""Isolated pytest must not hit the live Palemon bus.

Directors leak GCS_ACP_SEATS / GCS_MIND_SEATS / GCS_A2A_STATE /
GCS_A2A_REGISTRY / GCS_TASKBOARD_DB into pytest. Unique remaining vs
origin/main: a required conftest/plugin plus doctor/ship-gate check that
unsets those knobs unless a test opts into a temp state dir, and fails
the suite if it binds live hub port 8732.

Do not start the live bus from tests. Do not bounce leftover dispatch.
Do not clone LIV-67 runStatus printers, LIV-41 occupancy, or LIV-85
mail.txt / hub COMPLETE siblings. Never Bot CloudAgent. Living Sky only.
Never vendor Hermes. Never merge GCS #26/#28. Never Black Swan.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

import gcs_pytest_isolate as iso

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "scripts" / "gcs_pytest_isolate.py"
CONFTEST = REPO / "tests" / "conftest.py"
PYTEST_INI = REPO / "pytest.ini"
SHIP_GATE = REPO / "scripts" / "ci" / "ship-gate.sh"
DOCTOR = REPO / "doctor.sh"
DOCS = REPO / "docs" / "studio" / "PYTEST.md"
FEATURE = REPO / "tests" / "features" / "pytest_live_bus_isolate.feature"
AGENTS = REPO / "AGENTS.md"
README = REPO / "README.md"
HUB = REPO / "scripts" / "a2a" / "hub.py"
START_TB = REPO / "scripts" / "studio" / "taskboard" / "start-taskboard.sh"
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"

LEAK_VARS = (
    "GCS_ACP_SEATS",
    "GCS_MIND_SEATS",
    "GCS_A2A_STATE",
    "GCS_A2A_REGISTRY",
    "GCS_TASKBOARD_DB",
)
ALIAS_LEAK_VARS = ("PALEMON_A2A_STATE", "TASKBOARD_DB")
LIVE_HUB_PORT = 8732
LIVE_STATE = "/workspace/" + "palemon" + "/.a2a-state"
LIVE_DB = LIVE_STATE + "/taskboard/taskboard.db"
BLACK_SWAN = "blackswan" + ".money"
PRIVATE_GAME = "atebites-hub/" + "palemon"


def _load() -> ModuleType:
    assert PLUGIN.is_file(), f"missing {PLUGIN}"
    spec = importlib.util.spec_from_file_location("gcs_pytest_isolate_under_test", PLUGIN)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_feature_file_is_the_living_spec() -> None:
    assert FEATURE.is_file(), "missing tests/features/pytest_live_bus_isolate.feature"
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert "Feature:" in text
    assert "8732" in text
    for var in LEAK_VARS:
        assert var in text
    assert "gcs_temp_state" in text or "temp state" in fold
    assert "ship-gate" in fold
    assert "doctor" in fold
    assert "bot cloudagent" in fold
    assert "living sky" in fold
    assert "do not start the live bus" in fold or "do not start" in fold
    assert "leftover dispatch" in fold
    assert PRIVATE_GAME not in text
    assert "Scenario:" in text
    assert "Given " in text and "When " in text and "Then " in text


def test_plugin_and_conftest_and_docs_exist() -> None:
    assert PLUGIN.is_file(), "missing scripts/gcs_pytest_isolate.py"
    assert CONFTEST.is_file(), "missing tests/conftest.py"
    assert DOCS.is_file(), "missing docs/studio/PYTEST.md"
    src = PLUGIN.read_text(encoding="utf-8")
    assert "start-studio-bus.sh start" not in src
    assert "hermes-agent" not in src.lower()
    assert BLACK_SWAN not in src.lower()
    assert PRIVATE_GAME not in src


def test_pytest_ini_requires_isolate_plugin_without_quiet() -> None:
    text = PYTEST_INI.read_text(encoding="utf-8")
    assert "pythonpath = scripts" in text or "pythonpath=scripts" in text.replace(" ", "")
    assert "-p gcs_pytest_isolate" in text
    addopts = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("addopts"):
            addopts = stripped.split("=", 1)[-1]
    assert "-p gcs_pytest_isolate" in addopts
    assert "-q" not in addopts
    assert "-qq" not in addopts
    assert "--override-ini" not in text


def test_conftest_loads_required_plugin() -> None:
    text = CONFTEST.read_text(encoding="utf-8")
    assert "pytest_plugins" in text
    assert "gcs_pytest_isolate" in text


def test_ship_gate_unsets_leak_vars_before_pytest() -> None:
    text = SHIP_GATE.read_text(encoding="utf-8")
    for var in LEAK_VARS:
        assert var in text, var
    unset_idx = text.find("unset GCS_ACP_SEATS")
    pytest_idx = text.find('pytest_out="$(.venv/bin/pytest -q')
    assert unset_idx != -1
    assert pytest_idx != -1
    assert unset_idx < pytest_idx
    assert "--override-ini" not in text
    assert "launch-cloud-extra-high" not in text
    assert "Bot CloudAgent" not in text
    assert "start-studio-bus.sh start" not in text


def test_doctor_lists_plugin_and_runs_check() -> None:
    text = DOCTOR.read_text(encoding="utf-8")
    assert "gcs_pytest_isolate" in text
    assert "scripts/gcs_pytest_isolate.py" in text
    assert "--check" in text
    assert "docs/studio/PYTEST.md" in text
    assert "tests/conftest.py" in text


def test_docs_studio_note_names_the_contract() -> None:
    text = DOCS.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    for var in LEAK_VARS:
        assert var in text
    assert "8732" in text
    assert "gcs_temp_state" in text
    assert "gcs_pytest_isolate" in text
    assert "ship-gate" in fold
    assert "doctor" in fold
    assert "living sky" in fold
    assert "bot cloudagent" in fold
    assert "hermes" not in fold or "never vendor" in fold or "do not vendor" in fold
    assert BLACK_SWAN not in fold
    assert PRIVATE_GAME not in text
    assert "mail.txt" not in text
    assert "MUST_LAUNCH" not in text
    assert "runStatus" not in text


def test_agents_and_readme_point_at_pytest_isolation() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert "docs/studio/PYTEST.md" in agents or "gcs_pytest_isolate" in agents
    assert "docs/studio/PYTEST.md" in readme
    assert ".venv/bin/pytest -q" in agents
    assert ".venv/bin/pytest -q" in readme


def test_strip_removes_leaks_and_aliases_keeps_unrelated() -> None:
    mod = _load()
    env = {
        "GCS_ACP_SEATS": "floor,studio-ops",
        "GCS_MIND_SEATS": "floor,ops",
        "GCS_A2A_STATE": LIVE_STATE,
        "GCS_A2A_REGISTRY": "/tmp/reg.json",
        "GCS_TASKBOARD_DB": LIVE_DB,
        "PALEMON_A2A_STATE": LIVE_STATE,
        "TASKBOARD_DB": LIVE_DB,
        "PATH": "/usr/bin:/bin",
        "GCS_CLOUD_REPO": "https://github.com/example/control-plane",
        "GCS_BOT_BIND_OPTIONAL": "1",
    }
    out = mod.strip_live_studio_env(env)
    for key in LEAK_VARS + ALIAS_LEAK_VARS:
        assert key not in out, key
    assert out["PATH"] == "/usr/bin:/bin"
    assert out["GCS_CLOUD_REPO"] == "https://github.com/example/control-plane"
    assert "GCS_A2A_STATE" in env
    assert env["GCS_A2A_STATE"] == LIVE_STATE


def test_looks_like_live_palemon_state_and_db() -> None:
    mod = _load()
    assert mod.looks_like_live_palemon_state(LIVE_STATE) is True
    assert mod.looks_like_live_palemon_state(LIVE_STATE + "/") is True
    assert mod.looks_like_live_palemon_db(LIVE_DB) is True
    assert mod.looks_like_live_palemon_state("/tmp/pytest-of-ci/a2a-state") is False
    assert mod.looks_like_live_palemon_db("/tmp/pytest-of-ci/taskboard.db") is False
    assert mod.looks_like_live_palemon_state("") is False


def test_live_looking_env_cannot_launch_real_hub() -> None:
    mod = _load()
    env = {
        "GCS_A2A_STATE": LIVE_STATE,
        "GCS_A2A_PORT": str(LIVE_HUB_PORT),
        "PATH": "/usr/bin:/bin",
    }
    with pytest.raises(mod.LiveHubBindError):
        mod.refuse_live_studio_launch(["python3", str(HUB)], env)


def test_live_looking_env_cannot_launch_real_taskboard() -> None:
    mod = _load()
    env = {
        "GCS_A2A_STATE": LIVE_STATE,
        "GCS_TASKBOARD_DB": LIVE_DB,
        "PATH": "/usr/bin:/bin",
    }
    with pytest.raises(mod.LiveStudioStateError):
        mod.refuse_live_studio_launch(["bash", str(START_TB), "start"], env)


def test_temp_state_still_cannot_bind_live_hub_port() -> None:
    mod = _load()
    env = {
        "GCS_A2A_STATE": "/tmp/gcs-pytest-state",
        "GCS_A2A_PORT": str(LIVE_HUB_PORT),
        "PATH": "/usr/bin:/bin",
    }
    with pytest.raises(mod.LiveHubBindError):
        mod.refuse_live_studio_launch(["python3", str(HUB)], env)


def test_temp_state_ephemeral_hub_port_is_allowed() -> None:
    mod = _load()
    env = {
        "GCS_A2A_STATE": "/tmp/gcs-pytest-state",
        "GCS_A2A_PORT": "59991",
        "PATH": "/usr/bin:/bin",
    }
    mod.refuse_live_studio_launch(["python3", str(HUB)], env)


def test_bus_help_and_lib_cli_are_not_refused() -> None:
    mod = _load()
    env = {"GCS_A2A_STATE": LIVE_STATE, "GCS_A2A_PORT": str(LIVE_HUB_PORT)}
    mod.refuse_live_studio_launch(["bash", str(BUS), "--help"], env)
    mod.refuse_live_studio_launch(
        ["python3", str(REPO / "scripts" / "a2a" / "lib.py"), "launch-seats"],
        env,
    )
    mod.refuse_live_studio_launch(["bash", str(START_TB), "stop"], env)


def test_bus_start_on_live_port_is_refused() -> None:
    mod = _load()
    env = {
        "GCS_A2A_STATE": "/tmp/gcs-pytest-state",
        "GCS_A2A_PORT": str(LIVE_HUB_PORT),
    }
    with pytest.raises(mod.LiveHubBindError):
        mod.refuse_live_studio_launch(["bash", str(BUS), "start"], env)


def test_suite_env_has_leak_vars_unset() -> None:
    for key in LEAK_VARS + ALIAS_LEAK_VARS:
        assert key not in os.environ, f"{key} leaked into isolated pytest"


def test_gcs_temp_state_opt_in_is_tmp_not_live(gcs_temp_state: Path) -> None:
    assert gcs_temp_state.is_dir()
    assert os.environ.get("GCS_A2A_STATE") == str(gcs_temp_state)
    db = os.environ.get("GCS_TASKBOARD_DB", "")
    assert db.startswith(str(gcs_temp_state))
    assert "palemon/.a2a-state" not in str(gcs_temp_state)
    assert "GCS_ACP_SEATS" not in os.environ
    assert "GCS_MIND_SEATS" not in os.environ
    assert "GCS_A2A_REGISTRY" not in os.environ


def test_pytest_process_refuses_bind_of_live_hub_port() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(iso.LiveHubBindError):
            sock.bind(("127.0.0.1", LIVE_HUB_PORT))
    finally:
        sock.close()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ephemeral:
        ephemeral.bind(("127.0.0.1", 0))
        assert int(ephemeral.getsockname()[1]) != LIVE_HUB_PORT


def test_plugin_strips_leaked_parent_env_in_nested_pytest(tmp_path: Path) -> None:
    probe = tmp_path / "test_probe_live_env_stripped.py"
    probe.write_text(
        "import os\n"
        "LEAK = ("
        "'GCS_ACP_SEATS', 'GCS_MIND_SEATS', 'GCS_A2A_STATE', "
        "'GCS_A2A_REGISTRY', 'GCS_TASKBOARD_DB', "
        "'PALEMON_A2A_STATE', 'TASKBOARD_DB')\n"
        "def test_leaks_unset():\n"
        "    leaked = [key for key in LEAK if key in os.environ]\n"
        "    assert leaked == []\n",
        encoding="utf-8",
    )
    keep = (
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TERM",
        "USER",
        "LOGNAME",
        "TMPDIR",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONNOUSERSITE",
    )
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update(
        {
            "GCS_ACP_SEATS": "floor,studio-ops",
            "GCS_MIND_SEATS": "floor,ops",
            "GCS_A2A_STATE": LIVE_STATE,
            "GCS_A2A_REGISTRY": str(REPO / "docs" / "a2a" / "registry.json"),
            "GCS_TASKBOARD_DB": LIVE_DB,
            "PALEMON_A2A_STATE": LIVE_STATE,
            "TASKBOARD_DB": LIVE_DB,
            "PYTHONDONTWRITEBYTECODE": "1",
            "GCS_BOT_BIND_OPTIONAL": "1",
            "HOME": str(tmp_path / "home"),
        }
    )
    env["PYTHONPATH"] = str(REPO / "scripts")
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "gcs_pytest_isolate",
            str(probe),
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "passed" in proc.stdout


def test_isolate_check_fails_when_wiring_missing(tmp_path: Path) -> None:
    mod = _load()
    root = tmp_path / "kit"
    (root / "scripts" / "ci").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "docs" / "studio").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (root / "scripts" / "ci" / "ship-gate.sh").write_text(
        "#!/bin/bash\n.venv/bin/pytest -q\n",
        encoding="utf-8",
    )
    rc = mod.check_isolation_wiring(root)
    assert rc != 0


def test_isolate_check_passes_on_this_tree() -> None:
    mod = _load()
    assert mod.check_isolation_wiring(REPO) == 0


def test_isolate_cli_check_exits_nonzero_on_bare_tree(tmp_path: Path) -> None:
    root = tmp_path / "kit"
    (root / "scripts" / "ci").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "docs" / "studio").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (root / "scripts" / "ci" / "ship-gate.sh").write_text(
        "#!/bin/bash\n.venv/bin/pytest -q\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(PLUGIN), "--check", "--root", str(root)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "gcs_pytest_isolate" in blob or "isolation" in blob.lower()


def test_doctor_fails_when_isolate_plugin_missing(tmp_path: Path) -> None:
    kit = tmp_path / "kit"
    kit.mkdir()
    plugin = kit / "scripts" / "gcs_pytest_isolate.py"
    plugin.parent.mkdir(parents=True)
    plugin.write_text(PLUGIN.read_text(encoding="utf-8"), encoding="utf-8")
    doctor = kit / "doctor.sh"
    _write_exec(
        doctor,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'python3 "$ROOT/scripts/gcs_pytest_isolate.py" --check --root "$ROOT"\n',
    )
    (kit / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (kit / "scripts" / "ci").mkdir(parents=True, exist_ok=True)
    (kit / "scripts" / "ci" / "ship-gate.sh").write_text(
        "#!/bin/bash\nunset GCS_A2A_STATE\n.venv/bin/pytest -q\n",
        encoding="utf-8",
    )
    (kit / "tests").mkdir()
    (kit / "docs" / "studio").mkdir(parents=True)
    proc = subprocess.run(
        ["bash", str(doctor)],
        cwd=str(kit),
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path / "home"),
            "LC_ALL": "C",
            "TERM": "dumb",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode != 0
    blob = proc.stdout + proc.stderr
    assert "isolation" in blob.lower() or "gcs_pytest_isolate" in blob or "pytest.ini" in blob
