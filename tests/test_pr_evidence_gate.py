"""PR evidence gate: MERGE_REQUEST / QA need pasted pytest -q + secret_scan.

Empty GitHub leftover-green (MERGEABLE + check_runs=[]) is not a ship-gate.
A GitHub check named "pytest -q and secret_scan" SUCCESS is also not enough
without the paste (distinct from leftover LIV-94 #105/#88/#92). Do not
rebase those PRs. Do not twin beat1740 / GCS #117/#118 workflow files.
Do not remint leftover #140 (--name gcs-pr-evidence-gate-beat1849) or
cancelled tandem1914. This beat is scale1929 from current main (LIV-104
REPORT_TO stays). Never Bot CloudAgent. Palemon Linear is Living Sky
(LIV), never Black Swan.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

from fleet_ledger import notify_targets, notify_text  # noqa: E402
from pr_evidence import (  # noqa: E402
    evidence_text,
    has_pasted_pytest,
    has_pasted_secret_scan,
    has_pasted_ship_gate,
    is_empty_github_leftover_green,
    may_squash,
    merge_request_ready,
    parse_github_pull_url,
    should_hold_merge_request,
)

FEATURE = ROOT / "tests" / "features" / "pr_evidence_gate.feature"
EVIDENCE_PY = ROOT / "scripts" / "cloud" / "pr_evidence.py"
LEDGER = ROOT / "scripts" / "cloud" / "fleet_ledger.py"
FOOTER = ROOT / "scripts" / "directors" / "common_footer.txt"
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
CLOUD_DOC = ROOT / "docs" / "CLOUD.md"
ARCH = ROOT / "docs" / "ARCHITECTURE.md"
CLOUD_README = ROOT / "scripts" / "cloud" / "README.md"
QA_PROMPTS = (
    ROOT / "prompts" / "qa_a_director_prompt.txt",
    ROOT / "prompts" / "qa_b_director_prompt.txt",
    ROOT / "prompts" / "qa_a.txt",
    ROOT / "prompts" / "qa_b.txt",
)
QA_SOULS = (
    ROOT / "docs" / "studio" / "directors" / "souls" / "qa-a" / "SOUL.md",
    ROOT / "docs" / "studio" / "directors" / "souls" / "qa-b" / "SOUL.md",
)
QA_CARDS = (
    ROOT / "docs" / "a2a" / "cards" / "qa-a.json",
    ROOT / "docs" / "a2a" / "cards" / "qa-b.json",
)
GCS41 = "https://github.com/atebites-hub/grok-cloud-studio/pull/41"
GCS47 = "https://github.com/atebites-hub/grok-cloud-studio/pull/47"
GCS27 = "https://github.com/atebites-hub/grok-cloud-studio/pull/27"
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"
BLACK_SWAN = "blackswan" + ".money"
PASTE_OK = "12 passed in 1.23s\nsecret_scan=clean\n"
PYTEST_CMD = ".venv/bin/pytest -q"
SCAN_CMD = "python3 scripts/secret_scan.py"


def _finished(*, pr: str, extra: dict | None = None) -> dict:
    payload = {
        "runStatus": "FINISHED",
        "status": "FINISHED",
        "prUrl": pr,
        "name": "grunt",
        "url": "https://cursor.com/agents/bc-ev",
    }
    if extra:
        payload.update(extra)
    return payload


def test_feature_file_states_paste_law() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    assert "Empty GitHub leftover-green" in text or "empty GitHub leftover-green" in text
    assert "check_runs=[]" in text
    assert "MERGEABLE is not a substitute" in text
    assert PYTEST_CMD in text
    assert SCAN_CMD in text
    assert "secret_scan=clean" in text
    assert "MERGE_REQUEST" in text
    assert "Do not squash-merge CONFLICTING" in text or "CONFLICTING" in text
    assert "LIV-94" in text
    assert "#105" in text and "#88" in text and "#92" in text
    assert "beat1740" in text or "#117" in text
    assert "Never Bot CloudAgent" in text
    assert "Black Swan" in text
    assert "Hermes" in text
    assert "#140" in text
    assert "tandem1914" in text
    assert "scale1929" in text


def test_parse_github_pull_url() -> None:
    assert parse_github_pull_url(GCS41) == ("atebites-hub", "grok-cloud-studio", 41)
    assert parse_github_pull_url(GCS47) == ("atebites-hub", "grok-cloud-studio", 47)
    assert parse_github_pull_url("https://github.com/atebites-hub/grok-cloud-studio/pulls/27") == (
        "atebites-hub",
        "grok-cloud-studio",
        27,
    )
    assert parse_github_pull_url("https://cursor.com/agents/bc-x") is None
    assert parse_github_pull_url("none") is None
    assert parse_github_pull_url(None) is None


def test_empty_mergeable_is_leftover_green_not_evidence() -> None:
    for pr in (GCS41, GCS47, GCS27):
        payload = _finished(
            pr=pr,
            extra={
                "emptyChecks": True,
                "checkRuns": 0,
                "mergeableState": "clean",
                "shipGateOk": False,
            },
        )
        assert is_empty_github_leftover_green(payload) is True
        assert merge_request_ready(payload) is False
        assert should_hold_merge_request(payload) is True


def test_github_check_success_without_paste_is_not_evidence() -> None:
    """Distinct from leftover LIV-94: CI check name is not the MERGE_REQUEST gate."""
    payload = _finished(
        pr=GCS41,
        extra={
            "emptyChecks": False,
            "checkRuns": 1,
            "shipGateOk": True,
            "mergeableState": "clean",
            "result": "GitHub check pytest -q and secret_scan SUCCESS",
        },
    )
    assert is_empty_github_leftover_green(payload) is False
    assert has_pasted_ship_gate(evidence_text(payload)) is False
    assert merge_request_ready(payload) is False
    assert should_hold_merge_request(payload) is True


def test_zero_passed_is_not_paste() -> None:
    text = "0 passed in 0.01s\nsecret_scan=clean\n"
    assert has_pasted_pytest(text) is False
    assert has_pasted_secret_scan(text) is True
    assert has_pasted_ship_gate(text) is False


def test_failed_pytest_is_not_paste() -> None:
    text = "1 failed, 3 passed in 0.12s\nsecret_scan=clean\n"
    assert has_pasted_pytest(text) is False
    assert has_pasted_ship_gate(text) is False


def test_pasted_pytest_and_scan_is_evidence() -> None:
    assert has_pasted_pytest(PASTE_OK) is True
    assert has_pasted_secret_scan(PASTE_OK) is True
    assert has_pasted_ship_gate(PASTE_OK) is True
    payload = _finished(pr=GCS41, extra={"result": PASTE_OK})
    assert merge_request_ready(payload) is True
    assert should_hold_merge_request(payload) is False


def test_paste_in_merge_request_body_counts() -> None:
    payload = _finished(
        pr=GCS41,
        extra={"emptyChecks": True, "mergeableState": "clean", "merge_request": PASTE_OK},
    )
    assert is_empty_github_leftover_green(payload) is True
    assert merge_request_ready(payload) is True
    assert should_hold_merge_request(payload) is False


def test_conflicting_must_not_squash() -> None:
    payload = _finished(
        pr=GCS41,
        extra={"result": PASTE_OK, "mergeableState": "dirty"},
    )
    assert may_squash(payload) is False
    assert merge_request_ready(payload) is False
    conflicting = _finished(
        pr=GCS47,
        extra={"result": PASTE_OK, "mergeableState": "conflicting"},
    )
    assert may_squash(conflicting) is False
    assert should_hold_merge_request(conflicting) is True


def test_non_github_pr_url_does_not_invent_github_leftover_green() -> None:
    payload = _finished(pr="https://example.test/pr/1")
    assert is_empty_github_leftover_green(payload) is False
    assert should_hold_merge_request(payload) is False


def test_notify_text_holds_empty_leftover_green() -> None:
    text = notify_text("bc-ev", _finished(pr=GCS41, extra={"emptyChecks": True}))
    assert "FLEET_DONE" in text
    assert "HOLD" in text
    assert "MERGE_REQUEST" in text
    assert "Do not ping QA MERGE_REQUEST" in text
    assert MERGE_READY not in text
    assert PYTEST_CMD in text
    assert SCAN_CMD in text
    assert "leftover-green" in text or "empty GitHub" in text


def test_notify_text_merge_request_when_paste_present() -> None:
    text = notify_text("bc-ev", _finished(pr=GCS41, extra={"result": PASTE_OK}))
    assert "FLEET_DONE / PR_READY" in text
    assert MERGE_READY in text
    assert "Do not ping QA MERGE_REQUEST" not in text
    assert "HOLD" not in text


def test_cli_judge_hold_then_ok() -> None:
    hold = subprocess.run(
        ["python3", str(EVIDENCE_PY), "judge"],
        cwd=str(ROOT),
        input=json.dumps(_finished(pr=GCS41, extra={"emptyChecks": True})),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert hold.returncode != 0, hold.stdout + hold.stderr
    assert "PR_EVIDENCE_HOLD" in hold.stdout
    ok = subprocess.run(
        ["python3", str(EVIDENCE_PY), "judge"],
        cwd=str(ROOT),
        input=json.dumps(_finished(pr=GCS41, extra={"result": PASTE_OK})),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "PR_EVIDENCE_OK" in ok.stdout


def test_cli_does_not_print_tokens() -> None:
    env = {
        **os.environ,
        "GH_TOKEN": "not-a-real-token",
        "GITHUB_TOKEN": "not-a-real-token",
        "CURSOR_API_KEY": "not-a-real-cursor-key",
    }
    proc = subprocess.run(
        ["python3", str(EVIDENCE_PY), "judge"],
        cwd=str(ROOT),
        env=env,
        input=json.dumps(_finished(pr=GCS41, extra={"result": PASTE_OK})),
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert "not-a-real-token" not in blob
    assert "not-a-real-cursor-key" not in blob


def test_qa_prompts_require_paste_and_refuse_leftover_green() -> None:
    for path in QA_PROMPTS + QA_SOULS:
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        assert "empty github" in low or "leftover-green" in low
        assert "pytest" in low
        assert "secret_scan" in low
        assert "conflicting" in low
        assert "force-push" in low
        assert BLACK_SWAN not in low
        assert "bot cloudagent" not in low or "never bot cloudagent" in low


def test_qa_cards_name_paste_gate() -> None:
    for path in QA_CARDS:
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        assert "empty github" in low or "leftover-green" in low or "paste" in low
        assert "pytest" in low
        assert "secret_scan" in low


def test_footer_holds_merge_request_without_paste() -> None:
    text = FOOTER.read_text(encoding="utf-8")
    low = text.lower()
    assert "merge_request" in low
    assert "leftover-green" in low or "empty github" in low
    assert PYTEST_CMD in text
    assert SCAN_CMD in text
    assert "conflicting" in low
    assert "never bot cloudagent" in low


def test_docs_name_paste_gate_not_empty_ci() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    arch = ARCH.read_text(encoding="utf-8")
    how = CLOUD_README.read_text(encoding="utf-8")
    for blob in (agents, readme, cloud, arch, how):
        low = blob.lower()
        assert "merge_request" in low or "empty github" in low or "leftover-green" in low
        assert PYTEST_CMD in blob or "pytest -q" in blob
        assert "secret_scan" in blob
        assert BLACK_SWAN not in low
    assert "pr_evidence.py" in agents or "pr_evidence.py" in how or "pr_evidence.py" in cloud


def test_does_not_twin_beat1740_workflow() -> None:
    wf_dir = ROOT / ".github" / "workflows"
    names = {p.name for p in wf_dir.iterdir() if p.suffix in {".yml", ".yaml"}}
    assert "gcs-github-ship-gate-workflows-beat1740.yml" not in names
    assert "ship-gate.yml" in names
    src = EVIDENCE_PY.read_text(encoding="utf-8") if EVIDENCE_PY.is_file() else ""
    ledger = LEDGER.read_text(encoding="utf-8")
    assert "ship_gate_evidence" not in src
    assert "ship_gate_evidence" not in ledger
    assert BLACK_SWAN not in src.lower()
    assert "vendor/hermes" not in src.lower()
    assert "gcs-pr-evidence-gate-beat1849" not in src
    assert "tandem1914" not in src


def test_ledger_imports_pr_evidence_not_leftover_module() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    assert "pr_evidence" in text
    assert "ship_gate_evidence" not in text
    assert "should_hold_merge_request" in text


def test_does_not_regress_liv104_report_to() -> None:
    """Leftover #140 predated LIV-104; this gate must keep REPORT_TO pings."""
    text = LEDGER.read_text(encoding="utf-8")
    assert "notify_targets" in text
    assert "REPORT_TO" in text
    assert "report_to_seat" in text
    assert notify_targets("ops")[0] == "ops"
