"""MERGE_REQUEST / QA must not treat empty GitHub leftover-green as ship-gate.

Require pasted `.venv/bin/pytest -q` (`N passed`, N>=1) and
`python3 scripts/secret_scan.py` (`secret_scan=clean`).

Does not rebase leftover OPEN #140 CONFLICTING or recent GHA-SUCCESS twins.
Does not remint `.github/workflows/ship-gate.yml` / `scripts/ci/ship-gate.sh`.
Never Bot CloudAgent. Palemon Linear is Living Sky (LIV), not Black Swan.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))

FEATURE = ROOT / "tests" / "features" / "pr_evidence_gate.feature"
MODULE = ROOT / "scripts" / "cloud" / "pr_evidence.py"
LEDGER = ROOT / "scripts" / "cloud" / "fleet_ledger.py"
WORKFLOW = ROOT / ".github" / "workflows" / "ship-gate.yml"
SHIP_GATE = ROOT / "scripts" / "ci" / "ship-gate.sh"
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
ARCH = ROOT / "docs" / "ARCHITECTURE.md"
CLOUD = ROOT / "docs" / "CLOUD.md"
CLOUD_README = ROOT / "scripts" / "cloud" / "README.md"
FOOTER = ROOT / "scripts" / "directors" / "common_footer.txt"

QA_SURFACES = (
    ROOT / "prompts" / "qa_a.txt",
    ROOT / "prompts" / "qa_a_director_prompt.txt",
    ROOT / "prompts" / "qa_b.txt",
    ROOT / "prompts" / "qa_b_director_prompt.txt",
    ROOT / "docs" / "studio" / "directors" / "souls" / "qa-a" / "SOUL.md",
    ROOT / "docs" / "studio" / "directors" / "souls" / "qa-b" / "SOUL.md",
    ROOT / "docs" / "a2a" / "cards" / "qa-a.json",
    ROOT / "docs" / "a2a" / "cards" / "qa-b.json",
)

PYTEST_CMD = ".venv/bin/pytest -q"
SCAN_CMD = "python3 scripts/secret_scan.py"
BLACK_SWAN = "blackswan" + ".money"

GOOD_PASTE = (
    f"$ {PYTEST_CMD}\n"
    "372 passed in 59.33s\n"
    f"$ {SCAN_CMD}\n"
    "secret_scan=clean\n"
)


def _import_pr_evidence():
    import pr_evidence as pe  # type: ignore

    return pe


def _import_fleet_ledger():
    import fleet_ledger as fl  # type: ignore

    return fl


def test_feature_binds_paste_gate_and_leftover_green() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "leftover-green" in fold
    assert "mergeable" in fold and "check_runs=[]" in fold
    assert "secret_scan=clean" in fold or "secret_scan=clean" in text
    assert "n passed" in fold
    assert "hold" in fold
    assert "conflicting" in fold
    assert "do not rebase" in fold or "#140" in text
    assert "ship-gate.yml" in fold
    assert "bot cloudagent" in fold
    assert "living sky" in fold
    assert BLACK_SWAN not in fold
    assert MODULE.is_file()
    assert "leftover-green" in MODULE.read_text(encoding="utf-8").lower()


def test_empty_leftover_green_is_not_ship_gate() -> None:
    pe = _import_pr_evidence()
    assert pe.is_leftover_green(mergeable="MERGEABLE", check_runs=[]) is True
    verdict = pe.judge(paste="", mergeable="MERGEABLE", check_runs=[])
    assert verdict.allow_squash is False
    assert verdict.hold_merge_request is True
    assert verdict.reason == "leftover-green"


def test_github_success_check_is_not_paste() -> None:
    pe = _import_pr_evidence()
    checks = [
        {
            "name": "pytest -q and secret_scan",
            "conclusion": "SUCCESS",
            "status": "COMPLETED",
        }
    ]
    assert pe.is_leftover_green(mergeable="MERGEABLE", check_runs=checks) is False
    verdict = pe.judge(paste="", mergeable="MERGEABLE", check_runs=checks)
    assert verdict.allow_squash is False
    assert verdict.hold_merge_request is True
    assert verdict.reason == "missing-paste"


def test_paste_requires_n_passed_and_secret_scan_clean() -> None:
    pe = _import_pr_evidence()
    only_scan = f"$ {SCAN_CMD}\nsecret_scan=clean\n"
    only_pass = f"$ {PYTEST_CMD}\n12 passed in 1.00s\n"
    zero = f"$ {PYTEST_CMD}\n0 passed in 0.10s\nsecret_scan=clean\n"
    failed = f"$ {PYTEST_CMD}\n2 failed, 10 passed in 1.00s\nsecret_scan=clean\n"
    assert pe.has_paste_evidence(only_scan) is False
    assert pe.has_paste_evidence(only_pass) is False
    assert pe.has_paste_evidence(zero) is False
    assert pe.has_paste_evidence(failed) is False
    assert pe.has_paste_evidence(GOOD_PASTE) is True
    assert pe.pytest_passed_count(GOOD_PASTE) == 372


def test_paste_allows_squash_even_when_github_checks_empty() -> None:
    pe = _import_pr_evidence()
    verdict = pe.judge(paste=GOOD_PASTE, mergeable="MERGEABLE", check_runs=[])
    assert verdict.allow_squash is True
    assert verdict.hold_merge_request is False
    assert verdict.reason == "ok"
    assert verdict.pytest_passed == 372
    assert verdict.secret_scan_clean is True


def test_conflicting_or_dirty_is_not_squash_even_with_paste() -> None:
    pe = _import_pr_evidence()
    dirty = pe.judge(
        paste=GOOD_PASTE,
        mergeable="CONFLICTING",
        merge_state="DIRTY",
        check_runs=[{"name": "pytest -q and secret_scan", "conclusion": "SUCCESS"}],
    )
    assert pe.is_conflicting(mergeable="CONFLICTING", merge_state="DIRTY") is True
    assert dirty.allow_squash is False
    assert dirty.hold_merge_request is True
    assert dirty.reason == "conflicting"
    dirty2 = pe.judge(paste=GOOD_PASTE, mergeable="MERGEABLE", merge_state="DIRTY")
    assert dirty2.allow_squash is False
    assert dirty2.reason == "conflicting"


def test_fleet_done_without_paste_holds_merge_request() -> None:
    fl = _import_fleet_ledger()
    text = fl.notify_text(
        "bc-ff424a8f-36a6-4c63-8dc8-01d7e538dc55",
        {
            "runStatus": "FINISHED",
            "prUrl": "https://github.com/atebites-hub/grok-cloud-studio/pull/140",
            "name": "gcs-pr-evidence-gate-beat2022",
            "url": "https://cursor.com/agents/bc-ff424a8f-36a6-4c63-8dc8-01d7e538dc55",
        },
    )
    fold = text.lower()
    assert "hold" in fold
    assert "merge_request" in fold
    assert "ping qa" not in fold
    assert "leftover-green" in fold or "paste" in fold


def test_fleet_done_with_paste_pings_qa_merge_request() -> None:
    fl = _import_fleet_ledger()
    text = fl.notify_text(
        "bc-ok",
        {
            "runStatus": "FINISHED",
            "prUrl": "https://github.com/atebites-hub/grok-cloud-studio/pull/153",
            "name": "gcs-pr-evidence-gate",
            "notes": GOOD_PASTE,
        },
    )
    fold = text.lower()
    assert "merge_request" in fold
    assert "hold merge_request" not in fold
    assert "ping qa" in fold


def test_cli_judge_prints_verdict_not_tokens(tmp_path: Path) -> None:
    paste = tmp_path / "paste.txt"
    key_name = "CURSOR_API_" + "KEY"
    fake = "sk-test-not-a-real-key"
    paste.write_text(GOOD_PASTE + f"{key_name}={fake}\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(MODULE),
            "judge",
            "--paste-file",
            str(paste),
            "--mergeable",
            "MERGEABLE",
            "--checks-json",
            "[]",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    blob = proc.stdout + proc.stderr
    assert fake not in blob
    assert key_name not in blob
    data = json.loads(proc.stdout)
    assert data["allow_squash"] is True
    assert data["reason"] == "ok"


def test_cli_judge_leftover_green_exits_nonzero() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(MODULE),
            "judge",
            "--paste-file",
            "/dev/null",
            "--mergeable",
            "MERGEABLE",
            "--checks-json",
            "[]",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode != 0
    data = json.loads(proc.stdout)
    assert data["allow_squash"] is False
    assert data["reason"] == "leftover-green"
    assert data["hold_merge_request"] is True


def test_qa_surfaces_require_paste_and_forbid_leftover_green() -> None:
    for path in QA_SURFACES:
        text = path.read_text(encoding="utf-8")
        fold = text.lower()
        assert PYTEST_CMD.split()[0] in text or "pytest -q" in text, path
        assert "secret_scan" in fold, path
        assert "leftover-green" in fold or "empty github" in fold, path
        assert "conflicting" in fold, path
        assert BLACK_SWAN not in fold, path


def test_footer_and_docs_name_the_paste_gate() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    fold = footer.lower()
    assert "leftover-green" in fold or "empty github" in fold
    assert "pytest -q" in footer
    assert "secret_scan" in fold
    agents = AGENTS.read_text(encoding="utf-8")
    assert "leftover-green" in agents.lower() or "empty GitHub" in agents
    assert "pr_evidence.py" in agents or "pasted" in agents.lower()
    readme = README.read_text(encoding="utf-8")
    assert "leftover-green" in readme.lower() or "empty GitHub" in readme
    assert "MERGE_REQUEST" in readme or "pasted" in readme.lower()
    cloud = CLOUD.read_text(encoding="utf-8")
    assert "pr_evidence" in cloud or "MERGE_REQUEST" in cloud
    assert PYTEST_CMD in cloud or "pytest -q" in cloud
    arch = ARCH.read_text(encoding="utf-8")
    assert "pr_evidence" in arch or "leftover-green" in arch.lower()
    cloud_readme = CLOUD_README.read_text(encoding="utf-8")
    assert "pr_evidence.py" in cloud_readme
    assert "judge" in cloud_readme


def test_does_not_remint_github_actions_ship_gate() -> None:
    wf = WORKFLOW.read_text(encoding="utf-8")
    sh = SHIP_GATE.read_text(encoding="utf-8")
    assert "scripts/ci/ship-gate.sh" in wf
    assert PYTEST_CMD in sh or "pytest -q" in sh
    assert "scripts/secret_scan.py" in sh
    module = MODULE.read_text(encoding="utf-8")
    assert "ship-gate.yml" in module or "do not remint" in module.lower()


def test_living_sky_not_black_swan() -> None:
    module = MODULE.read_text(encoding="utf-8")
    assert "Living Sky" in module
    assert "LIV" in module
    assert BLACK_SWAN not in module.lower()
    assert "Bot CloudAgent" in module or "Never Bot" in module
