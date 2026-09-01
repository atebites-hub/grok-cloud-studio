"""LIV-82: hive stamps Living Sky Linear only after real evidence.

Hub TASK_STATE_COMPLETED is a receipt (LIV-85), not a stamp trigger.
LINEAR_API_KEY unset → fail closed; never fake a comment id.
Living Sky team LIV only — never Black Swan. Never Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
STAMP_PY = ROOT / "scripts" / "directors" / "liv_evidence_stamp.py"
MIND_PY = ROOT / "scripts" / "directors" / "mind.py"
HUB_PY = ROOT / "scripts" / "a2a" / "hub.py"
DUPLEX_PY = ROOT / "scripts" / "a2a" / "duplex.py"
BOT_BRIDGE_PY = ROOT / "scripts" / "a2a" / "bot-bridge.py"
LAUNCH_SH = ROOT / "scripts" / "launch-cloud-extra-high.sh"
LAUNCH_TS = ROOT / "scripts" / "cloud" / "sdk" / "launch.ts"
FOOTER = ROOT / "scripts" / "directors" / "common_footer.txt"
LINEAR_DOC = ROOT / "docs" / "studio" / "LINEAR.md"
SECRET_SCAN = ROOT / "scripts" / "secret_scan.py"
VENDOR = ROOT / "vendor"

FAKE_KEY = "lin_api_TESTONLY_not_a_real_secret_key"
LIV_MAIL = "Beat: stamp Living Sky LIV-82 after a real mind turn. Open a PR."


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stamp() -> ModuleType:
    assert STAMP_PY.is_file(), "missing scripts/directors/liv_evidence_stamp.py"
    return _load(STAMP_PY, "liv_evidence_stamp")


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> None:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-liv",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
    runner: Any,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_mind_liv_{unique}")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setattr(mind, "DEFAULT_RUNNER", runner)
    return mind, state


class FakeLinear:
    """In-process GraphQL stand-in. Never a Living Sky network call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.team_key = "LIV"
        self.team_name = "Livingsky"
        self.comment_id = "cmt-evidence-1"
        self.issue_id = "uuid-liv-82"
        self.raise_exc: Exception | None = None
        self.issue_missing = False

    def __call__(
        self, query: str, variables: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        self.calls.append(
            {"query": query, "variables": dict(variables), "headers": dict(headers)}
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        if "commentCreate" in query:
            return {
                "commentCreate": {
                    "success": True,
                    "comment": {"id": self.comment_id, "url": "https://linear.app/livingsky/comment/1"},
                }
            }
        if self.issue_missing:
            return {"issue": None}
        ident = str(variables.get("id") or variables.get("identifier") or "LIV-82")
        return {
            "issue": {
                "id": self.issue_id,
                "identifier": ident,
                "title": "hive stamp after evidence",
                "url": f"https://linear.app/livingsky/issue/{ident}",
                "team": {"key": self.team_key, "name": self.team_name},
            }
        }


@pytest.fixture()
def stamp_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_STAMP", raising=False)
    monkeypatch.delenv("GCS_LINEAR_TEAM_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_GRAPHQL_URL", raising=False)
    return tmp_path


def test_stamp_module_and_docs_exist() -> None:
    assert STAMP_PY.is_file()
    assert LINEAR_DOC.is_file()
    doc = LINEAR_DOC.read_text(encoding="utf-8")
    footer = FOOTER.read_text(encoding="utf-8")
    for blob in (doc, footer):
        assert "LIV-" in blob
        assert "Living Sky" in blob or "livingsky" in blob.lower()
        assert "Black Swan" in blob
        assert "TASK_STATE_COMPLETED" in blob
        assert "fail closed" in blob.lower() or "fail-closed" in blob.lower()


def test_extract_liv_identifiers_only() -> None:
    mod = _stamp()
    found = mod.extract_liv_identifiers(
        "Stamp LIV-82 and also LIV-96. Ignore PAL-43 and BSM-1 and liv-82."
    )
    assert found == ["LIV-82", "LIV-96"]
    assert mod.extract_liv_identifiers("no issues here") == []
    assert mod.extract_liv_identifiers("BSM-99 Black Swan") == []


def test_hub_receipt_never_posts_even_with_key_and_liv(
    stamp_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    graphql = FakeLinear()
    result = mod.stamp_after_evidence(
        kind="hub-receipt",
        seat="floor",
        text=LIV_MAIL + " TASK_STATE_COMPLETED",
        task_id="task-hub-ack",
        graphql=graphql,
    )
    assert result["posted"] is False
    assert result["ok"] is False or result["reason"] == "hub-receipt"
    assert result["reason"] == "hub-receipt"
    assert result.get("comment_ids") in ((), [], None)
    assert graphql.calls == []
    assert not (stamp_env / "a2a-state" / "floor" / "linear-stamp.json").is_file()


def test_task_state_completed_kind_aliases_are_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    graphql = FakeLinear()
    for kind in (
        "hub-receipt",
        "TASK_STATE_COMPLETED",
        "task_state_completed",
        "a2a-ack",
    ):
        result = mod.stamp_after_evidence(
            kind=kind,
            seat="floor",
            text=LIV_MAIL,
            graphql=graphql,
        )
        assert result["posted"] is False, kind
        assert result["reason"] == "hub-receipt", kind
    assert graphql.calls == []


def test_missing_linear_key_fails_closed_does_not_fake_stamp(
    stamp_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    mod = _stamp()
    graphql = FakeLinear()
    result = mod.stamp_after_evidence(
        kind="mind-turn",
        seat="floor",
        text=LIV_MAIL,
        graphql=graphql,
    )
    assert result["posted"] is False
    assert result["ok"] is False
    assert result["reason"] == "no-key"
    assert not result.get("comment_ids")
    assert graphql.calls == []
    fake_path = stamp_env / "a2a-state" / "floor" / "linear-stamp.json"
    assert not fake_path.is_file()
    # Fail closed is logged; never a success line or invented comment id.
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert "LINEAR_STAMP_FAIL" in blob
    assert "reason=no-key" in blob
    assert "LINEAR_STAMP_OK" not in blob
    assert "cmt-" not in blob
    assert FAKE_KEY not in blob


def test_no_liv_identifier_skips_before_key_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    mod = _stamp()
    graphql = FakeLinear()
    result = mod.stamp_after_evidence(
        kind="mind-turn",
        seat="floor",
        text="ACP_PING STATUS/CONTINUE keep-alive. Tools allowed.",
        graphql=graphql,
    )
    assert result["posted"] is False
    assert result["reason"] == "no-issue"
    assert graphql.calls == []


def test_mind_turn_with_key_posts_living_sky_comment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    graphql = FakeLinear()
    result = mod.stamp_after_evidence(
        kind="mind-turn",
        seat="floor",
        text=LIV_MAIL,
        turn="MIND_TURN ok. RESULT bc-id=none notes=hive stamp after evidence",
        task_id="task-turn-1",
        graphql=graphql,
    )
    assert result["ok"] is True
    assert result["posted"] is True
    assert result["reason"] == "ok"
    assert result["identifiers"] == ["LIV-82"]
    assert result["comment_ids"] == ["cmt-evidence-1"]
    assert any("commentCreate" in c["query"] for c in graphql.calls)
    assert any(
        c["variables"].get("id") == "LIV-82" or c["variables"].get("issueId")
        for c in graphql.calls
    )
    auth = graphql.calls[0]["headers"].get("Authorization") or ""
    assert FAKE_KEY in auth
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert "LINEAR_STAMP_OK" in blob
    assert "kind=mind-turn" in blob
    assert FAKE_KEY not in blob
    bodies = [
        str(c["variables"].get("body") or "")
        for c in graphql.calls
        if "commentCreate" in c["query"]
    ]
    assert bodies
    assert "mind-turn" in bodies[0]
    assert "LIV-82" in bodies[0]
    assert "hub-receipt" not in bodies[0].lower()
    assert FAKE_KEY not in bodies[0]


def test_cloud_launch_stamp_includes_bc_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    graphql = FakeLinear()
    result = mod.stamp_after_evidence(
        kind="cloud-launch",
        seat="floor",
        text="Implement LIV-82 hive stamp after Extra High launch. Open a PR.",
        name="gcs-liv82-linear-stamp-floor1747",
        bc_id="bc-e9af8de1-3155-44db-81a2-075d464d3c8a",
        graphql=graphql,
    )
    assert result["posted"] is True
    assert result["identifiers"] == ["LIV-82"]
    bodies = [
        str(c["variables"].get("body") or "")
        for c in graphql.calls
        if "commentCreate" in c["query"]
    ]
    assert any("bc-e9af8de1-3155-44db-81a2-075d464d3c8a" in b for b in bodies)
    assert any("cloud-launch" in b for b in bodies)


def test_liv_in_agent_name_counts_as_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    graphql = FakeLinear()
    result = mod.stamp_after_evidence(
        kind="cloud-launch",
        seat="systems",
        text="Implement the assigned outcome. Open a PR.",
        name="gcs-liv82-linear-stamp-after-turn-beat1740",
        bc_id="bc-aaaa",
        graphql=graphql,
    )
    assert result["posted"] is True
    assert "LIV-82" in result["identifiers"]


def test_black_swan_team_or_identifier_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    graphql = FakeLinear()
    graphql.team_key = "BSM"
    graphql.team_name = "Black Swan"
    result = mod.stamp_after_evidence(
        kind="mind-turn",
        seat="floor",
        text="Do not stamp BSM-1. This mail also has LIV-82.",
        graphql=graphql,
    )
    # GraphQL returned Black Swan team for LIV-82 → fail closed, no comment.
    if any("commentCreate" in c["query"] for c in graphql.calls):
        raise AssertionError("must not commentCreate on a non-LIV team")
    assert result["posted"] is False
    assert result["ok"] is False
    assert result["reason"] in {"not-living-sky", "black-swan"}

    graphql2 = FakeLinear()
    result2 = mod.stamp_after_evidence(
        kind="mind-turn",
        seat="floor",
        text="Stamp Black Swan BSM-12 only. Never Living Sky.",
        graphql=graphql2,
    )
    assert result2["posted"] is False
    assert graphql2.calls == []


def test_skip_seats_never_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    graphql = FakeLinear()
    for seat in ("donald", "orchestrator"):
        result = mod.stamp_after_evidence(
            kind="mind-turn",
            seat=seat,
            text=LIV_MAIL,
            graphql=graphql,
        )
        assert result["posted"] is False, seat
        assert result["reason"] == "skipSeats", seat
    assert graphql.calls == []


def test_graphql_error_fails_closed_no_fake_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    graphql = FakeLinear()
    graphql.raise_exc = RuntimeError("linear 401")
    result = mod.stamp_after_evidence(
        kind="mind-turn",
        seat="floor",
        text=LIV_MAIL,
        graphql=graphql,
    )
    assert result["posted"] is False
    assert result["ok"] is False
    assert result["reason"] in {"graphql", "http"}
    assert not result.get("comment_ids")


def test_operator_team_key_cannot_retarget_black_swan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    monkeypatch.setenv("GCS_LINEAR_TEAM_KEY", "BSM")
    mod = _stamp()
    graphql = FakeLinear()
    result = mod.stamp_after_evidence(
        kind="mind-turn",
        seat="floor",
        text=LIV_MAIL,
        graphql=graphql,
    )
    assert result["posted"] is False
    assert result["reason"] in {"not-living-sky", "black-swan"}
    assert graphql.calls == []


def test_process_once_stamps_after_real_turn_not_runner_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def spy(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"ok": True, "posted": True, "reason": "ok"}

    def ok_runner(prompt: str, **_kwargs: object) -> dict:
        return {"text": json.dumps({"ok": True, "echo": prompt})}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="turn_ok", runner=ok_runner)
    monkeypatch.setattr(mind, "after_mind_turn_stamp", spy)
    _append_inbox(state, "floor", "task-ok", LIV_MAIL)
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert calls and calls[0]["seat"] == "floor"
    assert calls[0]["mail"] == LIV_MAIL
    assert "task-ok" in str(calls[0].get("task_id") or "")

    calls.clear()

    def boom(_prompt: str, **_kwargs: object) -> dict:
        return {"text": "nope", "returncode": 2, "stderr": "runner exploded"}

    mind_fail, state_fail = _prep_mind(
        tmp_path, monkeypatch, unique="turn_fail", runner=boom
    )
    monkeypatch.setattr(mind_fail, "after_mind_turn_stamp", spy)
    _append_inbox(state_fail, "floor", "task-fail", LIV_MAIL)
    failed = mind_fail.process_once("floor")
    assert failed["consumed"] == 0
    assert calls == []


def test_hub_duplex_bot_bridge_do_not_import_linear_stamp() -> None:
    for path in (HUB_PY, DUPLEX_PY, BOT_BRIDGE_PY):
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        assert "liv_evidence_stamp" not in text, path.name
        assert "linear.app" not in lower, path.name
        assert "commentcreate" not in lower, path.name
        assert "LINEAR_API_KEY" not in text, path.name


def test_hub_source_still_returns_completed_as_receipt() -> None:
    text = HUB_PY.read_text(encoding="utf-8")
    assert "TASK_STATE_COMPLETED" in text
    assert "receipt" in text.lower()
    assert "liv_evidence_stamp" not in text


def test_launch_paths_stamp_after_cloud_launch_ok_not_before() -> None:
    bash = LAUNCH_SH.read_text(encoding="utf-8")
    ts = LAUNCH_TS.read_text(encoding="utf-8")
    assert "liv_evidence_stamp.py" in bash
    assert "cloud-launch" in bash
    assert "liv_evidence_stamp.py" in ts
    assert "cloud-launch" in ts
    # REST path: helper runs after the success printf, not on CLOUD_LAUNCH_ERR.
    ok_print = bash.index('printf \'%s\\n\' "CLOUD_LAUNCH_OK"')
    stamp_at = bash.index("liv_evidence_stamp.py")
    assert ok_print < stamp_at
    err_fn = bash.index("CLOUD_LAUNCH_ERR")
    # The first CLOUD_LAUNCH_ERR is the fail helper — stamp must not live there.
    assert "liv_evidence_stamp.py" not in bash[err_fn : err_fn + 400]
    ts_ok = ts.index("CLOUD_LAUNCH_OK")
    ts_stamp = ts.index("liv_evidence_stamp.py")
    assert ts_ok < ts_stamp


def test_secret_scan_fails_closed_on_linear_key_literals(tmp_path: Path) -> None:
    scan = _load(SECRET_SCAN, "gcs_secret_scan_liv")
    dirty = tmp_path / "leak.env"
    dirty.write_text(f"LINEAR_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    hits = scan.scan_text("leak.env", dirty.read_text(encoding="utf-8"))
    rules = {h[1] for h in hits}
    assert "linear_key_assignment" in rules or "linear_lin_api" in rules

    token_hits = scan.scan_text("x.py", 'TOKEN = "lin_api_' + 'abcdefghijklmnop"\n')
    assert any(h[1] == "linear_lin_api" for h in token_hits)

    clean = scan.scan_text(".env.example", "# LINEAR_API_KEY=\n")
    assert clean == []


def test_never_vendor_hermes() -> None:
    assert STAMP_PY.read_text(encoding="utf-8").lower().find("hermes") == -1
    if VENDOR.is_dir():
        names = {p.name.lower() for p in VENDOR.iterdir()}
        assert "hermes" not in names


def test_cli_hub_receipt_exits_without_posting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_KEY)
    mod = _stamp()
    rc = mod.main(
        [
            "--kind",
            "hub-receipt",
            "--seat",
            "floor",
            "--text",
            LIV_MAIL,
        ]
    )
    captured = capsys.readouterr()
    assert rc != 0
    assert "hub-receipt" in captured.out + captured.err
    assert "LINEAR_STAMP_OK" not in captured.out
