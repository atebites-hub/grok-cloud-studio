"""BDD example (LIV-67): first agent.send on GCS is grok-4.6 xhigh, not Auto.

Feature: GCS Extra High first send
  Jay saw Claude/Gemini because create pinned grok-4.6 then unpinned
  `agent.send(prompt)` let dashboard Auto pick Sonnet/Gemini. Silently
  ignoring CURSOR_CLOUD_MODEL=auto and still launching is also a fail.

  Scenario: first agent.send is grok-4.6 xhigh, not dashboard Auto
    Given Extra High launch on GCS
    When CURSOR_CLOUD_MODEL is unset or grok-4.6
    Then the posted model is grok-4.6 with effort=xhigh and fast=false
    And the SDK first send is sendPinned, not unpinned Auto
    And Grok Bot is never launched as a CloudAgent

  Scenario: non-grok CURSOR_CLOUD_MODEL cannot create or send
    Given CURSOR_CLOUD_MODEL is auto / claude-opus-5 / sonnet / gemini / composer
    When create or follow-up send is issued
    Then the launcher fails closed and does not POST
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from test_cloud_launch import (
    CLOUD,
    EXAMPLE_REPO,
    FAKE_KEY,
    FOLLOWUP,
    LAUNCH,
    NON_GROK_CURSOR_CLOUD_MODELS,
    MockCursorAPI,
    _run,
    _script_env,
    _ts_fn_body,
)

LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
FOLLOWUP_TS = CLOUD / "sdk" / "followup.ts"
COMMON_TS = CLOUD / "sdk" / "common.ts"
EXTRA_HIGH = CLOUD / "extra_high_model.py"
BOT_CLOUDAGENT = "Grok Bot " + "CloudAgent"

_UNPINNED_SEND_RE = re.compile(r"agent\.send\(\s*prompt\s*\)\s*;")
_FIRST_SEND_RE = re.compile(
    r"\b(?:await\s+)?(sendPinned\s*\([^;]+\)|agent\.send\s*\([^;]+\))",
)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _first_send_after_create(src: str) -> str:
    idx = src.index("Agent.create")
    match = _FIRST_SEND_RE.search(src[idx:])
    assert match is not None, "no agent.send / sendPinned after Agent.create"
    return re.sub(r"\s+", " ", match.group(1).strip())


def test_bdd_first_agent_send_on_gcs_is_grok_46_xhigh_not_dashboard_auto(
    tmp_path: Path,
) -> None:
    """Executable spec: first send is grok-4.6 xhigh, never dashboard Auto."""
    launch_ts = LAUNCH_TS.read_text(encoding="utf-8")
    followup_ts = FOLLOWUP_TS.read_text(encoding="utf-8")
    common_ts = COMMON_TS.read_text(encoding="utf-8")
    pin = _load(EXTRA_HIGH, "gcs_extra_high_first_send")

    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["--name", "bdd-first-send", "Implement the assigned outcome. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_LAUNCH_ERR" not in proc.stdout
    assert FAKE_KEY not in proc.stdout + proc.stderr
    assert api.posts, "first send/create never reached the API"
    body = api.posts[0]["body"]
    assert body["model"]["id"] == "grok-4.6"
    assert body["model"]["id"] != "auto"
    params = {(p["id"], p["value"]) for p in body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params

    first = _first_send_after_create(launch_ts)
    assert first.startswith("sendPinned("), first
    assert "sendPinned(agent, prompt)" in first
    assert _UNPINNED_SEND_RE.search(launch_ts) is None, launch_ts
    assert _UNPINNED_SEND_RE.search(followup_ts) is None, followup_ts
    assert "return agent.send(prompt, { model });" in common_ts
    extra = _ts_fn_body(common_ts, "extraHighModel")
    send_body = _ts_fn_body(common_ts, "sendPinned")
    assert "extraHighModel()" in common_ts
    assert "CURSOR_CLOUD_MODEL" not in extra
    assert "CURSOR_CLOUD_EFFORT" not in extra
    assert "CURSOR_CLOUD_EFFORT" not in common_ts
    assert "requirePinnedCloudModelEnv()" in send_body
    assert "requirePinnedCloudModelEnv()" in launch_ts
    assert "requirePinnedCloudModelEnv()" in followup_ts

    assert pin.is_extra_high_model("auto") is False
    assert pin.is_extra_high_model("auto-smart") is False
    assert pin.extra_high_model_object()["id"] == "grok-4.6"
    assert pin.cursor_cloud_model_env_ok()[0] is True
    assert BOT_CLOUDAGENT not in launch_ts
    assert BOT_CLOUDAGENT not in common_ts
    assert "GCS_BOT_AGENT_ID" not in launch_ts
    assert EXAMPLE_REPO in body["repos"][0]["url"]


def test_bdd_auto_opus_sonnet_env_cannot_create_or_send(tmp_path: Path) -> None:
    """Fail closed: dashboard Auto / Opus / Sonnet env must not launch or send."""
    pin = _load(EXTRA_HIGH, "gcs_extra_high_env_reject")
    for model_id in ("auto", "claude-opus-5", "claude-4-sonnet"):
        assert model_id in NON_GROK_CURSOR_CLOUD_MODELS
        assert pin.is_extra_high_model(model_id) is False
        with MockCursorAPI(create_http=201) as api:
            created = _run(
                LAUNCH,
                ["--name", "bdd-reject", "Implement the assigned outcome. Open a PR."],
                _script_env(
                    tmp_path,
                    api.base,
                    CURSOR_API_KEY=FAKE_KEY,
                    CURSOR_CLOUD_MODEL=model_id,
                ),
            )
            sent = _run(
                FOLLOWUP,
                ["bc-mock", "Keep going."],
                _script_env(
                    tmp_path,
                    api.base,
                    CURSOR_API_KEY=FAKE_KEY,
                    CURSOR_CLOUD_MODEL=model_id,
                ),
            )
        assert created.returncode != 0, model_id + created.stdout + created.stderr
        assert "CLOUD_LAUNCH_ERR" in created.stdout, model_id
        assert "CLOUD_LAUNCH_OK" not in created.stdout, model_id
        assert sent.returncode != 0, model_id + sent.stdout + sent.stderr
        assert "CLOUD_FOLLOWUP_ERR" in sent.stdout, model_id
        assert "CLOUD_FOLLOWUP_OK" not in sent.stdout, model_id
        assert not api.posts, f"{model_id} still posted: {api.posts}"
