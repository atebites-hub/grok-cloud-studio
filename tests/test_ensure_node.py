"""Node >= 22.13 bootstrap for @cursor/sdk via ensure-node.sh.

Unique remaining vs origin/main: GCS_NODE, PATH, and
~/.cache/gcs-node so sdk/run.sh can start. Unit tests use fake bins
and a stub curl — they must not download nodejs.org tarballs.

This slice is ensure-node only. Do not restack CLOUD_FORCE_REST
fallback (separate Extra High). Do not remint extraHighModel /
PAL-48 LIV-67. Never Bot CloudAgent.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENSURE = REPO / "scripts" / "cloud" / "sdk" / "ensure-node.sh"
RUN = REPO / "scripts" / "cloud" / "sdk" / "run.sh"
README = REPO / "scripts" / "cloud" / "README.md"
ENV_EXAMPLE = REPO / ".env.example"
FEATURE = REPO / "tests" / "features" / "ensure_node_bootstrap.feature"
COMMON_TS = REPO / "scripts" / "cloud" / "sdk" / "common.ts"

FAKE_KEY = "test-cursor-api-key-ensure-node-must-not-print"
BOT_CLOUDAGENT = "Bot" + " CloudAgent"
PRIVATE_GAME = "atebites-hub/" + "palemon"
BLACK_SWAN = "blackswan" + ".money"
DEFAULT_DIST = "v22.14.0"


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _fake_node(path: Path, version: str) -> Path:
    """Fake node that only implements -v / --version (no JS engine, no tarball)."""
    ver = version if version.startswith("v") else f"v{version}"
    return _write_exec(
        path,
        "#!/bin/sh\n"
        'case "$1" in\n'
        f'  -v|--version) printf "%s\\n" "{ver}"; exit 0 ;;\n'
        "esac\n"
        "exit 1\n",
    )


def _stub_refuse(bin_dir: Path, name: str, log: Path) -> Path:
    return _write_exec(
        bin_dir / name,
        "#!/bin/sh\n"
        f'printf "%s\\n" "{name} $*" >> "{log}"\n'
        f'echo "stub-{name}: refused (unit tests must not download tarballs)" >&2\n'
        "exit 1\n",
    )


def _isolated_env(
    tmp_path: Path,
    *,
    extra_path: list[Path] | None = None,
    extra: dict[str, str] | None = None,
) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)
    cache = tmp_path / "gcs-node-cache"
    cache.mkdir(parents=True, exist_ok=True)
    stub = tmp_path / "stub-bin"
    curl_log = tmp_path / "downloader.log"
    _stub_refuse(stub, "curl", curl_log)
    _stub_refuse(stub, "fnm", curl_log)
    _stub_refuse(stub, "volta", curl_log)
    parts = [*(str(p) for p in (extra_path or [])), str(stub), "/usr/bin", "/bin"]
    env = {
        "PATH": os.pathsep.join(parts),
        "HOME": str(home),
        "TMPDIR": str(tmpdir),
        "LC_ALL": "C",
        "TERM": "dumb",
        "GCS_ROOT": str(REPO),
        "GCS_NODE_CACHE": str(cache),
        "CURSOR_API_KEY": FAKE_KEY,
    }
    if extra:
        env.update(extra)
    return env, curl_log


def _run_ensure(
    env: dict[str, str], *, timeout: float = 8
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ENSURE)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _run_sdk(
    args: list[str], env: dict[str, str], *, timeout: float = 8
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUN), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _assert_no_secrets(proc: subprocess.CompletedProcess[str]) -> None:
    blob = proc.stdout + proc.stderr
    assert FAKE_KEY not in blob
    assert "CURSOR_API_KEY=" not in blob
    assert BOT_CLOUDAGENT not in blob
    assert PRIVATE_GAME not in blob
    assert BLACK_SWAN not in blob


def _assert_no_tarball(cache: Path, _log: Path) -> None:
    tarballs = list(cache.rglob("*.tar.gz"))
    assert tarballs == [], tarballs
    for node_bin in cache.rglob("bin/node"):
        text = node_bin.read_text(encoding="utf-8", errors="replace")
        assert "#!/bin/sh" in text


def test_feature_file_is_the_living_spec() -> None:
    assert FEATURE.is_file(), "missing tests/features/ensure_node_bootstrap.feature"
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert "Feature:" in text
    assert "ensure-node.sh" in text
    assert "GCS_NODE" in text
    assert "PATH" in text
    assert "~/.cache/gcs-node" in text or "gcs-node" in text
    assert "22.13" in text
    assert "tarball" in fold
    assert "fake" in fold
    assert "CLOUD_FORCE_REST" in text
    assert "Bot CloudAgent" in text or "bot cloudagent" in fold
    assert "run.sh" in text
    assert PRIVATE_GAME not in text
    assert "Scenario:" in text
    assert "Given " in text and "When " in text and "Then " in text


def test_ensure_node_and_run_sh_contract_on_disk() -> None:
    assert ENSURE.is_file()
    assert os.access(ENSURE, os.X_OK), "ensure-node.sh must be executable"
    src = ENSURE.read_text(encoding="utf-8")
    run_src = RUN.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    env_ex = ENV_EXAMPLE.read_text(encoding="utf-8")
    common = COMMON_TS.read_text(encoding="utf-8")
    assert "GCS_NODE" in src
    assert "GCS_NODE_CACHE" in src
    assert ".cache/gcs-node" in src
    assert "22" in src and "13" in src
    assert "CLOUD_FORCE_REST" not in src
    assert "extraHighModel" not in src
    assert "start-studio-bus" not in src
    assert "hermes-agent" not in src.lower()
    assert BOT_CLOUDAGENT not in src
    assert "ensure-node.sh" in run_src
    assert "NODE_BIN_DIR" in run_src
    assert 'export PATH="${NODE_BIN_DIR}:${PATH}"' in run_src
    assert "CLOUD_FORCE_REST" not in run_src
    assert "GCS_NODE=" in env_ex
    assert "GCS_NODE_CACHE=" in env_ex
    assert ">= 22.13" in readme or ">= **22.13**" in readme or "**>= 22.13**" in readme
    assert "fake" in readme.lower() or "unit test" in readme.lower()
    assert 'id: "grok-4.6"' in common
    assert 'value: "xhigh"' in common
    assert "cursor-grok-4.6-xhigh" not in common


def test_gcs_node_new_enough_wins_over_path_and_skips_download(tmp_path: Path) -> None:
    gcs = _fake_node(tmp_path / "override" / "node", "22.14.0")
    old_dir = tmp_path / "old-bin"
    _fake_node(old_dir / "node", "20.18.0")
    env, log = _isolated_env(tmp_path, extra_path=[old_dir], extra={"GCS_NODE": str(gcs)})
    proc = _run_ensure(env)
    _assert_no_secrets(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == str(gcs)
    assert not log.is_file() or log.read_text(encoding="utf-8") == ""
    _assert_no_tarball(Path(env["GCS_NODE_CACHE"]), log)


def test_gcs_node_too_old_falls_through_to_path(tmp_path: Path) -> None:
    old = _fake_node(tmp_path / "stale" / "node", "22.12.0")
    path_dir = tmp_path / "ok-bin"
    ok = _fake_node(path_dir / "node", "22.13.0")
    env, log = _isolated_env(
        tmp_path, extra_path=[path_dir], extra={"GCS_NODE": str(old)}
    )
    proc = _run_ensure(env)
    _assert_no_secrets(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == str(ok)
    assert not log.is_file() or "curl " not in log.read_text(encoding="utf-8")
    _assert_no_tarball(Path(env["GCS_NODE_CACHE"]), log)


def test_path_node_new_enough_when_gcs_node_unset(tmp_path: Path) -> None:
    path_dir = tmp_path / "ok-bin"
    ok = _fake_node(path_dir / "node", "22.13.1")
    env, log = _isolated_env(tmp_path, extra_path=[path_dir])
    proc = _run_ensure(env)
    _assert_no_secrets(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == str(ok)
    assert not log.is_file() or log.read_text(encoding="utf-8") == ""
    _assert_no_tarball(Path(env["GCS_NODE_CACHE"]), log)


def test_cache_hit_when_path_is_too_old(tmp_path: Path) -> None:
    old_dir = tmp_path / "old-bin"
    _fake_node(old_dir / "node", "20.18.0")
    env, log = _isolated_env(tmp_path, extra_path=[old_dir])
    cached = _fake_node(
        Path(env["GCS_NODE_CACHE"]) / DEFAULT_DIST / "bin" / "node", "22.14.0"
    )
    proc = _run_ensure(env)
    _assert_no_secrets(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == str(cached)
    assert not log.is_file() or "curl " not in log.read_text(encoding="utf-8")
    _assert_no_tarball(Path(env["GCS_NODE_CACHE"]), log)


def test_dist_ver_selects_cache_layout(tmp_path: Path) -> None:
    env, log = _isolated_env(tmp_path, extra={"GCS_NODE_DIST_VER": "v22.15.0"})
    cached = _fake_node(
        Path(env["GCS_NODE_CACHE"]) / "v22.15.0" / "bin" / "node", "22.15.0"
    )
    proc = _run_ensure(env)
    _assert_no_secrets(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == str(cached)
    assert not log.is_file() or "curl " not in log.read_text(encoding="utf-8")


def test_node_22_12_rejected_23_accepted(tmp_path: Path) -> None:
    too_old = _fake_node(tmp_path / "v2212" / "node", "22.12.99")
    env_old, log_old = _isolated_env(tmp_path / "old", extra={"GCS_NODE": str(too_old)})
    proc_old = _run_ensure(env_old)
    _assert_no_secrets(proc_old)
    assert proc_old.returncode == 75, proc_old.stdout + proc_old.stderr
    assert "CLOUD_SDK_ERR" in proc_old.stderr
    assert not (Path(env_old["GCS_NODE_CACHE"]) / DEFAULT_DIST / "bin" / "node").is_file()

    newer = _fake_node(tmp_path / "v23" / "node", "23.0.0")
    env_new, _log_new = _isolated_env(tmp_path / "new", extra={"GCS_NODE": str(newer)})
    proc_new = _run_ensure(env_new)
    _assert_no_secrets(proc_new)
    assert proc_new.returncode == 0, proc_new.stdout + proc_new.stderr
    assert proc_new.stdout.strip() == str(newer)
    assert log_old.is_file()
    assert "nodejs.org" in log_old.read_text(encoding="utf-8")


def test_missing_node_exits_75_without_storing_tarball(tmp_path: Path) -> None:
    env, log = _isolated_env(tmp_path)
    proc = _run_ensure(env)
    _assert_no_secrets(proc)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 75, blob
    assert "CLOUD_SDK_ERR" in proc.stderr
    assert FAKE_KEY not in blob
    cache = Path(env["GCS_NODE_CACHE"])
    assert list(cache.rglob("*.tar.gz")) == []
    assert not (cache / DEFAULT_DIST / "bin" / "node").exists()
    assert log.is_file()
    logged = log.read_text(encoding="utf-8")
    assert "curl " in logged
    assert "nodejs.org/dist" in logged
    assert DEFAULT_DIST in logged


def test_run_sh_help_does_not_touch_curl(tmp_path: Path) -> None:
    env, log = _isolated_env(tmp_path)
    proc = _run_sdk(["--help"], env)
    _assert_no_secrets(proc)
    assert proc.returncode == 2
    assert "usage: run.sh" in proc.stderr
    assert not log.is_file() or log.read_text(encoding="utf-8") == ""


def test_run_sh_list_exits_75_when_bootstrap_fails(tmp_path: Path) -> None:
    env, log = _isolated_env(tmp_path)
    proc = _run_sdk(["list"], env)
    _assert_no_secrets(proc)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 75, blob
    assert "CLOUD_SDK_ERR" in proc.stderr
    assert "22.13" in proc.stderr
    assert list(Path(env["GCS_NODE_CACHE"]).rglob("*.tar.gz")) == []
    assert log.is_file()
    assert "curl " in log.read_text(encoding="utf-8")
    assert "node_modules" not in blob.lower() or "install" not in blob.lower()
