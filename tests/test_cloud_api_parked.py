"""launch-cloud-extra-high.sh fail-closes when CLOUD_API_PARKED is set.

Park sources: env, $GCS_A2A_STATE/CLOUD_API_PARKED, or a hive-beats marker.
No Extra High create. Never recommends a Bot CloudAgent path.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from test_cloud_launch import FAKE_KEY, LAUNCH, MockCursorAPI, REPO, _run, _script_env

CLOUD = REPO / "scripts" / "cloud"
API_PARKED = CLOUD / "api_parked.py"
PROMPT = "Implement the assigned outcome. Open a PR."

_BOT_RECOMMEND = (
    "use Bot CloudAgent",
    "Bot CloudAgent instead",
    "launch Bot CloudAgent",
    "spawn Bot CloudAgent",
    "Bot CloudAgent path",
    "grok --resume for Cloud create",
)


def _load_api_parked() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_api_parked", API_PARKED)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _isolated_env(home: Path, base: str, **extra: str) -> dict[str, str]:
    state = home / "a2a-state"
    archive = home / "studio-archive"
    state.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)
    return _script_env(
        home,
        base,
        GCS_A2A_STATE=str(state),
        GCS_STUDIO_ARCHIVE=str(archive),
        **extra,
    )


def _create_posts(api: MockCursorAPI) -> list[dict[str, Any]]:
    return [p for p in api.posts if str(p.get("path") or "").rstrip("/") == "/v1/agents"]


def _assert_park_refuse(proc: Any, api: MockCursorAPI) -> None:
    blob = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode != 0, blob
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert "reason=CLOUD_API_PARKED" in proc.stdout
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    assert not _create_posts(api), api.posts
    assert FAKE_KEY not in blob
    lower = blob.lower()
    for phrase in _BOT_RECOMMEND:
        assert phrase.lower() not in lower, blob
    # Prohibition is allowed; a recommended Bot grunt path is not.
    assert "never Bot CloudAgent" in blob


def test_env_truthy_is_parked(monkeypatch: Any) -> None:
    parked = _load_api_parked()
    monkeypatch.setenv("CLOUD_API_PARKED", "1")
    monkeypatch.delenv("GCS_A2A_STATE", raising=False)
    monkeypatch.delenv("PALEMON_A2A_STATE", raising=False)
    monkeypatch.delenv("GCS_STUDIO_ARCHIVE", raising=False)
    monkeypatch.delenv("GCS_HIVE_BEATS", raising=False)
    monkeypatch.delenv("GCS_ROOT", raising=False)
    assert parked.parked_source() == "env"
    assert parked.parked() is True


def test_env_falsey_is_not_parked(monkeypatch: Any) -> None:
    parked = _load_api_parked()
    monkeypatch.setenv("CLOUD_API_PARKED", "0")
    monkeypatch.delenv("GCS_A2A_STATE", raising=False)
    monkeypatch.delenv("PALEMON_A2A_STATE", raising=False)
    monkeypatch.delenv("GCS_STUDIO_ARCHIVE", raising=False)
    monkeypatch.delenv("GCS_HIVE_BEATS", raising=False)
    monkeypatch.delenv("GCS_ROOT", raising=False)
    assert parked.parked_source() is None
    assert parked.parked() is False


def test_state_file_is_parked(tmp_path: Path, monkeypatch: Any) -> None:
    parked = _load_api_parked()
    state = tmp_path / "a2a-state"
    marker = state / "CLOUD_API_PARKED"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("parked\n", encoding="utf-8")
    monkeypatch.delenv("CLOUD_API_PARKED", raising=False)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.delenv("PALEMON_A2A_STATE", raising=False)
    monkeypatch.delenv("GCS_STUDIO_ARCHIVE", raising=False)
    monkeypatch.delenv("GCS_HIVE_BEATS", raising=False)
    assert parked.parked_source() == "state"
    assert parked.parked() is True


def test_hive_beats_archive_marker_is_parked(tmp_path: Path, monkeypatch: Any) -> None:
    parked = _load_api_parked()
    archive = tmp_path / "studio-archive"
    marker = archive / "hive-beats" / "CLOUD_API_PARKED"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("1\n", encoding="utf-8")
    monkeypatch.delenv("CLOUD_API_PARKED", raising=False)
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "empty-state"))
    monkeypatch.setenv("GCS_STUDIO_ARCHIVE", str(archive))
    monkeypatch.delenv("GCS_HIVE_BEATS", raising=False)
    assert parked.parked_source() == "hive-beats"
    assert parked.parked() is True


def test_hive_beats_state_dir_marker_is_parked(tmp_path: Path, monkeypatch: Any) -> None:
    parked = _load_api_parked()
    state = tmp_path / "a2a-state"
    marker = state / "hive-beats" / "CLOUD_API_PARKED"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")
    monkeypatch.delenv("CLOUD_API_PARKED", raising=False)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_STUDIO_ARCHIVE", str(tmp_path / "empty-archive"))
    monkeypatch.delenv("GCS_HIVE_BEATS", raising=False)
    assert parked.parked_source() == "hive-beats"


def test_hive_beats_env_override_is_parked(tmp_path: Path, monkeypatch: Any) -> None:
    parked = _load_api_parked()
    hive = tmp_path / "hive-beats"
    marker = hive / "CLOUD_API_PARKED"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("parked\n", encoding="utf-8")
    monkeypatch.delenv("CLOUD_API_PARKED", raising=False)
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "empty-state"))
    monkeypatch.setenv("GCS_STUDIO_ARCHIVE", str(tmp_path / "empty-archive"))
    monkeypatch.setenv("GCS_HIVE_BEATS", str(hive))
    assert parked.parked_source() == "hive-beats"


def test_launch_env_parked_does_not_create(tmp_path: Path) -> None:
    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["--name", "gcs-park-env", PROMPT],
            _isolated_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY, CLOUD_API_PARKED="1"),
        )
    _assert_park_refuse(proc, api)
    assert "source=env" in proc.stderr


def test_launch_state_file_parked_does_not_create(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path, "http://127.0.0.1:9", CURSOR_API_KEY=FAKE_KEY)
    marker = Path(env["GCS_A2A_STATE"]) / "CLOUD_API_PARKED"
    marker.write_text("parked\n", encoding="utf-8")
    with MockCursorAPI(create_http=201) as api:
        env = _isolated_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(LAUNCH, ["--name", "gcs-park-state", PROMPT], env)
    _assert_park_refuse(proc, api)
    assert "source=state" in proc.stderr


def test_launch_hive_beats_marker_does_not_create(tmp_path: Path) -> None:
    with MockCursorAPI(create_http=201) as api:
        env = _isolated_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        marker = Path(env["GCS_STUDIO_ARCHIVE"]) / "hive-beats" / "CLOUD_API_PARKED"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1\n", encoding="utf-8")
        proc = _run(LAUNCH, ["--name", "gcs-park-hive", PROMPT], env)
    _assert_park_refuse(proc, api)
    assert "source=hive-beats" in proc.stderr


def test_launch_parked_without_api_key_still_park_err(tmp_path: Path) -> None:
    """Park fail-closes before auth so Directors see CLOUD_API_PARKED, not missing key."""
    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["--name", "gcs-park-nokey", PROMPT],
            _isolated_env(tmp_path, api.base, CLOUD_API_PARKED="true"),
        )
    _assert_park_refuse(proc, api)
    assert "CURSOR_API_KEY" not in proc.stderr
    assert "CURSOR_API_KEY" not in proc.stdout


def test_launch_not_parked_still_creates(tmp_path: Path) -> None:
    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["--name", "gcs-park-clear", PROMPT],
            _isolated_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY, CLOUD_API_PARKED="0"),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_LAUNCH_ERR" not in proc.stdout
    assert _create_posts(api)


def test_launch_script_probes_park_before_sdk_or_rest() -> None:
    src = LAUNCH.read_text(encoding="utf-8")
    park_at = src.find("api_parked.py")
    sdk_at = src.find("cloud_sdk_exec")
    rest_at = src.find("POST /v1/agents")
    auth_at = src.find("cloud_load_auth")
    assert park_at != -1
    assert sdk_at != -1
    assert rest_at != -1
    assert auth_at != -1
    assert park_at < auth_at
    assert park_at < sdk_at
    assert "CLOUD_API_PARKED" in src
    assert "never Bot CloudAgent" in src
    assert "Bot CloudAgent instead" not in src
    assert "use Bot CloudAgent" not in src


def test_helper_cli_prints_source(capsys: Any, monkeypatch: Any) -> None:
    parked = _load_api_parked()
    monkeypatch.setenv("CLOUD_API_PARKED", "1")
    monkeypatch.delenv("GCS_A2A_STATE", raising=False)
    monkeypatch.delenv("PALEMON_A2A_STATE", raising=False)
    monkeypatch.delenv("GCS_STUDIO_ARCHIVE", raising=False)
    monkeypatch.delenv("GCS_HIVE_BEATS", raising=False)
    monkeypatch.delenv("GCS_ROOT", raising=False)
    rc = parked.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == "CLOUD_API_PARKED source=env"
