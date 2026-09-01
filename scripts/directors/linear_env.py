#!/usr/bin/env python3
"""Load LINEAR_API_KEY from env or a secret file. Never print the value.

Product Linear workspace is Living Sky (linear.app/livingsky, team Livingsky / LIV).
Never Black Swan Money.

Cursor Cloud snapshots should export this key (source scripts/cloud/load-linear-env.sh
from the snapshot install, or bake LINEAR_API_KEY from the secret file). Cloud
agents cannot scrape seat GROK_HOME.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LINEAR_WORKSPACE_HOST = "linear.app/livingsky"
LINEAR_TEAM = "Livingsky"
LINEAR_TEAM_KEY = "LIV"
BANNED_LINEAR_WORKSPACE = "Black Swan Money"

_ASSIGN_RE = re.compile(r"^(?:export\s+)?LINEAR_API_KEY\s*=\s*(.*)$")


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1].strip()
    return text


def parse_secret_text(text: str) -> str:
    """First LINEAR_API_KEY= assignment, else the first non-comment line."""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGN_RE.match(line)
        if match:
            value = _unquote(match.group(1))
            if value:
                return value
            continue
        return line
    return ""


def linear_secret_candidates() -> list[Path]:
    out: list[Path] = []
    explicit = (os.environ.get("LINEAR_API_KEY_FILE") or "").strip()
    if explicit:
        out.append(Path(explicit))
    state = (os.environ.get("GCS_A2A_STATE") or "").strip()
    if state:
        out.append(Path(state) / "secrets" / "linear.api_key")
    home = Path.home()
    out.append(home / ".config" / "linear" / "api_key")
    agent_env = (os.environ.get("CURSOR_AGENT_ENV") or "").strip()
    if agent_env:
        out.append(Path(agent_env))
    else:
        out.append(home / ".config" / "cursor" / "agent.env")
    seen: set[str] = set()
    unique: list[Path] = []
    for path in out:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def load_linear_api_key() -> str:
    """LINEAR_API_KEY from the environment or a secret file. Never print it."""
    existing = (os.environ.get("LINEAR_API_KEY") or "").strip()
    if existing:
        return existing
    for path in linear_secret_candidates():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        value = parse_secret_text(text)
        if value:
            return value
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve LINEAR_API_KEY from env or a secret file. Never logs the value."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="value",
        choices=("value", "workspace"),
        help="value prints the key to stdout for capture with set +x disabled",
    )
    args = parser.parse_args(argv)
    if args.command == "workspace":
        print(LINEAR_WORKSPACE_HOST)
        print(f"team={LINEAR_TEAM} key={LINEAR_TEAM_KEY}")
        print(f"never={BANNED_LINEAR_WORKSPACE}")
        return 0
    sys.stdout.write(load_linear_api_key())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
