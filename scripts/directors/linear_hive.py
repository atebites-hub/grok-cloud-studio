#!/usr/bin/env python3
"""Hive Living Sky Linear stamper. Runs after a successful mind turn.

Python (mailbox + pin + stay-up) comments Linear. Grok Bot does not.
Donald is notified via A2A only. Stdlib only. Never print secrets.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
DEFAULT_LINEAR_API = "https://api.linear.app/graphql"
DEFAULT_TEAM_KEYS = ("LIV",)
DEFAULT_A2A_SEAT = "donald"
DEFAULT_MAX_ISSUES = 5
DEFAULT_COMMENT_CHARS = 1500
DEFAULT_TIMEOUT = 10.0

ISSUE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,7}-\d+)\b")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(CURSOR_API_KEY|LINEAR_API_KEY|GCS_WEBHOOK_SECRET|Authorization|Bearer|"
    r"server-key|ACP_SECRET|api[_-]?key)\s*[=:]\s*\S+"
)

COMMENT_CREATE = (
    "mutation HiveComment($input: CommentCreateInput!) {"
    " commentCreate(input: $input) { success comment { id url } } }"
)

SendFn = Callable[..., str]
GraphQLFn = Callable[..., dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(text: str) -> str:
    """Strip credential assignments. Never print secrets."""
    if not text:
        return text
    return _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)


def _clip(text: str, limit: int) -> str:
    blob = text or ""
    if len(blob) <= limit:
        return blob
    if limit <= 1:
        return "…"
    return blob[: limit - 1] + "…"


def linear_disabled() -> bool:
    raw = (os.environ.get("GCS_LINEAR_DISABLE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def linear_api_key() -> str:
    return (os.environ.get("LINEAR_API_KEY") or "").strip()


def linear_api_url() -> str:
    return (os.environ.get("GCS_LINEAR_API") or DEFAULT_LINEAR_API).strip() or DEFAULT_LINEAR_API


def linear_timeout() -> float:
    raw = (os.environ.get("GCS_LINEAR_TIMEOUT") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT


def linear_max_issues() -> int:
    raw = (os.environ.get("GCS_LINEAR_MAX_ISSUES") or "").strip()
    if not raw:
        return DEFAULT_MAX_ISSUES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_ISSUES


def comment_char_limit() -> int:
    raw = (os.environ.get("GCS_LINEAR_COMMENT_CHARS") or "").strip()
    if not raw:
        return DEFAULT_COMMENT_CHARS
    try:
        return max(200, int(raw))
    except ValueError:
        return DEFAULT_COMMENT_CHARS


def linear_team_keys() -> tuple[str, ...]:
    raw = (os.environ.get("GCS_LINEAR_TEAM_KEYS") or "").strip()
    if not raw:
        return DEFAULT_TEAM_KEYS
    keys = tuple(part.strip().upper() for part in raw.split(",") if part.strip())
    return keys or DEFAULT_TEAM_KEYS


def linear_a2a_seat() -> str:
    """Donald A2A only unless GCS_LINEAR_A2A_SEAT overrides."""
    raw = (os.environ.get("GCS_LINEAR_A2A_SEAT") or "").strip().lower().replace("_", "-")
    if raw:
        return raw
    return DEFAULT_A2A_SEAT


def extract_issue_ids(text: str) -> list[str]:
    """Living Sky identifiers (default team LIV). Order-preserving unique."""
    if not text:
        return []
    allowed = set(linear_team_keys())
    found: list[str] = []
    seen: set[str] = set()
    for match in ISSUE_RE.findall(text):
        prefix = match.split("-", 1)[0]
        if prefix not in allowed:
            continue
        if match in seen:
            continue
        seen.add(match)
        found.append(match)
        if len(found) >= linear_max_issues():
            break
    return found


def format_comment(payload: dict[str, Any], issue: str) -> str:
    limit = comment_char_limit()
    seat = str(payload.get("seat") or "")
    task_id = str(payload.get("task_id") or "")
    offset = payload.get("offset")
    backend = str(payload.get("backend") or "")
    prompt = _clip(redact(str(payload.get("prompt") or "")), limit)
    turn = _clip(redact(str(payload.get("assistant_text") or "")), limit)
    lines = [
        "Hive mind turn (autonomous Living Sky stamp). Not Grok Bot.",
        "",
        f"issue={issue} seat={seat} task={task_id} offset={offset} runner={backend}",
        "",
        "Mail:",
        prompt,
        "",
        "Turn:",
        turn,
    ]
    return "\n".join(lines)


def graphql_post(
    payload: dict[str, Any], *, headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    """POST GraphQL. Returns parsed JSON or an errors object. Never prints secrets."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        linear_api_url(),
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = redact(exc.read().decode("utf-8", errors="replace"))[:400]
        return {"errors": [{"message": f"http-{exc.code} {body}"}]}
    except urllib.error.URLError as exc:
        return {"errors": [{"message": f"url-error {type(exc.reason).__name__}"}]}
    except (TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"errors": [{"message": f"{type(exc).__name__}"}]}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"errors": [{"message": "invalid-json"}]}
    if isinstance(parsed, dict):
        return parsed
    return {"errors": [{"message": "unexpected-graphql"}]}


