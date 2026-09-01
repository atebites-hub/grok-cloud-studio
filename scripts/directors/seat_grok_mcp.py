#!/usr/bin/env python3
"""Merge seat stdio MCP into an isolated GROK_HOME/config.toml.

Writes taskboard (`taskboard --db $DB mcp`) and chrome-devtools
(`npx -y chrome-devtools-mcp@latest`). chrome-devtools is the xAI Grok
catalog browser plugin/MCP (live Chrome). Equivalent to:

  GROK_HOME=$gh grok mcp add taskboard -- "$bin" --db "$db" mcp
  GROK_HOME=$gh grok mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest

qa-a visually playtests CLIENT_PLAYTEST_URL with chrome-devtools
`navigate_page`. Python mind does not call that tool (no second agent
loop). Not Cursor CLI. Not Bot CloudAgent.

Idempotent: a second write (or a grok rewrite that dropped the marker
comments) must not append a duplicate `[compat.cursor]` /
`[mcp_servers.taskboard]` / `[mcp_servers.chrome-devtools]` table.
Duplicate tables fail grok's TOML parse.

Do not copy this block into Cursor `.cursor/mcp.json`. Two catalogs.

Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

MARK_START = "# gcs-seat-taskboard-mcp"
MARK_END = "# gcs-seat-taskboard-mcp-end"

CHROME_DEVTOOLS_SERVER = "chrome-devtools"
CHROME_DEVTOOLS_COMMAND = "npx"
CHROME_DEVTOOLS_PACKAGE = "chrome-devtools-mcp@latest"
CHROME_DEVTOOLS_ARGS = ("-y", CHROME_DEVTOOLS_PACKAGE)
CLIENT_PLAYTEST_URL = "http://127.0.0.1:5173/"

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
_OWNED_TABLES = (
    "compat.cursor",
    "mcp_servers.taskboard",
    "mcp_servers.chrome-devtools",
)


def q(value: str) -> str:
    return json.dumps(value)


def chrome_devtools_toml(command: str = CHROME_DEVTOOLS_COMMAND) -> str:
    args = ", ".join(q(a) for a in CHROME_DEVTOOLS_ARGS)
    return (
        f"[mcp_servers.{CHROME_DEVTOOLS_SERVER}]\n"
        f"command = {q(command)}\n"
        f"args = [{args}]\n"
    )


def chrome_devtools_open_client_tool(
    url: str | None = None,
) -> dict[str, Any]:
    """Grok catalog chrome-devtools `navigate_page` for visual QA.

    Directors (qa-a) ask grok to use this MCP tool. Python mind.py does
    not parse grok stdout or invoke chrome-devtools itself.
    """
    origin = url if url else CLIENT_PLAYTEST_URL
    return {
        "server": CHROME_DEVTOOLS_SERVER,
        "name": "navigate_page",
        "arguments": {"url": origin},
    }


def mcp_block(command: str, db: str) -> str:
    return (
        f"{MARK_START}\n"
        "[compat.cursor]\n"
        "mcps = false\n"
        "\n"
        "[mcp_servers.taskboard]\n"
        f"command = {q(command)}\n"
        f"args = [{q('--db')}, {q(db)}, {q('mcp')}]\n"
        "\n"
        f"{chrome_devtools_toml()}"
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


def merge_seat_taskboard_mcp(text: str, command: str, db: str) -> str:
    """Return config.toml with exactly one marked GCS MCP block."""
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
