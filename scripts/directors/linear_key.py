"""Load LINEAR_API_KEY from a secret file. Never print the value.

Default path: $GCS_A2A_STATE/linear.env (KEY=value). Optional raw key in
~/.config/linear/api.key. Palemon Linear is Living Sky — never Black Swan Money.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import MutableMapping

_LIN_PREFIX = "lin_"


def resolve_linear_key_file(
    *,
    state_dir: Path | None = None,
    key_file: Path | None = None,
    home: Path | None = None,
) -> Path | None:
    if key_file is not None:
        return key_file if key_file.is_file() else None
    env_path = (os.environ.get("GCS_LINEAR_KEY_FILE") or "").strip()
    if env_path:
        path = Path(env_path)
        return path if path.is_file() else None
    if state_dir is not None:
        candidate = state_dir / "linear.env"
        if candidate.is_file():
            return candidate
    home_dir = home if home is not None else Path(os.environ.get("HOME") or "")
    if str(home_dir):
        alt = home_dir / ".config" / "linear" / "api.key"
        if alt.is_file():
            return alt
    return None


def read_linear_api_key(path: Path) -> str:
    """Parse LINEAR_API_KEY=… or a raw lin_… token. Never logs the secret."""
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if line.upper().startswith("LINEAR_API_KEY"):
            _, _, value = line.partition("=")
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            return value.strip()
        if line.startswith(_LIN_PREFIX):
            return line
    stripped = text.strip()
    if stripped.startswith(_LIN_PREFIX) and "\n" not in stripped and "=" not in stripped:
        return stripped
    return ""


def apply_linear_key_env(
    env: MutableMapping[str, str],
    *,
    state_dir: Path | None = None,
    key_file: Path | None = None,
    home: Path | None = None,
) -> bool:
    """Set LINEAR_API_KEY on env from the secret file. True if a value was applied."""
    existing = (env.get("LINEAR_API_KEY") or "").strip()
    if existing:
        return False
    path = resolve_linear_key_file(state_dir=state_dir, key_file=key_file, home=home)
    if path is None:
        return False
    value = read_linear_api_key(path)
    if not value:
        return False
    env["LINEAR_API_KEY"] = value
    return True
