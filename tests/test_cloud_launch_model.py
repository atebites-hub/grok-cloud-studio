"""Prove Extra High launch always pins grok-4.6 xhigh fast=false.

Inspects REST POST fields and SDK Agent.create / send fields (not source
comments). Env overrides must not win. Never Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urljoin
from urllib.request import pathname2url

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
CLOUD = REPO / "scripts" / "cloud"
FOLLOWUP = CLOUD / "followup.sh"
LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
COMMON_TS = CLOUD / "sdk" / "common.ts"
FOLLOWUP_TS = CLOUD / "sdk" / "followup.ts"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"
FAKE_KEY = "test-cursor-api-key"
EXAMPLE_REPO = "https://github.com/atebites-hub/grok-cloud-studio"
BOT_ID = "bc-bot-orchestrator"
EXTRA_HIGH_ID = "grok-4.6"
EXTRA_HIGH_EFFORT = "xhigh"
EXTRA_HIGH_FAST = "false"
OVERRIDE_MODEL = "claude-4-sonnet"
OVERRIDE_EFFORT = "low"

_HELPERS_PATH = Path(__file__).resolve().parent / "test_cloud_launch.py"


def _load_helpers() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_cloud_launch_helpers", _HELPERS_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_helpers = _load_helpers()
MockCursorAPI = _helpers.MockCursorAPI
_run = _helpers._run
_script_env = _helpers._script_env


def _file_url(path: Path) -> str:
    return urljoin("file:", pathname2url(str(path.resolve())))


def _assert_extra_high_model(model: dict[str, Any]) -> None:
    assert model["id"] == EXTRA_HIGH_ID, model
    params = {(str(p["id"]), str(p["value"])) for p in model["params"]}
    assert ("effort", EXTRA_HIGH_EFFORT) in params, model
    assert ("fast", EXTRA_HIGH_FAST) in params, model
    assert model["id"] != OVERRIDE_MODEL
    assert ("effort", OVERRIDE_EFFORT) not in params
    assert ("fast", "true") not in params


REGISTER_JS = """\\
import { register } from "node:module";
register(process.env.GCS_FAKE_SDK_LOADER, import.meta.url);
"""

LOADER_JS = """\\
export async function resolve(specifier, context, nextResolve) {
  if (specifier === "@cursor/sdk") {
    return { shortCircuit: true, url: process.env.GCS_FAKE_SDK_URL };
  }
  return nextResolve(specifier, context);
}
"""

FAKE_SDK_JS = """\\
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const logPath = process.env.GCS_SDK_FIELD_LOG || "";

function record(patch) {
  let prev = {};
  if (logPath && existsSync(logPath)) {
    try {
      prev = JSON.parse(readFileSync(logPath, "utf8"));
    } catch {
      prev = {};
    }
  }
  const next = { ...prev, ...patch, argv: process.argv };
  if (logPath) {
    writeFileSync(logPath, JSON.stringify(next));
  }
}

