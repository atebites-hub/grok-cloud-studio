#!/usr/bin/env python3
"""Fail-closed LIV-84 art-env catalog/remint gate for doctor.sh and recover.sh.

Extra High Higgsfield is the existing cloud-env snapshot login — not a Cursor
MCP server. Sentry DSN is dashboard Secrets / process env, not MCP. This gate
refuses when `.cursor/mcp.json` (checkout or live `$GCS_A2A_STATE`) already
contains Higgsfield or Sentry, even with `${VAR}` expansions. That is not a
key leak; leftover #143 covers argv/literals. Do not remint LIV-84 as
`.cursor/environment.json` or a `cloud-env` registry seat.

Grok-home Higgsfield (seat `GROK_HOME/config.toml`) is grok-only and is not
scanned here. Never prints matched values — only path, line, and rule id.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

Hit = tuple[str, str, int]

CURSOR_MCP_REL = Path(".cursor") / "mcp.json"
ENVIRONMENT_JSON_REL = Path(".cursor") / "environment.json"
REGISTRY_REL = Path("docs") / "a2a" / "registry.json"


def _line_of(text: str, *needles: str) -> int:
    low = text.lower()
    for needle in needles:
        idx = low.find(needle.lower())
        if idx >= 0:
            return text[:idx].count("\n") + 1
    return 1


def _blob(name: str, spec: Any) -> str:
    try:
        dumped = json.dumps(spec, default=str)
    except TypeError:
        dumped = str(spec)
    return f"{name} {dumped}".lower()


def _is_art_merge(name: str, spec: Any) -> bool:
    blob = _blob(name, spec)
    return "higgsfield" in blob or "sentry" in blob


def scan_cursor_mcp(rel: str, text: str) -> list[Hit]:
    """FAIL when a Cursor MCP document already contains Higgsfield or Sentry."""
    hits: list[Hit] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return hits
    if not isinstance(data, dict):
        return hits
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return hits
    for name, spec in servers.items():
        if not _is_art_merge(str(name), spec):
            continue
        hits.append((rel, "cursor_catalog_merged", _line_of(text, str(name), "higgsfield", "sentry")))
    return hits


def _scan_registry(rel: str, text: str) -> list[Hit]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    seats = data.get("seats")
    if not isinstance(seats, dict):
        return []
    if "cloud-env" not in seats:
        return []
    return [(rel, "cloud_env_registry_seat", _line_of(text, "cloud-env"))]


def _rel_to(path: Path, root: Path | None, state: Path | None) -> str:
    for base in (root, state):
        if base is None:
            continue
        try:
            return str(path.resolve().relative_to(base.resolve()))
        except ValueError:
            continue
    return str(path)


def _iter_live_cursor_mcp(state: Path) -> list[Path]:
    found: list[Path] = []
    if not state.is_dir():
        return found
    for path in state.rglob("mcp.json"):
        if not path.is_file() or path.is_symlink():
            continue
        if ".cursor" not in path.parts:
            continue
        found.append(path)
    return found


def collect_hits(
    root: Path | None = None,
    state: Path | None = None,
) -> list[Hit]:
    hits: list[Hit] = []
    if root is not None:
        cursor_mcp = root / CURSOR_MCP_REL
        if cursor_mcp.is_file() and not cursor_mcp.is_symlink():
            text = cursor_mcp.read_text(encoding="utf-8", errors="replace")
            hits.extend(scan_cursor_mcp(str(CURSOR_MCP_REL), text))
        env_json = root / ENVIRONMENT_JSON_REL
        if env_json.is_file() and not env_json.is_symlink():
            # Existence is the remint. Do not dump file contents (may hold secrets).
            hits.append((str(ENVIRONMENT_JSON_REL), "cloud_env_remint", 1))
        registry = root / REGISTRY_REL
        if registry.is_file() and not registry.is_symlink():
            text = registry.read_text(encoding="utf-8", errors="replace")
            hits.extend(_scan_registry(str(REGISTRY_REL), text))
    if state is not None:
        for path in _iter_live_cursor_mcp(state):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = _rel_to(path, root, state)
            hits.extend(scan_cursor_mcp(rel, text))
    return hits


def format_report(hits: list[Hit]) -> str:
    if not hits:
        return "liv84_art_env=clean\n"
    lines = ["liv84_art_env=FAIL"]
    for rel, rule_id, line in hits:
        lines.append(f"  {rel}:{line} rule={rule_id}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LIV-84 art env Cursor catalog / remint fail-closed gate"
    )
    parser.add_argument("--root", default="", help="checkout root")
    parser.add_argument("--state", default="", help="GCS_A2A_STATE (live .cursor/mcp.json)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    state = Path(args.state).resolve() if args.state else None
    hits = collect_hits(root=root, state=state)
    sys.stdout.write(format_report(hits))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
