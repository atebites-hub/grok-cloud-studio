"""Hive stamps Living Sky Linear after each mind turn. Donald A2A only.

Grok Bot must not write Linear. Fake GraphQL only — no network, no secrets.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
HIVE_PY = REPO / "scripts" / "directors" / "linear_hive.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
BOT_BRIDGE = REPO / "scripts" / "a2a" / "bot-bridge.py"
BIND_BOT = REPO / "scripts" / "a2a" / "bind-bot-agent.sh"
BOT_AGENTS = REPO / "docs" / "a2a" / "bot-agents.json"
DONALD_CARD = REPO / "docs" / "a2a" / "cards" / "donald.json"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
LINEAR_DOC = REPO / "docs" / "studio" / "LINEAR.md"
A2A_DOC = REPO / "docs" / "A2A.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"
AGENTS_DOC = REPO / "AGENTS.md"
README = REPO / "README.md"
PLUGIN_SERVER = REPO / "plugins" / "studio-mind" / "server.py"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
SCAN = REPO / "scripts" / "secret_scan.py"

TEAM = "LIV"
ISSUE = f"{TEAM}-82"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _write_fake_grok(tmp_path: Path, log: Path) -> Path:
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"log = {str(log)!r}\n"
        "rows = []\n"
        "if os.path.isfile(log):\n"
        "    rows = json.loads(open(log, encoding='utf-8').read() or '[]')\n"
        "rows.append({'argv': sys.argv[1:]})\n"
        "open(log, 'w', encoding='utf-8').write(json.dumps(rows))\n"
        "sys.stdout.write(json.dumps({'ok': True, 'text': 'hive turn done'}) + '\\n')\n"
        "raise SystemExit(0)\n"
    )
    return _write_exec(tmp_path / "fake-bin" / "grok", script)


def _prep_mind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, unique: str, grok: Path
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_mind_hive_{unique}")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_A2A_SEAT", raising=False)
    monkeypatch.delenv("GCS_LINEAR_DISABLE", raising=False)
    monkeypatch.delenv("GCS_LINEAR_TEAM_KEYS", raising=False)
    return mind, state


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> None:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-1",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _offset(state: Path, seat: str) -> int:
    path = state / seat / "mind" / "offset"
    if not path.is_file():
        return 0
    return int(path.read_text(encoding="utf-8").strip() or "0")


@pytest.fixture()
def hive() -> ModuleType:
    return _load(HIVE_PY, "gcs_linear_hive")


def test_extracts_living_sky_issue_ids_only(hive: ModuleType) -> None:
    extract = hive.extract_issue_ids
    assert extract(f"{ISSUE}: hive updates Living Sky Linear") == [ISSUE]
    url = f"https://linear.app/living-sky/issue/{ISSUE}/hive-updates"
    assert extract(url) == [ISSUE]
    blob = f"see ENG-1 and {ISSUE} plus GCS-9"
    assert extract(blob) == [ISSUE]
    assert extract("no tickets here") == []
    assert extract("liv-82") == []
    assert extract(f"{ISSUE} then {ISSUE} again") == [ISSUE]


def test_team_keys_env_can_allow_more_prefixes(
    hive: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GCS_LINEAR_TEAM_KEYS", "LIV,GCS")
    assert hive.extract_issue_ids("LIV-1 and GCS-9 and ENG-2") == ["LIV-1", "GCS-9"]


def test_comment_create_uses_identifier_and_hides_key(
    hive: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    def fake_post(payload: dict, *, headers: dict, timeout: float) -> dict:
        calls.append({"payload": payload, "headers": dict(headers), "timeout": timeout})
        return {
            "data": {
                "commentCreate": {
                    "success": True,
                    "comment": {"id": "comment-1", "url": "https://linear.app/c/1"},
                }
            }
        }

    key = "x" * 24
    monkeypatch.setenv("LINEAR_API_KEY", key)
    result = hive.comment_on_issue(
        ISSUE, "hive turn body", graphql_post=fake_post, api_key=key
    )
    assert result.get("ok") is True
    assert result.get("comment_id") == "comment-1"
    assert calls, "graphql_post must run"
    variables = calls[0]["payload"]["variables"]
    assert variables["input"]["issueId"] == ISSUE
    body = variables["input"]["body"]
    assert body == "hive turn body"
    assert key not in json.dumps(calls[0]["payload"])
    auth = calls[0]["headers"].get("Authorization") or ""
    assert auth.startswith("Bearer ")
    assert "commentCreate" in calls[0]["payload"]["query"]


def test_no_key_skips_graphql_and_a2as_donald_only(
    hive: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    posts: list[dict] = []
    sent: list[tuple[str, str, str]] = []

    def fake_post(*_a, **_k):
        posts.append({})
        raise AssertionError("Linear GraphQL must not run without a key")

    def send(seat: str, text: str, from_seat: str = "") -> str:
        sent.append((seat, text, from_seat))
        return "A2A_SEND_OK"

    result = hive.after_mind_turn(
        {
            "seat": "floor",
            "task_id": "task-1",
            "context_id": "ctx-1",
            "offset": 12,
            "prompt": f"{ISSUE}: do the hive stamp",
            "assistant_text": "worked",
            "backend": "grok",
        },
        send_fn=send,
        graphql_post=fake_post,
    )
    assert result.get("ok") is False
    assert result.get("reason") == "no-key"
    assert posts == []
    assert len(sent) == 1
    dest, text, from_seat = sent[0]
    assert dest == "donald"
    assert from_seat == "floor"
    assert "LINEAR_SKIP" in text
    assert ISSUE in text
    assert "source=hive" in text.replace("_", "-") or "source=hive-mind" in text
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert "LINEAR_SKIP" in blob
    assert "donald" in blob.lower() or "seat=donald" in blob


def test_successful_stamp_a2as_donald_not_a_second_seat(
    hive: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "k" * 24)
    sent: list[str] = []

    def fake_post(payload: dict, *, headers: dict, timeout: float) -> dict:
        return {
            "data": {
                "commentCreate": {
                    "success": True,
                    "comment": {"id": "c-ok", "url": "https://linear.app/c/ok"},
                }
            }
        }

    def send(seat: str, text: str, from_seat: str = "") -> str:
        sent.append(seat)
        assert "LINEAR_STAMP" in text
        assert ISSUE in text
        assert from_seat == "floor"
        return "A2A_SEND_OK"

    result = hive.after_mind_turn(
        {
            "seat": "floor",
            "task_id": "task-ok",
            "offset": 99,
            "prompt": f"work {ISSUE}",
            "assistant_text": "done",
            "backend": "grok",
        },
        send_fn=send,
        graphql_post=fake_post,
    )
    assert result.get("ok") is True
    assert sent == ["donald"]


def test_no_issue_id_does_not_a2a_or_call_linear(
    hive: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "k" * 24)
    sent: list[tuple] = []

    def fake_post(*_a, **_k):
        raise AssertionError("no GraphQL without an issue id")

    def send(*_a, **_k):
        sent.append(_a)
        return "A2A_SEND_OK"

    result = hive.after_mind_turn(
        {
            "seat": "floor",
            "task_id": "task-none",
            "offset": 1,
            "prompt": "STATUS/CONTINUE keep-alive",
            "assistant_text": "pong",
            "backend": "grok",
        },
        send_fn=send,
        graphql_post=fake_post,
    )
    assert result.get("reason") == "no-issue"
    assert sent == []


def test_linear_failure_still_a2as_donald(
    hive: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "k" * 24)
    sent: list[tuple[str, str]] = []

    def fake_post(*_a, **_k):
        return {"errors": [{"message": "boom"}]}

    def send(seat: str, text: str, from_seat: str = "") -> str:
        sent.append((seat, text))
        return "A2A_SEND_OK"

    result = hive.after_mind_turn(
        {
            "seat": "ops",
            "task_id": "task-fail",
            "offset": 3,
            "prompt": f"{ISSUE} please",
            "assistant_text": "tried",
            "backend": "cursor",
        },
        send_fn=send,
        graphql_post=fake_post,
    )
    assert result.get("ok") is False
    assert result.get("reason") in {"graphql-error", "linear-fail", "http-error"}
    assert sent == [("donald", sent[0][1])]
    assert "LINEAR_FAIL" in sent[0][1]


def test_a2a_seat_env_override(
    hive: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GCS_LINEAR_A2A_SEAT", "orchestrator")
    assert hive.linear_a2a_seat() == "orchestrator"
    monkeypatch.delenv("GCS_LINEAR_A2A_SEAT", raising=False)
    assert hive.linear_a2a_seat() == "donald"


def test_disable_env_skips_graphql(
    hive: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "k" * 24)
    monkeypatch.setenv("GCS_LINEAR_DISABLE", "1")
    sent: list[str] = []

    def fake_post(*_a, **_k):
        raise AssertionError("disabled")

    def send(seat: str, text: str, from_seat: str = "") -> str:
        sent.append(text)
        return "A2A_SEND_OK"

    result = hive.after_mind_turn(
        {
            "seat": "floor",
            "task_id": "t",
            "offset": 1,
            "prompt": ISSUE,
            "assistant_text": "x",
            "backend": "grok",
        },
        send_fn=send,
        graphql_post=fake_post,
    )
    assert result.get("reason") == "disabled"
    assert sent and "LINEAR_SKIP" in sent[0]


def test_redacts_secrets_from_linear_comment_body(hive: ModuleType) -> None:
    key_name = "LINEAR" + "_API_KEY"
    leak = f"{key_name}=supersecretvalue0001"
    body = hive.format_comment(
        {
            "seat": "floor",
            "task_id": "t",
            "offset": 1,
            "prompt": f"{ISSUE} {leak}",
            "assistant_text": leak,
            "backend": "grok",
        },
        ISSUE,
    )
    assert "hive" in body.lower()
    assert "not grok bot" in body.lower()
    assert "supersecretvalue0001" not in body
    assert "[redacted]" in body


def test_mind_turn_stamps_after_success_and_survives_hive_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok = _write_fake_grok(tmp_path, tmp_path / "grok.argv.json")
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="hook", grok=grok)
    seen: list[dict] = []

    def fake_after(payload: dict, **_kwargs):
        seen.append(payload)
        raise RuntimeError("linear transport exploded")

    monkeypatch.setattr(mind, "after_mind_turn", fake_after, raising=False)
    _append_inbox(state, "floor", "task-liv", f"{ISSUE}: implement hive stamp")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"
    assert _offset(state, "floor") > 0
    assert seen
    assert seen[0]["seat"] == "floor"
    assert ISSUE in seen[0]["prompt"]
    assert seen[0]["task_id"] == "task-liv"


def test_mind_turn_does_not_stamp_on_runner_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok-fail",
        "#!/usr/bin/env python3\nimport sys\nsys.stderr.write('boom\\n')\nraise SystemExit(1)\n",
    )
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="failhook", grok=grok)
    seen: list[dict] = []
    monkeypatch.setattr(
        mind, "after_mind_turn", lambda *a, **k: seen.append(a) or {}, raising=False
    )
    _append_inbox(state, "floor", "task-fail", f"{ISSUE} should not stamp")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert seen == []
    assert _offset(state, "floor") == 0


def test_grok_bot_paths_do_not_stamp_linear() -> None:
    banned = ("commentCreate", "api.linear.app", "LINEAR_API_KEY")
    for path in (BOT_BRIDGE, BIND_BOT, PLUGIN_SERVER, BOT_AGENTS):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} must not stamp Linear ({token})"
    plugins = _load(MIND_PY, "gcs_mind_plugin_scan").PLUGINS
    assert "linear" not in plugins
    assert "commentCreate" not in plugins
    assert "linear_stamp" not in plugins


def test_donald_card_exists_for_a2a_only() -> None:
    assert DONALD_CARD.is_file()
    card = json.loads(DONALD_CARD.read_text(encoding="utf-8"))
    assert "donald" in card["supportedInterfaces"][0]["url"]
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert "donald" in registry["skipSeats"]
    assert "donald" in registry["seats"]
    assert "acpPort" not in registry["seats"]["donald"]
    bots = json.loads(BOT_AGENTS.read_text(encoding="utf-8"))
    assert "donald" not in (bots.get("seats") or {}), (
        "committed bot-agents must not add a second placeholder Bot (doctor FAIL)"
    )


def test_docs_law_hive_not_bot() -> None:
    blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (LINEAR_DOC, MIND_DOC, A2A_DOC, ARCH_DOC, AGENTS_DOC, README, FOOTER)
    )
    low = blob.lower()
    assert LINEAR_DOC.is_file()
    assert "living sky" in low or "liv-82" in low or "linear" in low
    assert "donald" in low
    assert "a2a" in low
    assert "do not stamp linear from grok bot" in low or (
        "not stamp" in low and "linear" in low and "grok bot" in low
    )
    assert "after each mind turn" in low or "after each successful mind turn" in low
    assert "empty ci is not merge" in low or "empty CI is not merge" in blob
    assert "pytest -q" in blob
    assert "secret_scan" in blob
    src = HIVE_PY.read_text(encoding="utf-8")
    assert "stdlib" in src.lower() or "Stdlib" in src
    assert "skipSeats" in MIND_DOC.read_text(encoding="utf-8") or "donald" in MIND_DOC.read_text(
        encoding="utf-8"
    ).lower()


def test_secret_scan_bans_linear_api_key_assignment(tmp_path: Path) -> None:
    name = "LINEAR" + "_API_KEY"
    leak = tmp_path / "leak.env"
    leak.write_text(f"{name}=" + ("z" * 20) + "\n", encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(SCAN), "--root", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode != 0
    assert "linear_key_assignment" in proc.stdout
