#!/usr/bin/env python3
"""Judge MERGE_REQUEST / QA squash evidence.

Empty GitHub leftover-green (MERGEABLE + check_runs=[]) is not a ship-gate.
A GitHub check named "pytest -q and secret_scan" SUCCESS is not paste.
Require pasted `.venv/bin/pytest -q` (`N passed`, N>=1, no failed summary)
and `python3 scripts/secret_scan.py` (`secret_scan=clean`).
CONFLICTING / DIRTY is never squash. Do not remint ship-gate.yml.
Never Bot CloudAgent. Palemon Linear is Living Sky (LIV), not Black Swan.
Never prints tokens — verdict JSON only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PASSED_RE = re.compile(r"(?m)(\d+) passed")
FAILED_RE = re.compile(r"(?m)(\d+) failed")
SCAN_OK = "secret_scan=clean"

CONFLICT_STATES = frozenset({"CONFLICTING", "DIRTY"})
PASTE_PAYLOAD_KEYS = (
    "evidence",
    "paste",
    "notes",
    "summary",
    "body",
    "prBody",
    "result",
)


@dataclass(frozen=True)
class Verdict:
    allow_squash: bool
    hold_merge_request: bool
    reason: str
    pytest_passed: int | None
    secret_scan_clean: bool


def pytest_passed_count(text: str) -> int | None:
    hits = PASSED_RE.findall(text or "")
    if not hits:
        return None
    return int(hits[-1])


def pytest_failed_count(text: str) -> int:
    hits = FAILED_RE.findall(text or "")
    if not hits:
        return 0
    return int(hits[-1])


def has_secret_scan_clean(text: str) -> bool:
    return SCAN_OK in (text or "")


def has_paste_evidence(text: str) -> bool:
    passed = pytest_passed_count(text)
    if passed is None or passed < 1:
        return False
    if pytest_failed_count(text) > 0:
        return False
    return has_secret_scan_clean(text)


def is_leftover_green(*, mergeable: str, check_runs: list[Any] | None) -> bool:
    state = (mergeable or "").strip().upper()
    return state == "MERGEABLE" and not check_runs


def is_conflicting(*, mergeable: str, merge_state: str | None = None) -> bool:
    merge = (mergeable or "").strip().upper()
    extra = (merge_state or "").strip().upper()
    return merge in CONFLICT_STATES or extra in CONFLICT_STATES


def paste_from_payload(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    chunks: list[str] = []
    for key in PASTE_PAYLOAD_KEYS:
        val = payload.get(key)
        if val:
            chunks.append(str(val))
    return "\n".join(chunks)


def judge(
    paste: str,
    *,
    mergeable: str = "",
    merge_state: str = "",
    check_runs: list[Any] | None = None,
) -> Verdict:
    passed = pytest_passed_count(paste)
    scan_ok = has_secret_scan_clean(paste)
    if is_conflicting(mergeable=mergeable, merge_state=merge_state):
        return Verdict(
            allow_squash=False,
            hold_merge_request=True,
            reason="conflicting",
            pytest_passed=passed,
            secret_scan_clean=scan_ok,
        )
    if not has_paste_evidence(paste):
        if is_leftover_green(mergeable=mergeable, check_runs=check_runs):
            reason = "leftover-green"
        else:
            reason = "missing-paste"
        return Verdict(
            allow_squash=False,
            hold_merge_request=True,
            reason=reason,
            pytest_passed=passed,
            secret_scan_clean=scan_ok,
        )
    return Verdict(
        allow_squash=True,
        hold_merge_request=False,
        reason="ok",
        pytest_passed=passed,
        secret_scan_clean=scan_ok,
    )


def _load_paste(path: str) -> str:
    if not path or path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _load_checks(raw: str) -> list[Any]:
    text = (raw or "[]").strip() or "[]"
    candidate = Path(text)
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8")
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        runs = data.get("check_runs") or data.get("statusCheckRollup") or []
        if isinstance(runs, list):
            return runs
    return []


def _verdict_json(verdict: Verdict) -> str:
    return json.dumps(asdict(verdict), separators=(",", ":"), sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    judge_p = sub.add_parser("judge", help="Print squash verdict JSON (never the paste)")
    judge_p.add_argument("--paste-file", default="-", help="Paste file or - for stdin")
    judge_p.add_argument("--mergeable", default="")
    judge_p.add_argument("--merge-state", default="")
    judge_p.add_argument("--checks-json", default="[]")
    args = parser.parse_args(argv)
    if args.cmd != "judge":
        return 2
    paste = _load_paste(args.paste_file)
    checks = _load_checks(args.checks_json)
    verdict = judge(
        paste,
        mergeable=args.mergeable,
        merge_state=args.merge_state,
        check_runs=checks,
    )
    sys.stdout.write(_verdict_json(verdict) + "\n")
    return 0 if verdict.allow_squash else 1


if __name__ == "__main__":
    raise SystemExit(main())
