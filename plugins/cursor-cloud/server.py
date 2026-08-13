#!/usr/bin/env python3
"""Cursor Cloud plugin stdio entry. Runs the shared Grok Cloud Studio MCP server."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "mcp"))
from gcs_mcp import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--plane", "cloud", *sys.argv[1:]]))
