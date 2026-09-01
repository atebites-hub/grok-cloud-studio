#!/usr/bin/env python3
"""Merge taskboard + Linear MCP into an isolated GROK_HOME/config.toml.

Idempotent: a second write (or a grok rewrite that dropped the marker
comments) must not append a duplicate `[compat.cursor]` /
`[mcp_servers.taskboard]` / `[mcp_servers.linear]` table. Duplicate tables
fail grok's TOML parse.

Linear is the Grok catalog remote MCP (`grok mcp add --transport http linear`),
not a copy of Cursor `.cursor/mcp.json`. Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MARK_START = "# gcs-seat-taskboard-mcp"
MARK_END = "# gcs-seat-taskboard-mcp-end"

_MARKED_BLOCK = re.compile(
    r"(?ms)^"
    + re.escape(MARK_START)
    + r"[ \t]*\n.*?^"
    + re.escape(MARK_END)
    + r"[ \t]*\n?"
)
_MARK_LINE = re.compile(
    r"(?m)^" + re.escape(MARK_START) + r"(?:-end)?[ \t]*\n?"
)
_OWNED_TABLES = ("compat.cursor", "mcp_servers.taskboard", "mcp_servers.linear")
LINEAR_MCP_URL = "https://mcp.linear.app/mcp"


def q(value: str) -> str:
    return json.dumps(value)


def mcp_block(command: str, db: str) -> str:
    # Grok catalog (GROK_HOME/config.toml), not a copy of .cursor/mcp.json.
    # Linear remote MCP is equivalent to:
    #   grok mcp add --transport http linear https://mcp.linear.app/mcp \
    #     --header "Authorization: Bearer ${LINEAR_API_KEY}"
    auth = "Bearer ${LINEAR_API_KEY}"
    return (
        f"{MARK_START}\n"
        "[compat.cursor]\n"
        "mcps = false\n"
        "\n"
        "[mcp_servers.taskboard]\n"
        f"command = {q(command)}\n"
        f"args = [{q('--db')}, {q(db)}, {q('mcp')}]\n"
        "\n"
        "[mcp_servers.linear]\n"
        f"url = {q(LINEAR_MCP_URL)}\n"
        f"headers = {{ Authorization = {q(auth)} }}\n"
        f"{MARK_END}\n"
    )


def _header_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    if stripped.startswith("[["):
        inner = stripped[2:-2].strip() if stripped.endswith("]]") else stripped[2:-1].strip()
        return inner
    return stripped[1:-1].strip()


def _owned_header(header: str) -> bool:
    for name in _OWNED_TABLES:
        if header == name or header.startswith(name + "."):
            return True
    return False


def strip_owned_toml_tables(text: str) -> str:
    """Drop owned `[compat.cursor]`, taskboard, and Linear tables even without markers."""
    out: list[str] = []
    dropping = False
    for line in text.splitlines(keepends=True):
        header = _header_name(line)
        if header is not None:
            dropping = _owned_header(header)
        if dropping:
            continue
        out.append(line)
    return "".join(out)


def _collapse_blank_lines(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def merge_seat_taskboard_mcp(text: str, command: str, db: str) -> str:
    """Return config.toml with exactly one marked taskboard MCP block."""
    text = _MARKED_BLOCK.sub("", text or "")
    text = _MARK_LINE.sub("", text)
    text = strip_owned_toml_tables(text)
    text = _collapse_blank_lines(text)
    block = mcp_block(command, db)
    if text:
        return text + "\n\n" + block
    return block


def write_seat_taskboard_mcp_config(dest: Path, command: str, db: str) -> None:
    text = dest.read_text(encoding="utf-8") if dest.is_file() else ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(merge_seat_taskboard_mcp(text, command, db), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        print(
            "usage: seat_grok_mcp.py DEST_TOML COMMAND DB",
            file=sys.stderr,
        )
        return 2
    write_seat_taskboard_mcp_config(Path(args[0]), args[1], args[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
