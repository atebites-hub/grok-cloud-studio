"""Required pytest plugin: isolated tests must not hit the live Palemon bus.

Directors leak GCS_ACP_SEATS, GCS_MIND_SEATS, GCS_A2A_STATE,
GCS_A2A_REGISTRY, and GCS_TASKBOARD_DB into pytest. The live studio hub
holds 127.0.0.1:8732. This plugin unsets those knobs (plus PALEMON_A2A_STATE
/ TASKBOARD_DB aliases) unless a test opts into the gcs_temp_state fixture,
refuses launching hub/taskboard/bus against live Palemon paths, and fails
the suite if a test binds the live hub port.

Do not start the live bus from tests. Do not bounce leftover dispatch.
Never Bot CloudAgent. Living Sky only. See docs/studio/PYTEST.md.
"""
from __future__ import annotations

import argparse
import os
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

LEAK_VARS: tuple[str, ...] = (
    "GCS_ACP_SEATS",
    "GCS_MIND_SEATS",
    "GCS_A2A_STATE",
    "GCS_A2A_REGISTRY",
    "GCS_TASKBOARD_DB",
)
ALIAS_LEAK_VARS: tuple[str, ...] = (
    "PALEMON_A2A_STATE",
    "TASKBOARD_DB",
)
STRIP_VARS: tuple[str, ...] = LEAK_VARS + ALIAS_LEAK_VARS
LIVE_HUB_PORT = 8732
_LIVE_STATE_TAIL = "/" + "palemon" + "/.a2a-state"

_CONFIGURED = False
_ORIG_BIND = socket.socket.bind
_ORIG_POPEN = subprocess.Popen


class LiveHubBindError(RuntimeError):
    """Isolated pytest refused the live Palemon hub port."""


class LiveStudioStateError(RuntimeError):
    """Isolated pytest refused the live Palemon state dir or taskboard DB."""


