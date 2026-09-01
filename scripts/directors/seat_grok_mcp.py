#!/usr/bin/env python3
"""Merge taskboard stdio + Living Sky Linear HTTP into GROK_HOME/config.toml.

Idempotent: a second write (or a grok rewrite that dropped the marker
comments) must not append a duplicate `[compat.cursor]` /
`[mcp_servers.taskboard]` / `[mcp_servers.linear]` table. Duplicate tables
fail grok's TOML parse.

Linear stays in this Grok catalog (`url = "https://mcp.linear.app/mcp"`).
Do not copy GROK_HOME into Cursor CLI. `${LINEAR_API_KEY}` expands at grok
load time. Never print or commit the key.

Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
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
        "headers = { Authorization = "
        + q("Bearer ${LINEAR_API_KEY}")
        + " }\n"
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
    """Drop owned Cursor/taskboard/Linear tables even without markers."""
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
    """Return config.toml with one marked taskboard + Linear HTTP MCP block."""
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


def _is_absolute_posix(value: str) -> bool:
    return value.startswith("/") and "${" not in value


def lint_seat_taskboard_mcp(text: str) -> list[str]:
    """Return WARN reason tokens for an existing GROK_HOME/config.toml blob.

    Empty means the catalog already has an absolute command and args
    ``--db <absolute db> mcp``. Extra middle args are allowed. Does not
    write files. Does not require Linear MCP (PAL-45 is not this catalog).
    Missing files are not linted — doctor only scans existing
    ``*/grok-home/config.toml``.
    """
    reasons: list[str] = []
    raw = text or ""
    try:
        parsed = tomllib.loads(raw) if raw.strip() else {}
    except tomllib.TOMLDecodeError:
        return ["invalid-toml"]
    if not isinstance(parsed, dict):
        return ["invalid-toml"]
    servers = parsed.get("mcp_servers")
    table = servers.get("taskboard") if isinstance(servers, dict) else None
    if not isinstance(table, dict):
        return ["missing-taskboard-table"]
    command = table.get("command")
    if not isinstance(command, str) or not _is_absolute_posix(command):
        reasons.append("command-not-absolute")
    args = table.get("args")
    if not isinstance(args, list):
        reasons.append("args-not-db-mcp")
        return reasons
    str_args = [a if isinstance(a, str) else "" for a in args]
    if (
        len(str_args) < 3
        or str_args[0] != "--db"
        or str_args[-1] != "mcp"
    ):
        reasons.append("args-not-db-mcp")
    elif not _is_absolute_posix(str_args[1]):
        reasons.append("db-not-absolute")
    blob = command if isinstance(command, str) else ""
    blob += "".join(str_args)
    if "${" in blob:
        reasons.append("unexpanded-interpolation")
    out: list[str] = []
    for reason in reasons:
        if reason not in out:
            out.append(reason)
    return out


def _usage() -> None:
    print(
        "usage: seat_grok_mcp.py DEST_TOML COMMAND DB\n"
        "       seat_grok_mcp.py lint DEST_TOML [DEST_TOML ...]",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "lint":
        if len(args) < 2:
            _usage()
            return 2
        for dest in args[1:]:
            path = Path(dest)
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for reason in lint_seat_taskboard_mcp(text):
                print(f"{reason}\t{path}")
        return 0
    if len(args) != 3:
        _usage()
        return 2
    write_seat_taskboard_mcp_config(Path(args[0]), args[1], args[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
