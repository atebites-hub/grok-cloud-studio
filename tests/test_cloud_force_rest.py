"""CLOUD_FORCE_REST / GCS_CLOUD_BACKEND=rest skip SDK Agent.create.

Unique remaining vs origin/main: pytest must cover the force-REST Extra High
control-plane without relying only on CURSOR_API_BASE (mock URL). An explicit
CLOUD_SDK_RUN stub is still invoked when CURSOR_API_BASE is set, so exit-75
REST fallback is observable. CLOUD_FORCE_REST=1 and GCS_CLOUD_BACKEND=rest
must not call that stub (no double-create). Never Bot CloudAgent.

Do not remint extraHighModel / PAL-48 LIV-67. Do not clone LIV-41/67/85/82.
Do not vendor Hermes. Do not touch start-studio-bus.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from test_cloud_launch import (
    CLOUD,
    EXAMPLE_REPO,
    FAKE_KEY,
    LAUNCH,
    MockCursorAPI,
    REPO,
    _assert_extra_high_create,
    _run,
    _script_env,
)

COMMON = CLOUD / "_common.sh"
RUN_SH = CLOUD / "sdk" / "run.sh"
LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
COMMON_TS = CLOUD / "sdk" / "common.ts"
FEATURE = REPO / "tests" / "features" / "cloud_force_rest.feature"
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
PROMPT = "Implement the assigned outcome. Open a PR."
STUB_NAME = "gcs-eh-force-rest"
BOT_CLOUDAGENT = "Bot" + " CloudAgent"


def _create_posts(api: MockCursorAPI) -> list[dict[str, Any]]:
    return [p for p in api.posts if str(p.get("path") or "").rstrip("/") == "/v1/agents"]


def _write_sdk_stub(home: Path, *, rc: int) -> tuple[Path, Path]:
    """Stub sdk/run.sh. Logs Agent.create intent so tests can prove skip vs fallback."""
    stub = home / "cloud-sdk-run-stub.sh"
    log = home / "cloud-sdk-run-stub.log"
    stub.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f'printf "SDK_STUB_INVOKED cmd=%s\\n" "$*" >>"{log}"',
                'if [[ "${1:-}" == "launch" ]]; then',
                f'  printf "Agent.create\\n" >>"{log}"',
                "fi",
                f"exit {int(rc)}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub, log


def _stub_env(home: Path, base: str, stub: Path, **extra: str) -> dict[str, str]:
    env = _script_env(
        home,
        base,
        CURSOR_API_KEY=FAKE_KEY,
        CLOUD_SDK_RUN=str(stub),
        **extra,
    )
    if "CLOUD_FORCE_REST" not in extra:
        env.pop("CLOUD_FORCE_REST", None)
    if "GCS_CLOUD_BACKEND" not in extra:
        env.pop("GCS_CLOUD_BACKEND", None)
    env.pop("CLOUD_API_PARKED", None)
    return env


def _stub_log_text(log: Path) -> str:
    if not log.is_file():
        return ""
    return log.read_text(encoding="utf-8")


def test_feature_names_force_rest_without_api_base_only() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    assert "CLOUD_FORCE_REST" in text
    assert "GCS_CLOUD_BACKEND" in text
    assert "exit 75" in text
    assert "CURSOR_API_BASE" in text
    assert "without SDK Agent.create" in text or "without calling SDK Agent.create" in text
    assert BOT_CLOUDAGENT in text or "Never Bot CloudAgent" in text


def test_common_sh_force_rest_is_not_api_base_only() -> None:
    src = COMMON.read_text(encoding="utf-8")
    start = src.find("cloud_prefer_rest()")
    end = src.find("_cloud_sdk_try()")
    body = src[start:end]
    assert start != -1 and end != -1 and end > start
    force_at = body.find("CLOUD_FORCE_REST")
    backend_at = body.find("GCS_CLOUD_BACKEND")
    base_at = body.find("CURSOR_API_BASE")
    assert force_at != -1
    assert backend_at != -1
    assert force_at < base_at
    assert backend_at < base_at
    try_body = src[end:]
    assert "-eq 75" in try_body
    assert "double-create" in src
    assert "CLOUD_SDK_EXPLICIT" in src
    assert "Never Bot CloudAgent" in src


def test_launch_ts_still_pins_grok_xhigh_not_reminted() -> None:
    """Keep-out: this slice does not remint extraHighModel / PAL-48 LIV-67."""
    common = COMMON_TS.read_text(encoding="utf-8")
    launch = LAUNCH_TS.read_text(encoding="utf-8")
    assert 'id: "grok-4.6"' in common
    assert 'value: "xhigh"' in common
    assert 'value: "false"' in common
    assert "extraHighModel()" in launch
    assert "Agent.create" in launch
    assert "sdkCreateFailExitCode" in launch
    assert "process.exit(75)" in RUN_SH.read_text(encoding="utf-8") or "exit 75" in RUN_SH.read_text(
        encoding="utf-8"
    )


def test_does_not_touch_studio_bus_or_vendor_hermes() -> None:
    bus = BUS.read_text(encoding="utf-8")
    assert "start-studio-bus" in bus or "GCS_BOT_BRIDGE" in bus
    hermes = REPO / "vendor" / "hermes-agent"
    assert not hermes.exists()


def _prefer_rest_probe(*, force: str = "", backend: str = "", api_base: str = "") -> str:
    script = r"""
