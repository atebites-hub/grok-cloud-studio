#!/usr/bin/env python3
"""Merge taskboard stdio + Linear HTTP MCP into an isolated GROK_HOME/config.toml.

Idempotent: a second write (or a grok rewrite that dropped the marker
comments) must not append a duplicate `[compat.cursor]` /
`[mcp_servers.taskboard]` / `[mcp_servers.linear]` table. Duplicate tables
fail grok's TOML parse.

Linear is the Grok catalog form (`grok mcp add --transport http linear
https://mcp.linear.app/mcp`), not a copy of Cursor `.cursor/mcp.json`.
Palemon Linear is Living Sky (linear.app/livingsky, team Livingsky / LIV).
Never Black Swan Money.

Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MARK_START = "# gcs-seat-taskboard-mcp"
MARK_END = "# gcs-seat-taskboard-mcp-end"
LINEAR_MARK_START = "# gcs-seat-linear-mcp"
LINEAR_MARK_END = "# gcs-seat-linear-mcp-end"
LINEAR_MCP_URL = "https://mcp.linear.app/mcp"

_MARKED_BLOCK = re.compile(
    r"(?ms)^"
    + re.escape(MARK_START)
    + r"[ \t]*\n.*?^"
    + re.escape(MARK_END)
    + r"[ \t]*\n?"
)
_LINEAR_MARKED_BLOCK = re.compile(
    r"(?ms)^"
    + re.escape(LINEAR_MARK_START)
    + r"[ \t]*\n.*?^"
    + re.escape(LINEAR_MARK_END)
    + r"[ \t]*\n?"
)
_MARK_LINE = re.compile(
    r"(?m)^" + re.escape(MARK_START) + r"(?:-end)?[ \t]*\n?"
)
_LINEAR_MARK_LINE = re.compile(
    r"(?m)^" + re.escape(LINEAR_MARK_START) + r"(?:-end)?[ \t]*\n?"
)
_OWNED_TABLES = ("compat.cursor", "mcp_servers.taskboard", "mcp_servers.linear")


def q(value: str) -> str:
    return json.dumps(value)


def mcp_block(command: str, db: str) -> str:
    return (
        f"{MARK_START}\n"
        "[compat.cursor]\n"
        "mcps = false\n"
        "\n"
        "[mcp_servers.taskboard]\n"
        f"command = {q(command)}\n"
        f"args = [{q('--db')}, {q(db)}, {q('mcp')}]\n"
        f"{MARK_END}\n"
    )


def linear_block() -> str:
    """Grok HTTP catalog Linear. ${LINEAR_API_KEY} expands at grok load time."""
    return (
        f"{LINEAR_MARK_START}\n"
# Palemon Linear: Living Sky (linear.app/livingsky) team Livingsky / LIV. Never Black Swan Money.
        "[mcp_servers.linear]\n"
        f"url = {q(LINEAR_MCP_URL)}\n"
        'headers = { Authorization = "Bearer ${LINEAR_API_KEY}", '
        '"x-mcp-session-id" = "{{session_id}}" }\n'
        f"{LINEAR_MARK_END}\n"
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
    """Drop GCS-owned MCP tables even without markers."""
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


def merge_seat_linear_mcp(text: str) -> str:
    """Return config.toml with exactly one marked Linear HTTP MCP block."""
    text = _LINEAR_MARKED_BLOCK.sub("", text or "")
    text = _LINEAR_MARK_LINE.sub("", text)
    text = _strip_linear_tables(text)
    text = _collapse_blank_lines(text)
    block = linear_block()
    if text:
        return text + "\n\n" + block
    return block


def _strip_linear_tables(text: str) -> str:
    out: list[str] = []
    dropping = False
    for line in text.splitlines(keepends=True):
        header = _header_name(line)
        if header is not None:
            dropping = header == "mcp_servers.linear" or header.startswith(
                "mcp_servers.linear."
            )
        if dropping:
            continue
        out.append(line)
    return "".join(out)


def merge_seat_taskboard_mcp(text: str, command: str, db: str) -> str:
    """Return config.toml with one taskboard block and one Linear HTTP block."""
    text = _MARKED_BLOCK.sub("", text or "")
    text = _MARK_LINE.sub("", text)
    text = _LINEAR_MARKED_BLOCK.sub("", text)
    text = _LINEAR_MARK_LINE.sub("", text)
    text = strip_owned_toml_tables(text)
    text = _collapse_blank_lines(text)
    block = mcp_block(command, db) + "\n" + linear_block()
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
