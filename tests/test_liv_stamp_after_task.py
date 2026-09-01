"""Follow-up to PR #64: minds stamp Living Sky Linear after a TASK completes.

PR #64 wires Linear MCP catalogs. This slice is the executable demonstration:
`scripts/studio/linear/liv_stamp.py` comments a LIV-* issue via Linear GraphQL
(mocked here). Donald / orchestrator cannot stamp. NEVER Black Swan Money.

LIV-82 / LIV-43. Palemon/GCS issues stay on linear.app/livingsky only.
Does not touch list.sh runStatus, recover.sh, or Hermes harvest.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parents[1]
STAMP = REPO / "scripts" / "studio" / "linear" / "liv_stamp.py"
FEATURE = REPO / "docs" / "studio" / "bdd" / "liv_stamp_after_task.feature"
LINEAR_DOC = REPO / "docs" / "studio" / "LINEAR.md"
FORBIDDEN_LIST = REPO / "scripts" / "cloud" / "list.sh"
FORBIDDEN_RECOVER = REPO / "recover.sh"

LIVING_SKY_HOST = "linear.app/livingsky"
LINEAR_GRAPHQL_HOST = "api.linear.app"
LINEAR_MCP_HOST = "mcp.linear.app"
PRIVATE_GAME = "atebites-hub/" + "pale" + "mon"
GCS_LABEL = "atebites-hub/grok-cloud-studio"
FAKE_KEY = "lin_" + "test" + ("0" * 20)


def _load() -> ModuleType:
    existing = sys.modules.get("liv_stamp")
    stamp_path = STAMP.resolve()
    existing_file = getattr(existing, "__file__", None) if existing is not None else None
    if existing is not None and existing_file and Path(existing_file).resolve() == stamp_path:
        return existing
    spec = importlib.util.spec_from_file_location("liv_stamp", stamp_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["liv_stamp"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_mind(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / "directors" / "mind.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeLinear:
    """In-process Linear GraphQL stand-in. Records payloads; never the network."""

    def __init__(
        self,
        *,
        url_key: str = "livingsky",
        org_name: str = "Living Sky",
        team_key: str = "LIV",
        team_name: str = "Livingsky",
        issue_identifier: str = "LIV-82",
        issue_url: str = "https://linear.app/livingsky/issue/LIV-82",
        labels: dict[str, str] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.url_key = url_key
        self.org_name = org_name
        self.team_id = "team-liv-uuid"
        self.team_key = team_key
        self.team_name = team_name
        self.issue_id = "issue-uuid-82"
        self.issue_identifier = issue_identifier
        self.issue_url = issue_url
        self.comment_id = "comment-uuid-1"
        self.created_identifier = "LIV-99"
        self.created_id = "issue-uuid-99"
        self.labels = labels or {
            GCS_LABEL: "label-gcs",
            PRIVATE_GAME: "label-palemon",
        }

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        op = str(payload.get("operationName") or "")
        if op == "Organization":
            return {
                "data": {
                    "organization": {
                        "id": "org-liv",
                        "name": self.org_name,
                        "urlKey": self.url_key,
                    }
                }
            }
        if op == "Issue":
            ident = str((payload.get("variables") or {}).get("id") or "")
            return {
                "data": {
                    "issue": {
                        "id": self.issue_id,
                        "identifier": ident or self.issue_identifier,
                        "url": self.issue_url,
                        "title": "Hive minds stamp Linear",
                        "team": {
                            "id": self.team_id,
                            "key": self.team_key,
                            "name": self.team_name,
                        },
                    }
                }
            }
        if op == "TeamByKey":
            return {
                "data": {
                    "teams": {
                        "nodes": [
                            {
                                "id": self.team_id,
                                "key": self.team_key,
                                "name": self.team_name,
                            }
                        ]
                    }
                }
            }
        if op == "IssueLabels":
            names = list((payload.get("variables") or {}).get("names") or [])
            nodes = [
                {"id": lid, "name": name}
                for name, lid in self.labels.items()
                if name in names
            ]
            return {"data": {"issueLabels": {"nodes": nodes}}}
        if op == "CommentCreate":
            body = str(((payload.get("variables") or {}).get("input") or {}).get("body") or "")
            return {
                "data": {
                    "commentCreate": {
                        "success": True,
                        "comment": {
                            "id": self.comment_id,
                            "body": body,
                            "url": self.issue_url + "#comment-1",
                        },
                    }
                }
            }
        if op == "IssueCreate":
            return {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": self.created_id,
                            "identifier": self.created_identifier,
                            "url": "https://linear.app/livingsky/issue/"
                            + self.created_identifier,
                        },
                    }
                }
            }
        raise AssertionError(f"unexpected Linear operation {op!r}")

    def comment_bodies(self) -> list[str]:
        out: list[str] = []
        for call in self.calls:
            if call.get("operationName") != "CommentCreate":
                continue
            body = str(((call.get("variables") or {}).get("input") or {}).get("body") or "")
            out.append(body)
        return out


def _evidence() -> str:
    return (
        "CLOUD_LAUNCH_OK id=bc-fake run=run-fake "
        "url=https://cursor.com/agents/bc-fake\n"
        "pytest evidence: tests/test_liv_stamp_after_task.py"
    )


# --- Spec surfaces --------------------------------------------------------------


def test_feature_and_docs_name_living_sky_not_black_swan() -> None:
    feature = FEATURE.read_text(encoding="utf-8")
    doc = LINEAR_DOC.read_text(encoding="utf-8")
    blob = feature + "\n" + doc
    low = blob.lower()
    assert "LIV-82" in blob
    assert "LIV-43" in blob
    assert LIVING_SKY_HOST in blob
    assert "after" in low and "task" in low
    assert "CLOUD_LAUNCH_OK" in blob
    assert "pytest" in low
    assert "donald" in low and "diy" in low
    assert "never" in low and "black swan" in low
    assert "liv_stamp" in low or "stamp.py" in low or "liv_stamp.py" in low
    assert "process_once" in blob
    assert GCS_LABEL in blob
    assert PRIVATE_GAME not in blob
    assert "runStatus" not in blob
    assert "Hermes" not in blob


def test_stamp_script_exists_and_is_stdlib() -> None:
    text = STAMP.read_text(encoding="utf-8")
    assert "https://api.linear.app/graphql" in text
    assert LINEAR_MCP_HOST in text
    assert LIVING_SKY_HOST in text
    assert "save_comment" in text or "commentCreate" in text
    assert "from requests" not in text
    assert "import httpx" not in text
    assert FAKE_KEY not in text
    assert "send.sh" not in text
    assert PRIVATE_GAME not in text


def test_follow_up_does_not_touch_forbidden_surfaces() -> None:
    """This PR must not edit list.sh, recover.sh, or Hermes harvest."""
    list_text = FORBIDDEN_LIST.read_text(encoding="utf-8")
    recover_text = FORBIDDEN_RECOVER.read_text(encoding="utf-8")
    stamp_text = STAMP.read_text(encoding="utf-8")
    assert "runStatus" in list_text or "run_status" in list_text or "status" in list_text
    assert "Hermes" not in stamp_text
    assert "recover.sh" not in stamp_text
    assert str(FORBIDDEN_LIST) not in stamp_text
    assert "list.sh" not in stamp_text
    assert recover_text.strip()


# --- Comment body law -----------------------------------------------------------


def test_after_task_body_contains_cloud_launch_ok_and_pytest_evidence() -> None:
    mod = _load()
    body = mod.build_after_task_body(
        seat="floor",
        task_id="T-99",
        issue="LIV-82",
        evidence=_evidence(),
    )
    assert "CLOUD_LAUNCH_OK" in body
    assert "bc-fake" in body
    assert "pytest evidence" in body
    assert "tests/test_liv_stamp_after_task.py" in body
    assert "LIV-82" in body
    assert "T-99" in body
    assert "floor" in body
    assert LIVING_SKY_HOST in body
    assert "LIV" in body
    low = body.lower()
    assert "donald" in low
    assert "diy" in low
    assert FAKE_KEY not in body
    assert PRIVATE_GAME not in body


def test_mcp_save_comment_args_match_linear_tool_shape() -> None:
    mod = _load()
    body = mod.build_after_task_body(
        seat="ops",
        task_id="T-1",
        issue="LIV-43",
        evidence=_evidence(),
    )
    args = mod.linear_mcp_save_comment_args("LIV-43", body)
    assert args["issueId"] == "LIV-43"
    assert args["body"] == body
    assert "CLOUD_LAUNCH_OK" in args["body"]
    assert set(args) == {"issueId", "body"}


def test_stamp_after_task_posts_comment_with_cloud_launch_ok() -> None:
    mod = _load()
    fake = FakeLinear()
    client = mod.LinearGraphQL(FAKE_KEY, transport=fake)
    result = mod.stamp_after_task(
        issue="LIV-82",
        task_id="T-99",
        evidence=_evidence(),
        seat="floor",
        client=client,
    )
    assert result["ok"] is True
    assert result["issue"] == "LIV-82"
    assert result["workspace"] == "livingsky"
    assert result["team"] == "LIV"
    bodies = fake.comment_bodies()
    assert len(bodies) == 1
    body = bodies[0]
    assert "CLOUD_LAUNCH_OK" in body
    assert "pytest evidence" in body
    assert "LIV-82" in body
    ops = [c.get("operationName") for c in fake.calls]
    assert "Organization" in ops
    assert "Issue" in ops
    assert "CommentCreate" in ops
    comment = next(c for c in fake.calls if c.get("operationName") == "CommentCreate")
    issue_id = ((comment.get("variables") or {}).get("input") or {}).get("issueId")
    assert issue_id == fake.issue_id


def test_refuses_black_swan_workspace() -> None:
    mod = _load()
    fake = FakeLinear(
        url_key="blackswan",
        org_name="Black Swan Money",
        issue_url="https://linear.app/blackswan/issue/LIV-82",
    )
    client = mod.LinearGraphQL(FAKE_KEY, transport=fake)
    with pytest.raises(mod.LivStampError) as exc:
        mod.stamp_after_task(
            issue="LIV-82",
            task_id="T-1",
            evidence=_evidence(),
            seat="floor",
            client=client,
        )
    msg = str(exc.value).lower()
    assert "living sky" in msg or "livingsky" in msg
    assert "black swan" in msg or "refused" in msg or "never" in msg
    assert not fake.comment_bodies()
    assert FAKE_KEY not in str(exc.value)


def test_refuses_non_liv_issue_identifier() -> None:
    mod = _load()
    fake = FakeLinear()
    client = mod.LinearGraphQL(FAKE_KEY, transport=fake)
    with pytest.raises(mod.LivStampError):
        mod.stamp_after_task(
            issue="BSM-1",
            task_id="T-1",
            evidence=_evidence(),
            seat="floor",
            client=client,
        )
    assert fake.calls == []


def test_donald_and_orchestrator_do_not_diy_linear() -> None:
    mod = _load()
    for seat in ("donald", "orchestrator", "Donald"):
        fake = FakeLinear()
        client = mod.LinearGraphQL(FAKE_KEY, transport=fake)
        with pytest.raises(mod.LivStampError) as exc:
            mod.stamp_after_task(
                issue="LIV-82",
                task_id="T-1",
                evidence=_evidence(),
                seat=seat,
                client=client,
            )
        low = str(exc.value).lower()
        assert "skip" in low or "donald" in low or "diy" in low
        assert fake.calls == []


def test_create_issue_uses_liv_team_and_gcs_label() -> None:
    mod = _load()
    fake = FakeLinear()
    client = mod.LinearGraphQL(FAKE_KEY, transport=fake)
    result = mod.stamp_create(
        title="GCS stamp demo",
        description=_evidence(),
        seat="floor",
        client=client,
        label=GCS_LABEL,
    )
    assert result["ok"] is True
    assert str(result["issue"]).startswith("LIV-")
    create = next(c for c in fake.calls if c.get("operationName") == "IssueCreate")
    inp = (create.get("variables") or {}).get("input") or {}
    assert inp.get("teamId") == fake.team_id
    assert fake.labels[GCS_LABEL] in (inp.get("labelIds") or [])
    desc = str(inp.get("description") or "")
    assert "CLOUD_LAUNCH_OK" in desc or "pytest evidence" in desc


def test_create_rejects_unknown_label() -> None:
    mod = _load()
    fake = FakeLinear()
    client = mod.LinearGraphQL(FAKE_KEY, transport=fake)
    with pytest.raises(mod.LivStampError):
        mod.stamp_create(
            title="nope",
            description="x",
            seat="floor",
            client=client,
            label="black-swan-money",
        )
    assert not any(c.get("operationName") == "IssueCreate" for c in fake.calls)


def test_load_key_from_linear_env_without_printing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load()
    key_file = tmp_path / "a2a-state" / "linear.env"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(f"LINEAR_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    got = mod.load_linear_api_key(
        env={},
        state_dir=tmp_path / "a2a-state",
        home=tmp_path / "home",
    )
    assert got == FAKE_KEY
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out
    assert FAKE_KEY not in captured.err


def test_missing_key_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_KEY_FILE", raising=False)
    with pytest.raises(mod.LivStampError) as exc:
        mod.load_linear_api_key(
            env={},
            state_dir=tmp_path / "a2a-state",
            home=tmp_path / "home",
        )
    assert "LINEAR_API_KEY" in str(exc.value)
    assert FAKE_KEY not in str(exc.value)


def test_redact_strips_key_from_errors() -> None:
    mod = _load()
    leaked = f"Authorization: Bearer {FAKE_KEY} LINEAR_API_KEY={FAKE_KEY}"
    out = mod.redact(leaked)
    assert FAKE_KEY not in out
    assert "Bearer" in out or "redacted" in out.lower()


# --- CLI against a local GraphQL mock -------------------------------------------


class _GraphQLHandler(BaseHTTPRequestHandler):
    def log_message(self, _fmt: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8") or "{}")
        self.server.calls.append(  # type: ignore[attr-defined]
            {
                "path": urlparse(self.path).path,
                "auth": self.headers.get("Authorization") or "",
                "payload": payload,
            }
        )
        fake: FakeLinear = self.server.fake  # type: ignore[attr-defined]
        body = json.dumps(fake(payload)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(fake: FakeLinear) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GraphQLHandler)
    server.fake = fake  # type: ignore[attr-defined]
    server.calls = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/graphql"


def test_cli_after_task_mocks_linear_and_prints_liv_stamp_ok() -> None:
    fake = FakeLinear()
    server, url = _serve(fake)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(REPO),
        "GCS_ROOT": str(REPO),
        "LINEAR_API_KEY": FAKE_KEY,
        "GCS_LINEAR_GRAPHQL_URL": url,
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(STAMP),
                "after-task",
                "--issue",
                "LIV-82",
                "--task",
                "T-99",
                "--seat",
                "floor",
                "--evidence",
                _evidence(),
            ],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        server.shutdown()
        server.server_close()
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "LIV_STAMP_OK" in proc.stdout
    assert "LIV-82" in proc.stdout
    assert "livingsky" in proc.stdout.lower()
    assert FAKE_KEY not in blob
    bodies = fake.comment_bodies()
    assert bodies, blob
    assert "CLOUD_LAUNCH_OK" in bodies[0]
    assert "pytest evidence" in bodies[0]
    auths = [row["auth"] for row in server.calls]  # type: ignore[attr-defined]
    assert auths
    assert all("Bearer" in a for a in auths)
    assert all(FAKE_KEY not in json.dumps(row["payload"]) for row in server.calls)  # type: ignore[attr-defined]


def test_cli_donald_exits_nonzero_without_posting() -> None:
    fake = FakeLinear()
    server, url = _serve(fake)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(REPO),
        "GCS_ROOT": str(REPO),
        "LINEAR_API_KEY": FAKE_KEY,
        "GCS_LINEAR_GRAPHQL_URL": url,
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(STAMP),
                "after-task",
                "--issue",
                "LIV-82",
                "--task",
                "T-1",
                "--seat",
                "donald",
                "--evidence",
                _evidence(),
            ],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        server.shutdown()
        server.server_close()
    assert STAMP.is_file()
    assert proc.returncode != 0
    blob = proc.stdout + proc.stderr
    assert "LIV_STAMP_OK" not in blob
    assert "LIV_STAMP_ERR" in blob
    assert "diy" in blob.lower() or "skip" in blob.lower()
    assert FAKE_KEY not in blob
    assert fake.comment_bodies() == []
    assert server.calls == []  # type: ignore[attr-defined]


def test_allowed_labels_are_living_sky_only() -> None:
    mod = _load()
    labels = set(mod.living_sky_labels())
    assert GCS_LABEL in labels
    assert PRIVATE_GAME in labels
    assert all("black swan" not in n.lower() for n in labels)
    assert all(n.startswith("atebites-hub/") for n in labels)


# --- Remaining mechanic: stamp after process_once consumes a TASK (LIV-96 FAT) -


def test_maybe_stamp_after_task_posts_cloud_launch_ok() -> None:
    mod = _load()
    fake = FakeLinear()
    mod._TEST_CLIENT = mod.LinearGraphQL(FAKE_KEY, transport=fake)
    try:
        result = mod.maybe_stamp_after_task(
            seat="floor",
            task_id="T-99",
            evidence=_evidence(),
            issue="LIV-82",
        )
    finally:
        mod._TEST_CLIENT = None
    assert result.get("ok") is True
    assert result.get("issue") == "LIV-82"
    bodies = fake.comment_bodies()
    assert len(bodies) == 1
    assert "CLOUD_LAUNCH_OK" in bodies[0]
    assert "pytest evidence" in bodies[0]


def test_maybe_stamp_after_task_skips_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    mod._TEST_CLIENT = None
    monkeypatch.setenv("GCS_LIV_STAMP", "1")
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_KEY_FILE", raising=False)
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    result = mod.maybe_stamp_after_task(
        seat="floor",
        task_id="T-1",
        evidence=_evidence(),
        issue="LIV-82",
        env={},
        state_dir=tmp_path / "a2a-state",
        home=tmp_path / "home",
    )
    assert result.get("ok") is False
    assert result.get("reason") == "no-key"


def test_maybe_stamp_after_task_donald_does_not_post() -> None:
    mod = _load()
    fake = FakeLinear()
    mod._TEST_CLIENT = mod.LinearGraphQL(FAKE_KEY, transport=fake)
    try:
        result = mod.maybe_stamp_after_task(
            seat="donald",
            task_id="T-1",
            evidence=_evidence(),
            issue="LIV-82",
        )
    finally:
        mod._TEST_CLIENT = None
    assert result.get("ok") is False
    assert "skip" in str(result.get("reason", "")).lower()
    assert fake.calls == []


def test_process_once_stamps_liv_after_task_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Harness remaining mechanic: A2A TASK consumed → Living Sky comment."""
    stamp = _load()
    fake = FakeLinear()
    stamp._TEST_CLIENT = stamp.LinearGraphQL(FAKE_KEY, transport=fake)
    monkeypatch.setenv("GCS_LIV_STAMP", "1")
    monkeypatch.setenv("GCS_LIV_ISSUE", "LIV-82")
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    mind = _load_mind("gcs_mind_liv_stamp_hook")
    mind.STATE_DIR = tmp_path / "a2a-state"
    mind.ROOT = REPO
    inbox = tmp_path / "a2a-state" / "floor" / "inbox.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text(
        json.dumps(
            {
                "taskId": "T-99",
                "contextId": "ctx-1",
                "parts": [{"kind": "text", "text": "ship Extra High"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        result = mind.process_once(
            "floor",
            runner=lambda *_a, **_k: {
                "text": (
                    "CLOUD_LAUNCH_OK id=bc-fake\n"
                    "pytest evidence: tests/test_liv_stamp_after_task.py"
                )
            },
        )
    finally:
        stamp._TEST_CLIENT = None
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"
    assert result.get("liv") == "LIV-82"
    bodies = fake.comment_bodies()
    assert bodies, "process_once must stamp Living Sky after TASK completes"
    assert "CLOUD_LAUNCH_OK" in bodies[0]
    assert "pytest evidence" in bodies[0]
    assert "T-99" in bodies[0]


def test_process_once_donald_still_does_not_diy_linear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamp = _load()
    fake = FakeLinear()
    stamp._TEST_CLIENT = stamp.LinearGraphQL(FAKE_KEY, transport=fake)
    monkeypatch.setenv("GCS_LIV_STAMP", "1")
    monkeypatch.setenv("GCS_LIV_ISSUE", "LIV-82")
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    mind = _load_mind("gcs_mind_liv_stamp_donald")
    mind.STATE_DIR = tmp_path / "a2a-state"
    mind.ROOT = REPO
    inbox = tmp_path / "a2a-state" / "donald" / "inbox.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text(
        json.dumps({"taskId": "T-1", "parts": [{"kind": "text", "text": "stamp LIV-82"}]})
        + "\n",
        encoding="utf-8",
    )
    try:
        result = mind.process_once(
            "donald",
            runner=lambda *_a, **_k: {"text": "CLOUD_LAUNCH_OK id=bc-fake"},
        )
    finally:
        stamp._TEST_CLIENT = None
    assert result["consumed"] == 0
    assert "skip" in str(result.get("reason", "")).lower()
    assert fake.calls == []


def test_studio_mind_plugin_exposes_liv_stamp() -> None:
    mind = _load_mind("gcs_mind_liv_stamp_plugin")
    assert "liv_stamp" in mind.PLUGINS
    out = mind.call_plugin(
        "liv_stamp",
        {
            "seat": "donald",
            "task": "T-1",
            "evidence": _evidence(),
            "issue": "LIV-82",
        },
    )
    assert "LIV_STAMP_ERR" in out or "skip" in out.lower() or "donald" in out.lower()
    assert FAKE_KEY not in out


def test_studio_mind_plugin_floor_stamps_liv() -> None:
    stamp = _load()
    fake = FakeLinear()
    stamp._TEST_CLIENT = stamp.LinearGraphQL(FAKE_KEY, transport=fake)
    mind = _load_mind("gcs_mind_liv_stamp_plugin_floor")
    try:
        out = mind.call_plugin(
            "liv_stamp",
            {
                "seat": "floor",
                "task": "T-99",
                "evidence": _evidence(),
                "issue": "LIV-82",
            },
        )
    finally:
        stamp._TEST_CLIENT = None
    assert "LIV_STAMP_OK" in out
    assert "LIV-82" in out
    assert FAKE_KEY not in out
    bodies = fake.comment_bodies()
    assert bodies
    assert "CLOUD_LAUNCH_OK" in bodies[0]
    assert "pytest evidence" in bodies[0]