def comment_on_issue(
    issue: str,
    body: str,
    *,
    graphql_post: GraphQLFn | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """commentCreate against a Linear identifier (e.g. LIV-82)."""
    key = (api_key if api_key is not None else linear_api_key()).strip()
    if not key:
        return {"ok": False, "reason": "no-key"}
    post = graphql_post if graphql_post is not None else globals()["graphql_post"]
    payload = {
        "query": COMMENT_CREATE,
        "variables": {"input": {"issueId": issue, "body": body}},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    parsed = post(payload, headers=headers, timeout=linear_timeout())
    errors = parsed.get("errors") if isinstance(parsed, dict) else None
    if errors:
        msg = ""
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            msg = str(errors[0].get("message") or "")
        reason = "http-error" if msg.startswith("http-") else "graphql-error"
        return {"ok": False, "reason": reason, "error": redact(msg)[:240]}
    data = parsed.get("data") if isinstance(parsed, dict) else None
    created = (data or {}).get("commentCreate") if isinstance(data, dict) else None
    if not isinstance(created, dict) or not created.get("success"):
        return {"ok": False, "reason": "linear-fail"}
    comment = created.get("comment") if isinstance(created.get("comment"), dict) else {}
    return {
        "ok": True,
        "reason": "ok",
        "comment_id": str(comment.get("id") or ""),
        "url": str(comment.get("url") or ""),
    }


def default_a2a_send(
    seat: str, text: str, from_seat: str = "", *, root: Path | None = None
) -> str:
    repo = Path(root or os.environ.get("GCS_ROOT") or ROOT)
    script = repo / "scripts" / "a2a" / "send.sh"
    if not script.is_file():
        return "A2A_SEND_FAIL missing send.sh"
    cmd = ["bash", str(script)]
    if from_seat:
        cmd.extend(["--from", from_seat])
    cmd.extend([seat, text])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"A2A_SEND_FAIL {type(exc).__name__}"
    out = redact((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return f"A2A_SEND_FAIL rc={proc.returncode} {out[:200]}"
    return out or "A2A_SEND_OK"


def _a2a_line(*, kind: str, seat: str, issue: str, payload: dict[str, Any], extra: str) -> str:
    task_id = str(payload.get("task_id") or "")
    offset = payload.get("offset")
    bits = [
        kind,
        f"seat={seat}",
        f"issue={issue}",
        f"task={task_id}",
        f"offset={offset}",
        "source=hive-mind",
    ]
    if extra:
        bits.append(extra)
    return " ".join(str(b) for b in bits)


def _notify_donald(
    send_fn: SendFn | None,
    *,
    mind_seat: str,
    text: str,
    root: Path | None,
) -> str:
    dest = linear_a2a_seat()
    fn = send_fn if send_fn is not None else default_a2a_send
    try:
        return str(fn(dest, text, from_seat=mind_seat))
    except TypeError:
        try:
            return str(fn(dest, text, from_seat=mind_seat, root=root))
        except TypeError:
            try:
                return str(fn(dest, text, mind_seat))
            except TypeError:
                return str(fn(dest, text))
    except Exception as exc:
        return f"A2A_SEND_FAIL {type(exc).__name__}"


def _append_receipt(state_dir: Path | None, seat: str, row: dict[str, Any]) -> None:
    if not seat:
        return
    base = state_dir
    if base is None:
        raw = (os.environ.get("GCS_A2A_STATE") or "").strip()
        base = Path(raw) if raw else ROOT / ".a2a-state"
    path = Path(base) / seat / "mind" / "linear.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(row)
        rec.setdefault("ts", _now())
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        return


def after_mind_turn(
    payload: dict[str, Any],
    *,
    send_fn: SendFn | None = None,
    graphql_post: GraphQLFn | None = None,
    state_dir: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Stamp Living Sky Linear, then A2A Donald. Never raise into the mind loop."""
    seat = str(payload.get("seat") or "")
    prompt = str(payload.get("prompt") or "")
    assistant = str(payload.get("assistant_text") or "")
    issues = extract_issue_ids(f"{prompt}\n{assistant}")
    dest = linear_a2a_seat()
    if not issues:
        print(f"LINEAR_SKIP seat={seat} reason=no-issue dest={dest}", flush=True)
        return {"ok": False, "reason": "no-issue", "issues": [], "dest": dest}

    issue_blob = ",".join(issues)
    if linear_disabled():
        line = _a2a_line(
            kind="LINEAR_SKIP",
            seat=seat,
            issue=issue_blob,
            payload=payload,
            extra="reason=disabled",
        )
        _notify_donald(send_fn, mind_seat=seat, text=line, root=root)
        print(f"LINEAR_SKIP seat={seat} issue={issue_blob} reason=disabled dest={dest}", flush=True)
        _append_receipt(state_dir, seat, {"reason": "disabled", "issues": issues})
        return {"ok": False, "reason": "disabled", "issues": issues, "dest": dest}

    key = linear_api_key()
    if not key:
        line = _a2a_line(
            kind="LINEAR_SKIP",
            seat=seat,
            issue=issue_blob,
            payload=payload,
            extra="reason=no-key",
        )
        _notify_donald(send_fn, mind_seat=seat, text=line, root=root)
        print(f"LINEAR_SKIP seat={seat} issue={issue_blob} reason=no-key dest={dest}", flush=True)
        _append_receipt(state_dir, seat, {"reason": "no-key", "issues": issues})
        return {"ok": False, "reason": "no-key", "issues": issues, "dest": dest}

    stamps: list[dict[str, Any]] = []
    overall_ok = True
    fail_reason = "ok"
    for issue in issues:
        body = format_comment(payload, issue)
        result = comment_on_issue(
            issue, body, graphql_post=graphql_post, api_key=key
        )
        stamps.append({"issue": issue, **{k: v for k, v in result.items() if k != "error"}})
        if not result.get("ok"):
            overall_ok = False
            fail_reason = str(result.get("reason") or "linear-fail")
            extra = f"reason={fail_reason}"
            kind = "LINEAR_FAIL"
        else:
            extra = "comment=ok"
            kind = "LINEAR_STAMP"
        line = _a2a_line(
            kind=kind, seat=seat, issue=issue, payload=payload, extra=extra
        )
        _notify_donald(send_fn, mind_seat=seat, text=line, root=root)
        print(
            f"{kind} seat={seat} issue={issue} dest={dest} reason={result.get('reason') or 'ok'}",
            flush=True,
        )

    reason = "ok" if overall_ok else fail_reason
    _append_receipt(
        state_dir,
        seat,
        {"reason": reason, "issues": issues, "ok": overall_ok},
    )
    return {
        "ok": overall_ok,
        "reason": reason,
        "issues": issues,
        "dest": dest,
        "stamps": stamps,
    }
