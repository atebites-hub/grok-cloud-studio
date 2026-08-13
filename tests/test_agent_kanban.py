"""Agent Kanban sync-only bridge: fleet.jsonl → ak apply, no secrets, no ak start."""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts" / "studio" / "agent-kanban" / "install-ak.sh"
CONFIGURE = ROOT / "scripts" / "studio" / "agent-kanban" / "configure-ak.sh"
BOOTSTRAP = ROOT / "scripts" / "studio" / "agent-kanban" / "bootstrap-board.sh"
BRIDGE = ROOT / "scripts" / "studio" / "agent-kanban" / "fleet-bridge.py"
BUS = ROOT / "scripts" / "a2a" / "start-studio-bus.sh"
DOCS = ROOT / "docs" / "studio" / "AGENT_KANBAN.md"
DASHBOARD = ROOT / "scripts" / "studio" / "dashboard" / "README.md"
FAKE_KEY = "test-ak-key-not-a-secret"


def _env(home: Path, state: Path, **extra: str) -> dict[str, str]:
    env = {
        "PATH": f"{home / 'bin'}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(home),
        "TMPDIR": str(home),
        "GCS_ROOT": str(ROOT),
        "GCS_A2A_STATE": str(state),
        "LC_ALL": "C",
        "AGENT_KANBAN_BOARD_NAME": "Studio Mission Control",
        "AGENT_KANBAN_API_URL": "https://agent-kanban.dev",
    }
    env.update(extra)
    return env