def strip_live_studio_env(env: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of env without live Palemon leak variables."""
    return {key: value for key, value in env.items() if key not in STRIP_VARS}


def looks_like_live_palemon_state(path: str | None) -> bool:
    """True when path is the recovered Palemon live state dir."""
    if not path:
        return False
    normalized = str(path).replace("\\", "/").rstrip("/")
    return normalized.endswith(_LIVE_STATE_TAIL)


def looks_like_live_palemon_db(path: str | None) -> bool:
    """True when path is SQLite under the recovered Palemon live state dir."""
    if not path:
        return False
    normalized = str(path).replace("\\", "/")
    marker = _LIVE_STATE_TAIL + "/taskboard/"
    return marker in normalized or looks_like_live_palemon_state(normalized)


def _argv_parts(argv: str | bytes | Sequence[Any] | None) -> list[str]:
    if argv is None:
        return []
    if isinstance(argv, bytes):
        argv = argv.decode()
    if isinstance(argv, str):
        return shlex.split(argv)
    return [str(part) for part in argv]


def _is_help_or_lifecycle(parts: list[str]) -> bool:
    return any(part in {"--help", "-h", "stop", "status"} for part in parts)


def is_studio_server_argv(argv: str | bytes | Sequence[Any] | None) -> bool:
    """True when argv would start hub, studio bus, or host taskboard/MCP HTTP."""
    parts = _argv_parts(argv)
    if not parts:
        return False
    blob = " ".join(parts)
    if "hub.py" in blob:
        return True
    if "mcp_http_gateway.py" in blob:
        return not _is_help_or_lifecycle(parts)
    if "start-studio-bus.sh" in blob:
        return not _is_help_or_lifecycle(parts)
    if "start-taskboard.sh" in blob:
        return not _is_help_or_lifecycle(parts)
    if "mcp-http.sh" in blob:
        return not _is_help_or_lifecycle(parts)
    return False


def _is_hub_or_bus_argv(parts: list[str]) -> bool:
    blob = " ".join(parts)
    return "hub.py" in blob or "start-studio-bus.sh" in blob


def _db_from_argv_or_env(parts: list[str], env: Mapping[str, str]) -> str:
    if "--db" in parts:
        index = parts.index("--db")
        if index + 1 < len(parts):
            return parts[index + 1]
    return env.get("GCS_TASKBOARD_DB") or env.get("TASKBOARD_DB") or ""


def _port_from_address(address: object) -> int | None:
    if isinstance(address, tuple) and len(address) >= 2:
        try:
            return int(address[1])
        except (TypeError, ValueError):
            return None
    return None


def refuse_live_hub_bind(host: str, port: int) -> None:
    """Raise if a caller would bind the live Palemon hub port."""
    del host
    if int(port) == LIVE_HUB_PORT:
        raise LiveHubBindError(
            f"isolated pytest must not bind live Palemon hub port {LIVE_HUB_PORT}"
        )


def refuse_live_studio_launch(
    argv: str | bytes | Sequence[Any] | None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Refuse hub/bus/taskboard launches that would open the live Palemon studio."""
    if not is_studio_server_argv(argv):
        return
    parts = _argv_parts(argv)
    if env is None:
        merged = {key: str(value) for key, value in os.environ.items()}
    else:
        merged = {
            str(key): str(value) for key, value in env.items() if value is not None
        }
    if _is_hub_or_bus_argv(parts):
        raw_port = merged.get("GCS_A2A_PORT") or str(LIVE_HUB_PORT)
        try:
            port = int(raw_port)
        except ValueError:
            port = LIVE_HUB_PORT
        if port == LIVE_HUB_PORT:
            raise LiveHubBindError(
                f"isolated pytest must not launch hub/bus on live port {LIVE_HUB_PORT}"
            )
    state = merged.get("GCS_A2A_STATE") or merged.get("PALEMON_A2A_STATE") or ""
    db = _db_from_argv_or_env(parts, merged)
    if looks_like_live_palemon_state(state) or looks_like_live_palemon_db(db):
        raise LiveStudioStateError(
            "isolated pytest must not open the live Palemon state dir or taskboard DB"
        )


def apply_live_studio_env_strip() -> None:
    """Unset leak variables on the current process."""
    for key in STRIP_VARS:
        os.environ.pop(key, None)


def _guarded_bind(self: socket.socket, address: object) -> None:
    port = _port_from_address(address)
    if port == LIVE_HUB_PORT:
        raise LiveHubBindError(
            f"isolated pytest must not bind live Palemon hub port {LIVE_HUB_PORT}"
        )
    return _ORIG_BIND(self, address)


def _guarded_popen(args: Any, *extra: Any, **kwargs: Any) -> subprocess.Popen[Any]:
    refuse_live_studio_launch(args, kwargs.get("env"))
    return _ORIG_POPEN(args, *extra, **kwargs)


def install_isolation_guards() -> None:
    """Install bind + Popen guards. Idempotent."""
    socket.socket.bind = _guarded_bind  # type: ignore[method-assign]
    subprocess.Popen = _guarded_popen  # type: ignore[misc, assignment]


def check_isolation_wiring(root: Path) -> int:
    """Return 0 when pytest.ini, conftest, ship-gate, plugin, and docs are wired."""
    errors: list[str] = []
    plugin = root / "scripts" / "gcs_pytest_isolate.py"
    conftest = root / "tests" / "conftest.py"
    pytest_ini = root / "pytest.ini"
    ship_gate = root / "scripts" / "ci" / "ship-gate.sh"
    docs = root / "docs" / "studio" / "PYTEST.md"
    if not plugin.is_file():
        errors.append("missing scripts/gcs_pytest_isolate.py")
    if not conftest.is_file():
        errors.append("missing tests/conftest.py")
    else:
        conftest_text = conftest.read_text(encoding="utf-8")
        if "pytest_plugins" not in conftest_text or "gcs_pytest_isolate" not in conftest_text:
            errors.append("tests/conftest.py must set pytest_plugins to gcs_pytest_isolate")
    if not pytest_ini.is_file():
        errors.append("missing pytest.ini")
    else:
        ini = pytest_ini.read_text(encoding="utf-8")
        if "-p gcs_pytest_isolate" not in ini:
            errors.append("pytest.ini must register -p gcs_pytest_isolate")
        addopts = ""
        for line in ini.splitlines():
            stripped = line.strip()
            if stripped.startswith("addopts"):
                addopts = stripped.split("=", 1)[-1]
        if "-q" in addopts:
            errors.append("pytest.ini addopts must not include -q (hides N passed)")
    if not ship_gate.is_file():
        errors.append("missing scripts/ci/ship-gate.sh")
    else:
        gate = ship_gate.read_text(encoding="utf-8")
        unset_idx = gate.find("unset GCS_ACP_SEATS")
        pytest_idx = gate.find('pytest_out="$(.venv/bin/pytest -q')
        if unset_idx == -1 or pytest_idx == -1 or unset_idx > pytest_idx:
            errors.append("ship-gate.sh must unset live studio env before pytest")
        for var in LEAK_VARS:
            if var not in gate:
                errors.append(f"ship-gate.sh must unset {var}")
    if not docs.is_file():
        errors.append("missing docs/studio/PYTEST.md")
    if errors:
        print("pytest isolation: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print("pytest isolation: OK")
    return 0


@pytest.fixture
def gcs_temp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Opt into a temporary GCS_A2A_STATE / GCS_TASKBOARD_DB for one test."""
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_TASKBOARD_DB", str(db))
    for key in ("GCS_ACP_SEATS", "GCS_MIND_SEATS", "GCS_A2A_REGISTRY") + ALIAS_LEAK_VARS:
        monkeypatch.delenv(key, raising=False)
    return state


def pytest_configure(config: pytest.Config) -> None:
    """Strip leaked studio env and install live-bus guards before collection."""
    global _CONFIGURED
    config.addinivalue_line(
        "markers",
        "gcs_temp_state: opt into a temporary GCS_A2A_STATE directory",
    )
    apply_live_studio_env_strip()
    if _CONFIGURED:
        return
    install_isolation_guards()
    _CONFIGURED = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grok Cloud Studio pytest live-bus isolation plugin"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify pytest.ini / conftest / ship-gate isolation wiring",
    )
    parser.add_argument(
        "--root",
        default="",
        help="Checkout root (default: repository containing this script)",
    )
    args = parser.parse_args(argv)
    if not args.check:
        parser.print_help()
        return 2
    root = Path(args.root) if args.root else Path(__file__).resolve().parents[1]
    return check_isolation_wiring(root)


if __name__ == "__main__":
    raise SystemExit(main())
