"""GitHub Actions ship gate: pytest -q AND secret_scan.

PRs must not land on leftover-green `--override-ini` or a plan with no
`N passed`. Does not remint secret_scan mcp.json (#56) or doctor.sh (#51).
Never launches Bot CloudAgent.
"""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ship-gate.yml"
SHIP_GATE = REPO / "scripts" / "ci" / "ship-gate.sh"
INSTALL = REPO / "install.sh"
AGENTS = REPO / "AGENTS.md"
README = REPO / "README.md"
DOCTOR = REPO / "doctor.sh"
MCP_JSON = REPO / ".cursor" / "mcp.json"
SECRET_SCAN = REPO / "scripts" / "secret_scan.py"

PYTEST_CMD = ".venv/bin/pytest -q"
SCAN_CMD = "python3 scripts/secret_scan.py"
BLACK_SWAN = "blackswan" + ".money"


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _run_ship_gate(
    tree: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tree / "home"),
        "GCS_ROOT": str(tree),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SHIP_GATE)],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _gate_tree(
    tmp_path: Path,
    *,
    pytest_script: str,
    scan_script: str,
) -> Path:
    tree = tmp_path / "kit"
    _write_exec(tree / ".venv" / "bin" / "pytest", pytest_script)
    scan = tree / "scripts" / "secret_scan.py"
    scan.parent.mkdir(parents=True, exist_ok=True)
    scan.write_text(scan_script, encoding="utf-8")
    (tree / "home").mkdir(parents=True, exist_ok=True)
    return tree


def test_github_actions_workflow_exists() -> None:
    assert WORKFLOW.is_file(), "missing .github/workflows/ship-gate.yml"


def test_workflow_runs_on_pull_request() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request" in text
    assert "ubuntu-latest" in text


def test_workflow_bootstraps_venv_then_runs_canonical_gate() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "./install.sh" in text or "bash install.sh" in text or "bash ./install.sh" in text
    assert "scripts/ci/ship-gate.sh" in text
    assert "GCS_BOT_BIND_OPTIONAL" in text


def test_workflow_is_not_leftover_green_override_ini() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--override-ini" not in text
    assert "continue-on-error" not in text


def test_workflow_does_not_launch_bot_cloudagent() -> None:
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    assert "launch-cloud-extra-high" not in text
    assert "bot cloudagent" not in text
    assert "cursor.com/agents" not in text
    assert "cloud_launch" not in text


def test_workflow_linear_is_not_black_swan() -> None:
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    assert BLACK_SWAN not in text
    assert "black swan" not in text


def test_ship_gate_script_exists_and_is_bash() -> None:
    assert SHIP_GATE.is_file(), "missing scripts/ci/ship-gate.sh"
    text = SHIP_GATE.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert PYTEST_CMD in text
    assert SCAN_CMD in text or "scripts/secret_scan.py" in text


def test_ship_gate_script_invokes_exact_pytest_q_not_override_ini() -> None:
    text = SHIP_GATE.read_text(encoding="utf-8")
    assert PYTEST_CMD in text
    assert "--override-ini" not in text
    assert "launch-cloud-extra-high" not in text
    assert "Bot CloudAgent" not in text
    assert BLACK_SWAN not in text.lower()


def test_ship_gate_requires_n_passed(tmp_path: Path) -> None:
    tree = _gate_tree(
        tmp_path,
        pytest_script=(
            "#!/bin/sh\n"
            "printf 'no tests ran in 0.01s\\n'\n"
            "exit 0\n"
        ),
        scan_script="print('secret_scan=clean')\n",
    )
    proc = _run_ship_gate(tree)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "passed" in combined.lower() or "ship-gate" in combined.lower()


def test_ship_gate_fails_when_pytest_fails(tmp_path: Path) -> None:
    tree = _gate_tree(
        tmp_path,
        pytest_script=(
            "#!/bin/sh\n"
            "printf '1 failed, 0 passed in 0.01s\\n'\n"
            "exit 1\n"
        ),
        scan_script="print('secret_scan=clean')\n",
    )
    proc = _run_ship_gate(tree)
    assert proc.returncode != 0


def test_ship_gate_fails_when_secret_scan_fails(tmp_path: Path) -> None:
    tree = _gate_tree(
        tmp_path,
        pytest_script=(
            "#!/bin/sh\n"
            "printf '3 passed in 0.01s\\n'\n"
            "exit 0\n"
        ),
        scan_script=(
            "import sys\n"
            "print('secret_scan=FAIL')\n"
            "raise SystemExit(1)\n"
        ),
    )
    proc = _run_ship_gate(tree)
    assert proc.returncode != 0


def test_ship_gate_ok_when_pytest_passes_and_scan_clean(tmp_path: Path) -> None:
    tree = _gate_tree(
        tmp_path,
        pytest_script=(
            "#!/bin/sh\n"
            "printf '3 passed in 0.01s\\n'\n"
            "exit 0\n"
        ),
        scan_script="print('secret_scan=clean')\n",
    )
    proc = _run_ship_gate(tree)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "3 passed" in combined
    assert "secret_scan=clean" in combined
    assert "ship-gate: OK" in combined


def test_ship_gate_does_not_run_scan_when_pytest_has_zero_passed(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "scan-ran"
    tree = _gate_tree(
        tmp_path,
        pytest_script=(
            "#!/bin/sh\n"
            "printf '0 passed in 0.01s\\n'\n"
            "exit 0\n"
        ),
        scan_script=(
            f"from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
            "print('secret_scan=clean')\n"
        ),
    )
    proc = _run_ship_gate(tree)
    assert proc.returncode != 0
    assert not marker.is_file()


def test_docs_name_the_two_ship_gate_commands() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert PYTEST_CMD in agents
    assert SCAN_CMD in agents
    assert PYTEST_CMD in readme
    assert SCAN_CMD in readme
    assert "ship-gate.yml" in readme or ".github/workflows" in readme


def test_this_pr_does_not_remint_doctor_or_mcp_json() -> None:
    """#51 owns doctor launch-plane; #56 owns mcp.json LINEAR literals."""
    doctor = DOCTOR.read_text(encoding="utf-8")
    mcp = MCP_JSON.read_text(encoding="utf-8")
    scan = SECRET_SCAN.read_text(encoding="utf-8")
    gate = SHIP_GATE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for blob in (gate, workflow):
        assert "LINEAR_API_KEY" not in blob
        assert "doctor.sh" not in blob or "remint" in blob.lower()
    assert "scripts/secret_scan.py" in doctor
    assert "mcpServers" in mcp
    assert "BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY" in scan


def test_install_chmods_ship_gate_script() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    assert "scripts/ci" in text
    assert "chmod +x" in text


def test_pytest_ini_does_not_double_quiet_the_ship_gate() -> None:
    """pytest 9: addopts=-q plus CLI -q is -qq and hides 'N passed'."""
    text = (REPO / "pytest.ini").read_text(encoding="utf-8")
    addopts = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("addopts"):
            addopts = stripped.split("=", 1)[-1]
    assert "-q" not in addopts
    assert "-qq" not in addopts