def _write_exec(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _fake_ak(home: Path, *, boards: str = "[]", apply_msg: str = "Created task tsk-1: demo") -> Path:
    log = home / "ak.argv"
    ak = home / "bin" / "ak"
    _write_exec(
        ak,
        f"""#!/usr/bin/env bash
set -euo pipefail
log={json.dumps(str(log))}
printf '%s\\n' "$0 $*" >>"$log"
cmd="${{1:-}}"
shift || true
case "$cmd" in
  config)
    echo "Saved credentials for agent-kanban.dev"
    ;;
  get)
    if [[ "${{1:-}}" == "board" ]]; then
      cat <<'JSON'
{boards}
JSON
    else
      echo "[]"
    fi
    ;;
  create)
    if [[ "${{1:-}}" == "board" ]]; then
      echo "Created board brd-new: Studio Mission Control"
    elif [[ "${{1:-}}" == "repo" ]]; then
      echo "Added repository repo-1: product"
    else
      echo "created"
    fi
    ;;
  apply)
    echo {json.dumps(apply_msg)}
    ;;
  start)
    echo "AK_START_CALLED" >&2
    exit 3
    ;;
  *)
    echo "ak-fake unknown $cmd" >&2
    exit 2
    ;;
esac
""",
    )
    return log


def _run(script: Path, env: dict[str, str], args: list[str] | None = None, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    cmd = ["bash", str(script), *(args or [])]
    if script.suffix == ".py":
        cmd = ["python3", str(script), *(args or [])]
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def test_docs_cover_aliases_sync_only_and_fsl() -> None:
    text = DOCS.read_text(encoding="utf-8")
    assert "GCS_AGENT_KANBAN_API_KEY" in text
    assert "GCS_AGENT_KANBAN_API_URL" in text
    assert "AGENT_KANBAN_API_KEY" in text
    assert "sync-only" in text.lower() or "sync only" in text.lower()
    assert "ak start" in text.lower()
    assert "FSL" in text
    assert "https://agent-kanban.dev" in text
    assert "github.com/saltbo/agent-kanban" in text
    assert "studio mission control" in text.lower()
    assert "scripts/studio/dashboard" in text


def test_legacy_dashboard_points_at_agent_kanban_docs() -> None:
    text = DASHBOARD.read_text(encoding="utf-8")
    assert "LEGACY" in text
    assert "docs/studio/AGENT_KANBAN.md" in text


def test_install_ak_exits_zero_when_ak_present(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    log = _fake_ak(home)
    npm_log = home / "npm.log"
    _write_exec(
        home / "bin" / "npm",
        f"#!/usr/bin/env bash\necho npm \"$@\" >>{json.dumps(str(npm_log))}\nexit 1\n",
    )
    proc = _run(INSTALL, _env(home, state))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not npm_log.exists()
    argv = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert "start" not in argv


def test_configure_ak_uses_gcs_alias_and_omits_key_from_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    _fake_ak(home, boards='[{"id":"brd-studio","name":"Studio Mission Control"}]')
    env = _env(home, state, GCS_AGENT_KANBAN_API_KEY=FAKE_KEY)
    proc = _run(CONFIGURE, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    configured = state / "agent-kanban" / "configured"
    body = configured.read_text(encoding="utf-8")
    assert "api-url=" in body
    assert "ts=" in body
    assert FAKE_KEY not in body
    assert FAKE_KEY not in proc.stdout
    assert FAKE_KEY not in proc.stderr
    argv = (home / "ak.argv").read_text(encoding="utf-8")
    assert "config set" in argv
    assert "get board" in argv
    assert "start" not in argv


def test_configure_ak_reads_connector_secrets_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    secrets = state / "agent-kanban" / "connector-secrets.json"
    secrets.parent.mkdir(parents=True, exist_ok=True)
    secrets.write_text(json.dumps({"api_key": FAKE_KEY, "api_url": "https://agent-kanban.dev"}), encoding="utf-8")
    _fake_ak(home, boards="[]")
    proc = _run(CONFIGURE, _env(home, state))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    argv = (home / "ak.argv").read_text(encoding="utf-8")
    assert "config set" in argv
    assert FAKE_KEY not in proc.stdout + proc.stderr
    assert FAKE_KEY not in (state / "agent-kanban" / "configured").read_text(encoding="utf-8")


def test_bootstrap_board_reuses_existing_and_prints_board_url(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    boards = json.dumps(
        [{"id": "brd-studio", "name": "Studio Mission Control", "url": "https://agent-kanban.dev/b/brd-studio"}]
    )
    _fake_ak(home, boards=boards)
    proc = _run(BOOTSTRAP, _env(home, state))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (state / "agent-kanban" / "board.id").read_text(encoding="utf-8").strip() == "brd-studio"
    assert "BOARD_URL=" in proc.stdout
    argv = (home / "ak.argv").read_text(encoding="utf-8")
    assert "create board" not in argv
    assert "start" not in argv


def test_bootstrap_board_creates_when_missing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    _fake_ak(home, boards="[]")
    proc = _run(BOOTSTRAP, _env(home, state))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (state / "agent-kanban" / "board.id").read_text(encoding="utf-8").strip() == "brd-new"
    argv = (home / "ak.argv").read_text(encoding="utf-8")
    assert "create board" in argv
    assert "--type ops" in argv


def test_fleet_bridge_applies_task_yaml_and_writes_task_map(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    seat = state / "ops"
    seat.mkdir(parents=True)
    (seat / "fleet.jsonl").write_text(
        json.dumps(
            {
                "bc_id": "bc-aaa",
                "seat": "ops",
                "name": "demo-run",
                "status": "open",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ak_dir = state / "agent-kanban"
    ak_dir.mkdir(parents=True)
    (ak_dir / "board.id").write_text("brd-studio\n", encoding="utf-8")
    log = _fake_ak(home)
    env = _env(home, state, GCS_CLOUD_REPO="https://github.com/example/control-plane")
    proc = _run(BRIDGE, env, args=["--once"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "AK_BRIDGE_" in proc.stdout
    assert FAKE_KEY not in proc.stdout + proc.stderr
    argv = log.read_text(encoding="utf-8")
    assert "apply -f" in argv
    assert "start" not in argv
    task_map = json.loads((ak_dir / "task-map.json").read_text(encoding="utf-8"))
    assert task_map["ops:bc-aaa"]["task_id"] == "tsk-1"


def test_fleet_bridge_skips_unchanged_and_updates_on_status_change(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    seat = state / "ops"
    seat.mkdir(parents=True)
    row = {"bc_id": "bc-aaa", "seat": "ops", "name": "demo-run", "status": "open"}
    (seat / "fleet.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    ak_dir = state / "agent-kanban"
    ak_dir.mkdir(parents=True)
    (ak_dir / "board.id").write_text("brd-studio\n", encoding="utf-8")
    log = _fake_ak(home, apply_msg="Created task tsk-1: demo")
    env = _env(home, state)
    first = _run(BRIDGE, env, args=["--once"])
    assert first.returncode == 0, first.stdout + first.stderr
    second = _run(BRIDGE, env, args=["--once"])
    assert second.returncode == 0, second.stdout + second.stderr
    assert "AK_BRIDGE_SKIP" in second.stdout
    applies = [ln for ln in log.read_text(encoding="utf-8").splitlines() if " apply " in ln]
    assert len(applies) == 1
    row["status"] = "closed"
    row["notified_by"] = "waiter"
    (seat / "fleet.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    _fake_ak(home, apply_msg="Updated task tsk-1: demo")
    third = _run(BRIDGE, env, args=["--once"])
    assert third.returncode == 0, third.stdout + third.stderr
    applies = [ln for ln in log.read_text(encoding="utf-8").splitlines() if " apply " in ln]
    assert len(applies) == 2
    yaml_text = (ak_dir / "apply-task.yaml").read_text(encoding="utf-8")
    assert "id:" in yaml_text
    assert "tsk-1" in yaml_text


def test_fleet_bridge_stays_under_250_lines() -> None:
    lines = BRIDGE.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 250


def test_bus_script_optional_ak_bridge_hooks() -> None:
    text = BUS.read_text(encoding="utf-8")
    assert "ak-bridge" in text
    assert "AGENT_KANBAN_API_KEY" in text
    assert "GCS_AGENT_KANBAN_API_KEY" in text
    assert "STUDIO_BUS_AK_BRIDGE" in text