export class Agent {
  agentId = "bc-sdk-mock";
  static async create(opts) {
    record({ create: opts });
    return new Agent();
  }
  async send(prompt, options) {
    record({ send: { prompt, options: options ?? null } });
    return { id: "run-sdk-mock", status: "CREATING" };
  }
  async [Symbol.asyncDispose]() {}
}
"""


def _sdk_env(home: Path, log: Path, register: Path, loader: Path, fake_sdk: Path) -> dict[str, str]:
    path = os.environ.get("PATH", "/usr/bin:/bin")
    node_dir = str(Path(os.environ.get("GCS_NODE") or "/exec-daemon").parent)
    if Path("/exec-daemon/node").is_file() and node_dir not in path.split(":"):
        path = f"/exec-daemon:{path}"
    return {
        "PATH": path,
        "HOME": str(home),
        "TMPDIR": str(home),
        "CURSOR_API_KEY": FAKE_KEY,
        "GCS_CLOUD_REPO": EXAMPLE_REPO,
        "GCS_CLOUD_REF": "main",
        "GCS_SPAWN_WAITER": "0",
        "CLOUD_SPAWN_WAITER": "0",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "NODE_NO_WARNINGS": "1",
        "GCS_SDK_FIELD_LOG": str(log),
        "GCS_FAKE_SDK_LOADER": _file_url(loader),
        "GCS_FAKE_SDK_URL": _file_url(fake_sdk),
        "CURSOR_CLOUD_MODEL": OVERRIDE_MODEL,
        "CURSOR_CLOUD_EFFORT": OVERRIDE_EFFORT,
        "GCS_BOT_AGENT_ID": BOT_ID,
    }


def _run_sdk_launch(tmp_path: Path, prompt: str, name: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    register = tmp_path / "register.mjs"
    loader = tmp_path / "loader.mjs"
    fake_sdk = tmp_path / "fake-sdk.mjs"
    log = tmp_path / "sdk-fields.json"
    register.write_text(REGISTER_JS, encoding="utf-8")
    loader.write_text(LOADER_JS, encoding="utf-8")
    fake_sdk.write_text(FAKE_SDK_JS, encoding="utf-8")
    env = _sdk_env(tmp_path, log, register, loader, fake_sdk)
    proc = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--no-warnings",
            f"--import={_file_url(register)}",
            str(LAUNCH_TS),
            prompt,
            name,
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    payload: dict[str, Any] = {}
    if log.is_file() and log.read_text(encoding="utf-8").strip():
        payload = json.loads(log.read_text(encoding="utf-8"))
    return proc, payload


def test_rest_launch_posts_grok_46_xhigh_fast_false_despite_env_override(tmp_path: Path) -> None:
    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["--name", "gcs-eh-pin", "Implement the assigned outcome. Open a PR."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                CURSOR_CLOUD_MODEL=OVERRIDE_MODEL,
                CURSOR_CLOUD_EFFORT=OVERRIDE_EFFORT,
                GCS_BOT_AGENT_ID=BOT_ID,
            ),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    body = api.posts[0]["body"]
    _assert_extra_high_model(body["model"])
    assert BOT_ID not in json.dumps(body)
    assert body.get("id") != BOT_ID
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_sdk_create_fields_are_grok_46_xhigh_fast_false_despite_env(tmp_path: Path) -> None:
    prompt = "Implement the assigned outcome. Open a PR."
    name = "gcs-sdk-pin"
    proc, payload = _run_sdk_launch(tmp_path, prompt, name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    create = payload["create"]
    _assert_extra_high_model(create["model"])
    assert create.get("name") == name
    assert BOT_ID not in json.dumps(create)
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_sdk_launch_argv_is_prompt_and_name_not_model(tmp_path: Path) -> None:
    prompt = "Implement the assigned outcome. Open a PR."
    name = "gcs-sdk-argv"
    proc, payload = _run_sdk_launch(tmp_path, prompt, name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    argv = [str(a) for a in payload["argv"]]
    assert prompt in argv
    assert name in argv
    assert "--model" not in argv
    assert OVERRIDE_MODEL not in argv
    assert EXTRA_HIGH_ID not in argv
    assert EXTRA_HIGH_EFFORT not in argv
    launch_sh = LAUNCH.read_text(encoding="utf-8")
    assert 'cloud_sdk_exec launch "$prompt" "$name"' in launch_sh
    assert "--model" not in launch_sh


def test_sdk_first_send_pins_extra_high_model(tmp_path: Path) -> None:
    prompt = "Implement the assigned outcome. Open a PR."
    proc, payload = _run_sdk_launch(tmp_path, prompt, "gcs-sdk-send")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    send = payload["send"]
    assert send["prompt"] == prompt
    assert send["options"] is not None, "first send must pass model; unpinned send lets Auto pick"
    _assert_extra_high_model(send["options"]["model"])


def test_extra_high_model_source_is_hard_pinned() -> None:
    common = COMMON_TS.read_text(encoding="utf-8")
    launch = LAUNCH_TS.read_text(encoding="utf-8")
    rest = LAUNCH.read_text(encoding="utf-8")
    assert "function extraHighModel" in common
    assert "CURSOR_CLOUD_MODEL" not in common
    assert "CURSOR_CLOUD_EFFORT" not in common
    assert f'id: "{EXTRA_HIGH_ID}"' in common or f'id: "{EXTRA_HIGH_ID}"' in rest
    assert EXTRA_HIGH_ID in common
    assert EXTRA_HIGH_EFFORT in common
    assert EXTRA_HIGH_FAST in common
    assert "extraHighModel()" in launch
    assert '"id": "grok-4.6"' in rest
    assert '{"id": "effort", "value": "xhigh"}' in rest
    assert '{"id": "fast", "value": "false"}' in rest


def test_launch_never_targets_bot_cloud_agent() -> None:
    launch_sh = LAUNCH.read_text(encoding="utf-8")
    launch_ts = LAUNCH_TS.read_text(encoding="utf-8")
    common = COMMON_TS.read_text(encoding="utf-8")
    for text in (launch_sh, launch_ts, common):
        assert "GCS_BOT_AGENT_ID" not in text
        assert "bot-agents.json" not in text
        assert "REPLACE_WITH_YOUR_GROK_BOT_AGENT_ID" not in text
    footer = FOOTER.read_text(encoding="utf-8")
    assert "Bot CloudAgent" in footer or "Grok Bot CloudAgent" in footer
    assert EXTRA_HIGH_ID in footer
    assert EXTRA_HIGH_EFFORT in footer
    assert EXTRA_HIGH_FAST in footer or "fast=false" in footer


def test_docs_living_sky_liv_never_bot_or_black_swan() -> None:
    cloud_doc = CLOUD_DOC.read_text(encoding="utf-8")
    readme = CLOUD_README.read_text(encoding="utf-8")
    for label, text in (("docs/CLOUD.md", cloud_doc), ("scripts/cloud/README.md", readme)):
        low = text.lower()
        assert "living sky" in low, label
        assert "liv" in low, label
        assert "black swan" in low, f"{label} must say NEVER Black Swan"
        assert "never" in low and "bot" in low and "cloudagent" in low.replace(" ", ""), label
        assert EXTRA_HIGH_ID in text, label
        assert EXTRA_HIGH_EFFORT in text, label
        assert "fast=false" in text or 'fast", "value": "false"' in text, label


def test_rest_followup_posts_grok_46_xhigh_fast_false_despite_env_override(tmp_path: Path) -> None:
    with MockCursorAPI(followup_http=201) as api:
        proc = _run(
            FOLLOWUP,
            ["bc-mock", "Keep the PR; pin stays Extra High."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                CURSOR_CLOUD_MODEL=OVERRIDE_MODEL,
                CURSOR_CLOUD_EFFORT=OVERRIDE_EFFORT,
                GCS_BOT_AGENT_ID=BOT_ID,
            ),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_FOLLOWUP_OK" in proc.stdout
    runs = [p for p in api.posts if str(p["path"]).endswith("/runs")]
    assert len(runs) == 1, api.posts
    body = runs[0]["body"]
    _assert_extra_high_model(body["model"])
    assert body["prompt"]["text"] == "Keep the PR; pin stays Extra High."
    assert BOT_ID not in json.dumps(body)
    assert FAKE_KEY not in proc.stdout + proc.stderr
    followup_src = FOLLOWUP.read_text(encoding="utf-8")
    followup_ts = FOLLOWUP_TS.read_text(encoding="utf-8")
    assert "sendPinned" in followup_ts
    assert '"id": "grok-4.6"' in followup_src
    assert '{"id": "effort", "value": "xhigh"}' in followup_src
    assert '{"id": "fast", "value": "false"}' in followup_src


def test_pin_does_not_vendor_hermes_or_launch_bot() -> None:
    """Follow-up law: never vendor Hermes; never Bot CloudAgent."""
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert not (REPO / "vendor" / "hermes").exists()
    gitmodules = (REPO / ".gitmodules").read_text(encoding="utf-8")
    assert "hermes-agent" not in gitmodules.lower()
    assert "nousresearch" not in gitmodules.lower()
    pkg = (CLOUD / "sdk" / "package.json").read_text(encoding="utf-8").lower()
    assert "hermes-agent" not in pkg
    assert "nousresearch" not in pkg
    req = (REPO / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "hermes" not in req
    launch_sh = LAUNCH.read_text(encoding="utf-8")
    assert "GCS_BOT_AGENT_ID" not in launch_sh
    assert "cloud_sdk_exec launch" in launch_sh
