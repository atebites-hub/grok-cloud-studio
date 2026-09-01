#!/usr/bin/env python3
"""Cursor Cloud plugin stdio entry. Runs the shared Grok Cloud Studio MCP server.

Honors GCS_ROOT, then GROK_HOME/gcs-root after grok plugin install copies
this file off the repo tree. Extra High only. Not Bot CloudAgent.
Handshake stays open.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _resolve_gcs_root() -> Path:
    env = (os.environ.get("GCS_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    grok_home = (os.environ.get("GROK_HOME") or "").strip()
    if grok_home:
        stamp = Path(grok_home).expanduser() / "gcs-root"
        try:
            text = stamp.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            return Path(text).expanduser().resolve()
    here = Path(__file__).resolve().parent
    for cand in (here, *here.parents):
        if (cand / "scripts" / "mcp" / "gcs_mcp.py").is_file():
            return cand
    return Path(__file__).resolve().parents[2]


ROOT = _resolve_gcs_root()
os.environ.setdefault("GCS_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "mcp"))
from gcs_mcp import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--plane", "cloud", *sys.argv[1:]]))
