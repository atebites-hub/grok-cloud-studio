"""Stateful Grok Build mind: mailbox + pin + stay-up. Fake grok only.

No live grok CLI, no network, no secrets. Default runner is a fake `grok`
binary that records argv and prints a json blob.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
DISPATCH_PY = REPO / "scripts" / "a2a" / "dispatch.py"
LIB_PY = REPO / "scripts" / "a2a" / "lib.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
AGENTS_DOC = REPO / "AGENTS.md"
A2A_DOC = REPO / "docs" / "A2A.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"
PLUGIN_DIR = REPO / "plugins" / "studio-mind"
