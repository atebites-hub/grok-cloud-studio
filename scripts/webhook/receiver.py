#!/usr/bin/env python3
"""Deprecated path: canonical receiver is scripts/cloud/webhook_receiver.py."""
from __future__ import annotations

import runpy
from pathlib import Path

_CANONICAL = Path(__file__).resolve().parents[1] / "cloud" / "webhook_receiver.py"
runpy.run_path(str(_CANONICAL), run_name="__main__")
