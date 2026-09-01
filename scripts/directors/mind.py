#!/usr/bin/env python3
"""Grok Build seat mind: mailbox + pin + stay-up.

Python is not the agent. It harvests one inbox line, pins a grok session UUID,
runs one `grok --prompt-file` turn, persists json stdout, and stays up. Grok is
the agent for that turn (its own tool loop, `--max-turns 40`). Default
`GCS_MIND_RUNNER=auto` persists `$GCS_A2A_STATE/<seat>/mind/runner` (`grok` or
`cursor`). Each mail line uses that file. On quota / HTTP 402, flip the file
and retry that same mail line once on the other runner (`MIND_SWITCH`). Forced
`GCS_MIND_RUNNER=grok|cursor` does not flip. Never remint the grok UUID because
harvest was empty or because the runner switched.

Do not parse grok stdout for function calls. Do not run a second tool-calling
loop. Do not use grok agent serve or leftover ACP inject on opted-in mind
seats. Pin one UUID in mind/session; first turn `--session-id`, later turns
`--resume` that id. Never remint because harvest was empty. Never bare `-p` on
grok (`--single` requires a prompt; `--prompt-file` is the prompt). Cursor
CLI uses `-p` (print mode) and a positional prompt. `--agent-profile`,
`--trust`, and `--plugin-dir` are grok agent flags, not grok headless.

Stdlib only. Donald/orchestrator (skipSeats) are not mind seats.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import canonical_seat, skip_seats  # noqa: E402

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))


def _load_liv_stamp_mod() -> Any:
    """Load scripts/studio/linear/liv_stamp.py as liv_stamp (shared sys.modules)."""
    name = "liv_stamp"
    path = (ROOT / "scripts" / "studio" / "linear" / "liv_stamp.py").resolve()
    cached = sys.modules.get(name)
    cached_file = getattr(cached, "__file__", None) if cached is not None else None
    if cached is not None and cached_file and Path(cached_file).resolve() == path:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_liv_stamp = _load_liv_stamp_mod()
maybe_stamp_after_task = _liv_stamp.maybe_stamp_after_task
plugin_liv_stamp = _liv_stamp.plugin_liv_stamp
LIV_STAMP_SCHEMA = _liv_stamp.LIV_STAMP_SCHEMA

_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(CURSOR_API_KEY|GCS_WEBHOOK_SECRET|Authorization|Bearer|"
    r"server-key|ACP_SECRET|api[_-]?key)\s*[=:]\s*\S+"
)
_SESSION_IN_USE_RE = re.compile(
    r"session.*already in use|already in use.*session",
    re.IGNORECASE | re.DOTALL,
)
_USAGE_EXHAUSTED_RE = re.compile(
    r"usage balance exhausted|\bHTTP\s*402\b",
    re.IGNORECASE,
)
MIND_FAIL_STDERR_CHARS = 240
CURSOR_MIND_MODEL = "cursor-grok-4.6-xhigh"
GROK_MIND_MODEL = "grok-4.6"
GROK_MIND_REASONING_EFFORT = "xhigh"  # extra-high
