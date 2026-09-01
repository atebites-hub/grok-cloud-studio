#!/usr/bin/env python3
"""A2A plugin stdio entry. Runs the shared Grok Cloud Studio MCP server."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / "scripts" / "mcp"))
from gcs_mcp import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--plane", "a2a", *sys.argv[1:]]))
