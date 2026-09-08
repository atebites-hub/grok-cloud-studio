#!/usr/bin/env python3
"""LIV-82 hive Linear stamp is STATUS evidence when Linear MCP needsAuth.

When LINEAR_API_KEY is unset and Linear MCP is needsAuth, print
LINEAR_STAMP_FAIL with no comment id. Never call mcp_auth. Never print
the key. Distinct from leftover Linear MCP catalog interpolation tests
and from GraphQL leftover (linear_comment.py). Living Sky only.
Never Black Swan Money. Stdlib only.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, TextIO

_DIRECTORS = Path(__file__).resolve().parent / "directors"
if str(_DIRECTORS) not in sys.path:
    sys.path.insert(0, str(_DIRECTORS))

from linear_key import apply_linear_key_env  # noqa: E402

LIVING_SKY_TEAM_KEY = "LIV"
ISSUE_REF_RE = re.compile(r"([A-Za-z][A-Za-z0-9]*-\d+)")
ISSUE_URL_RE = re.compile(r"/issue/([A-Za-z][A-Za-z0-9]*-\d+)", re.I)
FAIL_TOKEN = "LINEAR_STAMP_FAIL"
SKIP_TOKEN = "LINEAR_STAMP_SKIP"
KIND_STATUS = "status"
MCP_AUTH_NEVER = "never"


@dataclass(frozen=True)
class StampResult:
    token: str
    issue: str
    reason: str
    comment_id: str | None = None
    kind: str = KIND_STATUS
    mcp_auth: str = MCP_AUTH_NEVER
    exit_code: int = 2

    def line(self) -> str:
        comment = "none" if not self.comment_id else str(self.comment_id)
        return (
            f"{self.token} issue={self.issue} comment={comment} "
            f"kind={self.kind} reason={self.reason} mcp_auth={self.mcp_auth}"
        )


def mcp_status_is_needs_auth(raw: str) -> bool:
    norm = str(raw or "").strip().lower().replace("_", "").replace("-", "")
    return norm == "needsauth"


def parse_issue_ref(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "LIV-82"
    url_hit = ISSUE_URL_RE.search(text)
    if url_hit:
        return url_hit.group(1).upper()
    direct = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*-\d+)", text)
    if direct:
        return direct.group(1).upper()
    loose = ISSUE_REF_RE.search(text)
    if loose:
        return loose.group(1).upper()
    return text.strip().upper()


def is_living_sky_identifier(identifier: str) -> bool:
    return str(identifier or "").upper().startswith(f"{LIVING_SKY_TEAM_KEY}-")


def linear_key_present(
    environ: Mapping[str, str] | MutableMapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> bool:
    """True when a Linear key is available. Never returns the secret."""
    env: dict[str, str] = dict(os.environ if environ is None else environ)
    for name in ("LINEAR_API_KEY", "GCS_LINEAR_API_KEY"):
        if str(env.get(name) or "").strip():
            return True
    state = str(env.get("GCS_A2A_STATE") or "").strip()
    state_dir = Path(state) if state else None
    home_path = home
    if home_path is None:
        home_raw = str(env.get("HOME") or "")
        home_path = Path(home_raw) if home_raw else None
    apply_linear_key_env(env, state_dir=state_dir, home=home_path)
    return bool(str(env.get("LINEAR_API_KEY") or "").strip())


def hive_linear_stamp(
    *,
    issue: str = "LIV-82",
    mcp_status: str = "",
    environ: Mapping[str, str] | None = None,
    mcp_auth_fn: Callable[..., Any] | None = None,
    home: Path | None = None,
) -> StampResult:
    """STATUS evidence for LIV-82. Never calls mcp_auth. Never posts a comment."""
    del mcp_auth_fn  # never invoke; hive stamp is STATUS evidence only
    identifier = parse_issue_ref(issue)
    if not is_living_sky_identifier(identifier):
        return StampResult(
            token=SKIP_TOKEN,
            issue=identifier,
            reason="not-living-sky (never Black Swan)",
        )
    key_set = linear_key_present(environ, home=home)
    needs_auth = mcp_status_is_needs_auth(mcp_status)
    if not key_set and needs_auth:
        return StampResult(
            token=FAIL_TOKEN,
            issue=identifier,
            reason="unset-key+mcp-needsAuth",
        )
    if not str(mcp_status or "").strip():
        return StampResult(
            token=SKIP_TOKEN,
            issue=identifier,
            reason="mcp-status-missing",
        )
    if key_set:
        return StampResult(
            token=SKIP_TOKEN,
            issue=identifier,
            reason="key-present-use-linear-comment",
        )
    return StampResult(
        token=SKIP_TOKEN,
        issue=identifier,
        reason="mcp-not-needsAuth",
    )


def _emit(stream: TextIO, message: str) -> None:
    stream.write(message + "\n")
    stream.flush()


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    mcp_auth_fn: Callable[..., Any] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="linear_stamp.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "LIV-82 hive Linear stamp. STATUS evidence only when "
            "LINEAR_API_KEY is unset and Linear MCP is needsAuth. "
            "Prints LINEAR_STAMP_FAIL with comment=none. Never call mcp_auth. "
            "Never print LINEAR_API_KEY. Living Sky only (never Black Swan). "
            "Not GraphQL leftover. Not MCP catalog interpolation leftover."
        ),
        epilog=(
            "Examples:\n"
            "  python3 scripts/linear_stamp.py --issue LIV-82 "
            "--mcp-status needsAuth\n"
        ),
    )
    parser.add_argument(
        "--issue",
        default="LIV-82",
        help="Living Sky identifier (LIV-82) or linear.app/livingsky issue URL",
    )
    parser.add_argument(
        "--mcp-status",
        default="",
        help="Linear MCP namespace status (needsAuth). Or GCS_LINEAR_MCP_STATUS.",
    )
    args = parser.parse_args(argv)
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    env: Mapping[str, str] = os.environ if environ is None else environ
    mcp_status = str(args.mcp_status or "").strip() or str(
        env.get("GCS_LINEAR_MCP_STATUS") or ""
    ).strip()
    result = hive_linear_stamp(
        issue=str(args.issue or "LIV-82"),
        mcp_status=mcp_status,
        environ=env,
        mcp_auth_fn=mcp_auth_fn,
    )
    _emit(out, result.line())
    if result.token == FAIL_TOKEN:
        _emit(err, result.line())
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
