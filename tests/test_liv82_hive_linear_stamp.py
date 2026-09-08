"""LIV-82 remaining: hive Linear stamp is STATUS evidence when MCP needsAuth.

When LINEAR_API_KEY is unset and Linear MCP is needsAuth, print
LINEAR_STAMP_FAIL with no comment id. Never call mcp_auth. Never print
the key. Distinct from leftover Linear MCP catalog interpolation tests
(test_linear_mcp.py / test_cursor_cloud_linear_mcp.py) and from GraphQL
commentCreate (linear_comment.py). Living Sky only. Never Black Swan.
Never Bot CloudAgent. Does not remint CLOSED #109/#126/#130 hive hooks.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "linear_stamp.py"
FEATURE = ROOT / "tests" / "features" / "liv82_hive_linear_stamp_status.feature"
LEFTOVER_INTERP = ROOT / "tests" / "test_linear_mcp.py"
CURSOR_INTERP = ROOT / "tests" / "test_cursor_cloud_linear_mcp.py"
LINEAR_COMMENT = ROOT / "scripts" / "linear_comment.py"
DOC = ROOT / "docs" / "studio" / "LINEAR.md"
README = ROOT / "README.md"
ARCH = ROOT / "docs" / "ARCHITECTURE.md"
DOCTOR = ROOT / "doctor.sh"
INSTALL = ROOT / "install.sh"

sys.path.insert(0, str(ROOT / "scripts"))

from linear_stamp import (  # noqa: E402
    hive_linear_stamp,
    linear_key_present,
    main,
    mcp_status_is_needs_auth,
)

FAKE_KEY = "lin_api_hive_stamp_must_never_print_" + ("x" * 16)
BLACK_SWAN = "Black Swan Money"
PRIVATE_GAME = "atebites-hub/" + "palemon"
INTERP_TOKEN = "${" + "LINEAR_API_KEY}"


def _strip_linear_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (
        "LINEAR_API_KEY",
        "GCS_LINEAR_API_KEY",
        "GCS_LINEAR_KEY_FILE",
        "LINEAR_API_KEY_FILE",
        "GCS_LINEAR_MCP_STATUS",
        "GCS_A2A_STATE",
    ):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


def _run_main(
    argv: list[str],
    *,
    environ: dict[str, str] | None = None,
    mcp_auth_fn: Any = None,
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = main(
        argv,
        environ=environ,
        stdout=stdout,
        stderr=stderr,
        mcp_auth_fn=mcp_auth_fn,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def test_feature_file_states_status_evidence_law() -> None:
    assert FEATURE.is_file()
    text = FEATURE.read_text(encoding="utf-8")
    low = text.lower()
    assert "LIV-82" in text
    assert "LINEAR_STAMP_FAIL" in text
    assert "needsAuth" in text
    assert "LINEAR_API_KEY is unset" in text or "unset" in low
    assert "comment id" in low
    assert "mcp_auth" in low
    assert "status" in low
    assert "never" in low and "black swan" in low
    assert INTERP_TOKEN not in text
    assert PRIVATE_GAME not in text
    assert "Scenario:" in text
    assert "Given " in text and "When " in text and "Then " in text


def test_script_exists_stdlib_never_mcp_auth_or_graphql() -> None:
    assert SCRIPT.is_file()
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3")
    assert "import requests" not in text
    assert "commentCreate" not in text
    assert "issueDelete" not in text
    assert "mcp_auth(" not in text
    assert "CallMcpAuth" not in text
    assert INTERP_TOKEN not in text
    assert "LINEAR_STAMP_FAIL" in text
    assert "needsAuth" in text
    assert PRIVATE_GAME not in text
    low = text.lower()
    assert "black swan" in low
    assert "never" in low
    assert "urllib" not in text


def test_this_slice_is_not_leftover_mcp_interpolation() -> None:
    leftover = LEFTOVER_INTERP.read_text(encoding="utf-8")
    cursor = CURSOR_INTERP.read_text(encoding="utf-8")
    stamp = SCRIPT.read_text(encoding="utf-8")
    here = Path(__file__).read_text(encoding="utf-8")
    assert INTERP_TOKEN in leftover
    assert INTERP_TOKEN in cursor
    assert INTERP_TOKEN not in stamp
    assert "hive_linear_stamp" not in leftover
    assert "LINEAR_STAMP_FAIL" not in leftover
    assert "LINEAR_STAMP_FAIL" in here
    assert "commentCreate" in LINEAR_COMMENT.read_text(encoding="utf-8")
    assert "commentCreate" not in stamp


def test_mcp_status_is_needs_auth_normalizes() -> None:
    assert mcp_status_is_needs_auth("needsAuth") is True
    assert mcp_status_is_needs_auth("needs_auth") is True
    assert mcp_status_is_needs_auth("needs-auth") is True
    assert mcp_status_is_needs_auth("NEEDSAUTH") is True
    assert mcp_status_is_needs_auth("ready") is False
    assert mcp_status_is_needs_auth("") is False
    assert mcp_status_is_needs_auth("unknown") is False


def test_linear_key_present_is_boolean_never_returns_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _strip_linear_env(monkeypatch, tmp_path)
    env: dict[str, str] = {"HOME": str(tmp_path / "home")}
    assert linear_key_present(env) is False
    env["LINEAR_API_KEY"] = FAKE_KEY
    assert linear_key_present(env) is True
    assert linear_key_present(env) is not FAKE_KEY


def test_unset_key_and_needs_auth_prints_linear_stamp_fail_no_comment_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _strip_linear_env(monkeypatch, tmp_path)
    spy = MagicMock(name="mcp_auth")
    result = hive_linear_stamp(
        issue="LIV-82",
        mcp_status="needsAuth",
        environ={"HOME": str(tmp_path / "home")},
        mcp_auth_fn=spy,
    )
    spy.assert_not_called()
    assert result.token == "LINEAR_STAMP_FAIL"
    assert result.issue == "LIV-82"
    assert result.comment_id is None
    assert result.kind == "status"
    assert "needsAuth" in result.reason or "needs-auth" in result.reason.replace("_", "-")
    assert result.mcp_auth == "never"
    line = result.line()
    assert "LINEAR_STAMP_FAIL" in line
    assert "comment=none" in line
    assert "kind=status" in line
    assert "mcp_auth=never" in line
    assert "comment=" in line
    assert FAKE_KEY not in line
    for banned in ("comment_id=", "comment=uuid", "comment=cmt_"):
        assert banned not in line


def test_cli_unset_key_needs_auth_is_status_evidence_exit_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _strip_linear_env(monkeypatch, tmp_path)
    spy = MagicMock(name="mcp_auth")
    env = {"HOME": str(tmp_path / "home")}
    code, out, err = _run_main(
        ["--issue", "LIV-82", "--mcp-status", "needsAuth"],
        environ=env,
        mcp_auth_fn=spy,
    )
    combined = out + err
    spy.assert_not_called()
    assert code != 0
    assert "LINEAR_STAMP_FAIL" in combined
    assert "comment=none" in combined
    assert "kind=status" in combined
    assert "mcp_auth=never" in combined
    assert FAKE_KEY not in combined
    assert "lin_api_" not in combined
    assert "LINEAR_API_KEY=" not in combined


def test_subprocess_cli_with_process_env_stripped(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--issue",
            "LIV-82",
            "--mcp-status",
            "needsAuth",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "LINEAR_STAMP_FAIL" in blob
    assert "comment=none" in blob
    assert "kind=status" in blob
    assert "mcp_auth" in blob.lower()
    assert FAKE_KEY not in blob


def test_key_present_plus_needs_auth_is_not_stamp_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _strip_linear_env(monkeypatch, tmp_path)
    spy = MagicMock(name="mcp_auth")
    env = {"HOME": str(tmp_path / "home"), "LINEAR_API_KEY": FAKE_KEY}
    result = hive_linear_stamp(
        issue="LIV-82",
        mcp_status="needsAuth",
        environ=env,
        mcp_auth_fn=spy,
    )
    spy.assert_not_called()
    assert result.token != "LINEAR_STAMP_FAIL"
    assert result.comment_id is None
    assert result.kind == "status"
    assert FAKE_KEY not in result.line()
    code, out, err = _run_main(
        ["--issue", "LIV-82", "--mcp-status", "needsAuth"],
        environ=env,
        mcp_auth_fn=spy,
    )
    combined = out + err
    assert "LINEAR_STAMP_FAIL" not in combined
    assert FAKE_KEY not in combined
    assert "comment=none" in combined
    assert code != 0


def test_unset_key_ready_mcp_is_not_stamp_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _strip_linear_env(monkeypatch, tmp_path)
    spy = MagicMock(name="mcp_auth")
    result = hive_linear_stamp(
        issue="LIV-82",
        mcp_status="ready",
        environ={"HOME": str(tmp_path / "home")},
        mcp_auth_fn=spy,
    )
    spy.assert_not_called()
    assert result.token != "LINEAR_STAMP_FAIL"
    assert result.comment_id is None
    assert result.kind == "status"


def test_non_living_sky_is_refused_without_mcp_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _strip_linear_env(monkeypatch, tmp_path)
    spy = MagicMock(name="mcp_auth")
    code, out, err = _run_main(
        ["--issue", "BSM-1", "--mcp-status", "needsAuth"],
        environ={"HOME": str(tmp_path / "home")},
        mcp_auth_fn=spy,
    )
    spy.assert_not_called()
    combined = (out + err).lower()
    assert code != 0
    assert "not-living-sky" in combined or "black swan" in combined
    assert "comment=none" in (out + err)


def test_help_names_fail_token_and_forbids_mcp_auth() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    low = blob.lower()
    assert "LINEAR_STAMP_FAIL" in blob
    assert "needsAuth" in blob or "needsauth" in low
    assert "mcp_auth" in low
    assert "liv-82" in low
    assert "living sky" in low or "liv" in low
    assert "black swan" in low
    assert "--mcp-status" in blob
    assert INTERP_TOKEN not in blob


def test_docs_and_wiring_name_status_stamp_fail() -> None:
    doc = DOC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    arch = ARCH.read_text(encoding="utf-8")
    doctor = DOCTOR.read_text(encoding="utf-8")
    install = INSTALL.read_text(encoding="utf-8")
    assert "linear_stamp.py" in doc
    assert "LINEAR_STAMP_FAIL" in doc
    assert "needsAuth" in doc
    assert "mcp_auth" in doc.lower()
    assert "comment=none" in doc or "no comment id" in doc.lower()
    assert "linear_stamp.py" in readme
    assert "linear_stamp.py" in arch
    assert "scripts/linear_stamp.py" in doctor
    assert "scripts/linear_stamp.py" in install
    assert PRIVATE_GAME not in doc
    assert BLACK_SWAN.split()[0].lower() in doc.lower()
    leftover = LEFTOVER_INTERP.read_text(encoding="utf-8")
    assert "LINEAR_STAMP_FAIL" not in leftover