set -euo pipefail
unset CURSOR_API_BASE GCS_CLOUD_BACKEND CLOUD_FORCE_REST || true
if [[ -n "${PROBE_FORCE:-}" ]]; then export CLOUD_FORCE_REST="$PROBE_FORCE"; fi
if [[ -n "${PROBE_BACKEND:-}" ]]; then export GCS_CLOUD_BACKEND="$PROBE_BACKEND"; fi
if [[ -n "${PROBE_BASE:-}" ]]; then export CURSOR_API_BASE="$PROBE_BASE"; fi
# shellcheck source=scripts/cloud/_common.sh
source scripts/cloud/_common.sh
if cloud_prefer_rest; then
  printf 'PREFER_REST=yes\n'
else
  printf 'PREFER_REST=no\n'
fi
"""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "GCS_ROOT": str(REPO),
        "PROBE_FORCE": force,
        "PROBE_BACKEND": backend,
        "PROBE_BASE": api_base,
    }
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert FAKE_KEY not in blob
    return proc.stdout


def test_prefer_rest_cloud_force_rest_without_cursor_api_base() -> None:
    """FORCE_REST must select REST even when CURSOR_API_BASE is unset."""
    out = _prefer_rest_probe(force="1")
    assert "PREFER_REST=yes" in out


def test_prefer_rest_gcs_cloud_backend_rest_without_cursor_api_base() -> None:
    out = _prefer_rest_probe(backend="rest")
    assert "PREFER_REST=yes" in out


def test_prefer_rest_neither_force_flag_without_cursor_api_base() -> None:
    out = _prefer_rest_probe()
    assert "PREFER_REST=no" in out


def test_launch_cloud_force_rest_skips_sdk_stub(
    tmp_path: Path,
) -> None:
    stub, log = _write_sdk_stub(tmp_path, rc=0)
    with MockCursorAPI(create_http=201) as api:
        env = _stub_env(tmp_path, api.base, stub, CLOUD_FORCE_REST="1")
        proc = _run(LAUNCH, ["--name", STUB_NAME, PROMPT], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_LAUNCH_ERR" not in proc.stdout
    assert "CLOUD_SDK_FALLBACK: REST requested (CLOUD_FORCE_REST or GCS_CLOUD_BACKEND=rest)" in (
        proc.stderr
    )
    posts = _create_posts(api)
    assert len(posts) == 1, api.posts
    _assert_extra_high_create(posts[0]["body"], repo=EXAMPLE_REPO, name=STUB_NAME)
    log_text = _stub_log_text(log)
    assert "SDK_STUB_INVOKED" not in log_text
    assert "Agent.create" not in log_text
    assert FAKE_KEY not in blob
    assert BOT_CLOUDAGENT not in blob


def test_launch_gcs_cloud_backend_rest_skips_sdk_stub(tmp_path: Path) -> None:
    stub, log = _write_sdk_stub(tmp_path, rc=0)
    with MockCursorAPI(create_http=201) as api:
        env = _stub_env(tmp_path, api.base, stub, GCS_CLOUD_BACKEND="rest")
        proc = _run(LAUNCH, ["--name", STUB_NAME, PROMPT], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_SDK_FALLBACK: REST requested (CLOUD_FORCE_REST or GCS_CLOUD_BACKEND=rest)" in (
        proc.stderr
    )
    posts = _create_posts(api)
    assert len(posts) == 1, api.posts
    _assert_extra_high_create(posts[0]["body"], repo=EXAMPLE_REPO, name=STUB_NAME)
    log_text = _stub_log_text(log)
    assert "SDK_STUB_INVOKED" not in log_text
    assert "Agent.create" not in log_text
    assert FAKE_KEY not in blob


def test_launch_run_sh_exit_75_rest_falls_back(tmp_path: Path) -> None:
    """Explicit CLOUD_SDK_RUN stub is tried even with CURSOR_API_BASE; 75 → REST once."""
    stub, log = _write_sdk_stub(tmp_path, rc=75)
    with MockCursorAPI(create_http=201) as api:
        env = _stub_env(tmp_path, api.base, stub)
        proc = _run(LAUNCH, ["--name", STUB_NAME, PROMPT], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_SDK_FALLBACK: SDK unavailable (exit 75); using REST curl" in proc.stderr
    posts = _create_posts(api)
    assert len(posts) == 1, api.posts
    _assert_extra_high_create(posts[0]["body"], repo=EXAMPLE_REPO, name=STUB_NAME)
    log_text = _stub_log_text(log)
    assert "SDK_STUB_INVOKED" in log_text
    assert "Agent.create" in log_text
    assert FAKE_KEY not in blob


def test_launch_sdk_exit_1_does_not_double_create(tmp_path: Path) -> None:
    """Non-75 SDK failure must not POST /v1/agents (no double-create)."""
    stub, log = _write_sdk_stub(tmp_path, rc=1)
    with MockCursorAPI(create_http=201) as api:
        env = _stub_env(tmp_path, api.base, stub)
        proc = _run(LAUNCH, ["--name", STUB_NAME, PROMPT], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 1, blob
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    assert not _create_posts(api), api.posts
    log_text = _stub_log_text(log)
    assert "SDK_STUB_INVOKED" in log_text
    assert FAKE_KEY not in blob


def test_force_rest_wins_over_exit_75_stub(tmp_path: Path) -> None:
    """FORCE_REST must skip the stub entirely (stub exit 75 would otherwise create via REST)."""
    stub, log = _write_sdk_stub(tmp_path, rc=75)
    with MockCursorAPI(create_http=201) as api:
        env = _stub_env(tmp_path, api.base, stub, CLOUD_FORCE_REST="1")
        proc = _run(LAUNCH, ["--name", STUB_NAME, PROMPT], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "REST requested (CLOUD_FORCE_REST or GCS_CLOUD_BACKEND=rest)" in proc.stderr
    assert "SDK unavailable (exit 75)" not in proc.stderr
    assert len(_create_posts(api)) == 1
    assert "SDK_STUB_INVOKED" not in _stub_log_text(log)
    assert FAKE_KEY not in blob
