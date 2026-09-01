"""git ls-remote preflight + Cursor ref-verify FOLLOWUP_FIRST."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "scripts" / "cloud" / "resolve_starting_ref.py"
spec = importlib.util.spec_from_file_location("resolve_starting_ref", SRC)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
followup_first_line = mod.followup_first_line
git_ls_remote = mod.git_ls_remote
is_cursor_ref_verify_error = mod.is_cursor_ref_verify_error


def _ok(stdout: str, rc: int = 0):
    def runner(cmd, **kwargs):
        return SimpleNamespace(returncode=rc, stdout=stdout, stderr="")

    return runner


def test_ls_remote_heads_sha() -> None:
    sha = "d32ed8033c0854302ba5ae49016eee0343b43796"
    got = git_ls_remote(
        "https://github.com/atebites-hub/grok-cloud-studio.git",
        "main",
        runner=_ok(f"{sha}\trefs/heads/main\n"),
    )
    assert got == sha


def test_ls_remote_miss() -> None:
    got = git_ls_remote(
        "https://github.com/atebites-hub/grok-cloud-studio.git",
        "no-such-branch",
        runner=_ok("", rc=2),
    )
    assert got is None


def test_cursor_verify_error_detect() -> None:
    msg = "[validation_error] Failed to verify existence of branch 'main' in repository atebites-hub/grok-cloud-studio."
    assert is_cursor_ref_verify_error(msg)
    assert is_cursor_ref_verify_error(
        "Failed to verify existence of commit 'abc' in repository atebites-hub/grok-cloud-studio"
    )
    assert not is_cursor_ref_verify_error("rate limit of 6000")


def test_followup_first_line_points_at_followup() -> None:
    line = followup_first_line(
        sha="deadbeef",
        ref="main",
        url="https://github.com/atebites-hub/grok-cloud-studio",
    )
    assert "FOLLOWUP_FIRST" in line
    assert "followup-cloud-agent.sh" in line
    assert "do not retry create" in line
    assert "deadbeef" in line
