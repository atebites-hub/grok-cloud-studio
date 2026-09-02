#!/usr/bin/env python3
"""A2A plugin stdio entry. Runs the shared Grok Cloud Studio MCP server.

Honor GCS_ROOT so a copy under seat GROK_HOME still imports gcs_mcp.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _gcs_root() -> Path:
    env = (os.environ.get("GCS_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


ROOT = _gcs_root()
sys.path.insert(0, str(ROOT / "scripts" / "mcp"))
from gcs_mcp import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--plane", "a2a", *sys.argv[1:]]))
