#!/usr/bin/env python3
"""LIV-41: a director/mind turn that finds RUNNING < 8 execs the launcher.

Grok Build directors and opted-in minds count latest-run ``runStatus=RUNNING``
for the bound repo, then ``subprocess`` ``scripts/launch-cloud-extra-high.sh``.
Leftover agent ``ACTIVE``+``FINISHED`` shells are not workers. ``CREATING`` is
not ``RUNNING``. Floor is ``GCS_CLOUD_MIN_RUNNING`` (default 8).

This is the turn-exec path. It is not Donald cron (host-ticker only enqueues
ACP_PING). It is not Bot CloudAgent. It does not remint the Python capacity
beat (GCS #65) or the FAIL-without-spawn transcript judge (GCS #75).

Stdlib only. Never prints API keys. Living Sky LIV, never Black Swan.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import canonical_seat, skip_seats  # noqa: E402

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))

DEFAULT_MIN_RUNNING = 8
DEFAULT_LIST_LIMIT = 100
LAUNCH_REL = "scripts/launch-cloud-extra-high.sh"
TURN_AGENT_NAME = "gcs-liv41-turn-exec"
RESERVED_SPAWN_NAME = "gcs-liv41-mind-must-launch"
RUNNING_STATUS = "RUNNING"
FILL_PROMPT = (
    "LIV-41 turn exec. Implement the assigned outcome. Open a PR. "
    "Model grok-4.6 extra-high (xhigh), fast=false. Never Bot CloudAgent."
)
_BOT_NAMES = frozenset(
    {
        "donald",
        "orchestrator",
        "grok-bot",
        "bot",
        "bot-cloudagent",
        "grok bot",
    }
)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(CURSOR_API_KEY|GCS_WEBHOOK_SECRET|Authorization|Bearer|"
    r"server-key|ACP_SECRET|api[_-]?key)\s*[=:]\s*\S+"
)
LaunchFn = Callable[..., str]


def redact(text: str) -> str:
    """Strip credential assignments. Never print secrets."""
    if not text:
        return text
    return _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)


def min_running(raw: str | None = None) -> int:
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if not text:
        return DEFAULT_MIN_RUNNING
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_MIN_RUNNING
    return value if value > 0 else DEFAULT_MIN_RUNNING


def bound_repo(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    for key in ("GCS_CLOUD_REPO", "CLOUD_REPO_URL", "CURSOR_CLOUD_REPO"):
        raw = str(source.get(key) or "").strip()
        if raw:
            return raw
    return ""


def normalize_repo(url: str) -> str:
    """org/name key for https, ssh, and .git forms of the same remote."""
    text = (url or "").strip()
    if not text:
        return ""
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text.split(":", 1)[1]
    text = text.rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    lowered = text.lower()
    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "https://www.github.com/",
        "http://www.github.com/",
    ):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower().rstrip("/")


def normalize_run_status(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return "none"
    upper = text.upper()
    if upper == "NONE":
        return "none"
    return upper


def is_running_status(raw: str | None) -> bool:
    """True only for runStatus RUNNING. Never agent ACTIVE. Never CREATING."""
    return normalize_run_status(raw) == RUNNING_STATUS


def is_bot_cloudagent_name(name: str, bot_agent_id: str = "") -> bool:
    raw = (name or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if lowered in _BOT_NAMES:
        return True
    if "bot cloudagent" in lowered:
        return True
    bot_id = (bot_agent_id or os.environ.get("GCS_BOT_AGENT_ID") or "").strip()
    if bot_id and raw == bot_id:
        return True
    return False


def is_forbidden_spawn_name(name: str, bot_agent_id: str = "") -> bool:
    raw = (name or "").strip()
    if not raw:
        return False
    if raw.lower() == RESERVED_SPAWN_NAME.lower():
        return True
    return is_bot_cloudagent_name(raw, bot_agent_id=bot_agent_id)


def is_skip_seat(seat: str) -> bool:
    key = canonical_seat(seat, ROOT)
    skipped = skip_seats(ROOT)
    return key in skipped or seat.strip().lower() in skipped or key in _BOT_NAMES


def _collect_repo_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    repo = payload.get("repo")
    if isinstance(repo, str) and repo.strip():
        urls.append(repo.strip())
    repos = payload.get("repos") or payload.get("repositories") or []
    if isinstance(repos, list):
        for item in repos:
            if isinstance(item, str) and item.strip():
                urls.append(item.strip())
            elif isinstance(item, dict):
                found = str(
                    item.get("url") or item.get("repository") or item.get("repo") or ""
                ).strip()
                if found:
                    urls.append(found)
    git = payload.get("git")
    if isinstance(git, dict):
        for branch in git.get("branches") or []:
            if not isinstance(branch, dict):
                continue
            found = str(branch.get("repoUrl") or branch.get("url") or "").strip()
            if found:
                urls.append(found)
    return urls


def row_repo_urls(row: dict[str, Any]) -> list[str]:
    return _collect_repo_urls(row)


def count_running_for_repo(rows: list[dict[str, Any]], repo: str) -> int:
    """Count runStatus=RUNNING on this bound remote. Unbound rows do not count."""
    want = normalize_repo(repo)
    if not want:
        return 0
    n = 0
    for row in rows:
        urls = row_repo_urls(row)
        if not urls:
            continue
        if not any(normalize_repo(url) == want for url in urls):
            continue
        status = row.get("runStatus")
        if status is None:
            status = row.get("run_status")
        if is_running_status(str(status) if status is not None else ""):
            n += 1
    return n


def load_cursor_api_key() -> str:
    existing = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if existing:
        return existing
    raw_path = (os.environ.get("CURSOR_AGENT_ENV") or "").strip()
    path = Path(raw_path) if raw_path else Path.home() / ".config" / "cursor" / "agent.env"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(?:export\s+)?CURSOR_API_KEY\s*=\s*(.*)$", line)
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        value = value.strip()
        if value:
            return value
    return ""


def _api_base() -> str:
    return (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")


def _http_timeout() -> float:
    raw = (os.environ.get("CLOUD_CURL_MAX_TIME") or "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return 15.0


def http_get_json(path: str, *, key: str, timeout: float | None = None) -> Any | None:
    url = f"{_api_base()}{path}"
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
    )
    limit = timeout if timeout is not None else _http_timeout()
    try:
        with urllib.request.urlopen(req, timeout=limit) as resp:
            blob = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _unwrap(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def fetch_fleet_rows(*, key: str | None = None) -> list[dict[str, Any]]:
    """List agents, bind repo via GET agent (fail closed), runStatus via latest run."""
    api_key = (key if key is not None else load_cursor_api_key()).strip()
    if not api_key:
        return []
    timeout = _http_timeout()
    payload = http_get_json(f"/v1/agents?limit={DEFAULT_LIST_LIMIT}", key=api_key, timeout=timeout)
    if not isinstance(payload, dict):
        return []
    items = payload.get("items") or payload.get("agents") or []
    if not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        agent = _unwrap(item, "agent")
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("id") or agent.get("agentId") or "").strip()
        if not agent_id:
            continue
        detail = http_get_json(f"/v1/agents/{agent_id}", key=api_key, timeout=timeout)
        detail_agent: dict[str, Any] = agent
        if isinstance(detail, dict):
            unwrapped = _unwrap(detail, "agent")
            if isinstance(unwrapped, dict):
                detail_agent = unwrapped
        urls = _collect_repo_urls(detail_agent)
        run_id = str(
            detail_agent.get("latestRunId")
            or agent.get("latestRunId")
            or agent.get("runId")
            or ""
        ).strip()
        run_status = "none"
        if run_id:
            run_payload = http_get_json(
                f"/v1/agents/{agent_id}/runs/{run_id}", key=api_key, timeout=timeout
            )
            if isinstance(run_payload, dict):
                run_obj = _unwrap(run_payload, "run")
                if isinstance(run_obj, dict):
                    run_status = normalize_run_status(
                        str(run_obj.get("status") or run_obj.get("runStatus") or "")
                    )
                    for extra in _collect_repo_urls(run_obj):
                        if extra not in urls:
                            urls.append(extra)
        if not urls:
            continue
        rows.append(
            {
                "id": agent_id,
                "agentStatus": str(detail_agent.get("status") or agent.get("status") or ""),
                "runStatus": run_status,
                "latestRunId": run_id,
                "repos": urls,
                "repo": urls[0],
            }
        )
    return rows


def exec_launcher(
    prompt: str,
    *,
    name: str = "",
    root: Path | None = None,
    timeout: int = 180,
) -> str:
    """Create one Extra High grunt via the real PATH launcher. Never Bot CloudAgent."""
    if is_forbidden_spawn_name(name):
        return "CLOUD_LAUNCH_ERR Bot CloudAgent names are refused"
    base = root if root is not None else ROOT
    script = base / "scripts" / "launch-cloud-extra-high.sh"
    if not script.is_file():
        return "CLOUD_LAUNCH_ERR missing scripts/launch-cloud-extra-high.sh"
    env = os.environ.copy()
    env["GCS_ROOT"] = str(base)
    cmd = ["bash", str(script)]
    if name.strip():
        cmd.extend(["--name", name.strip()])
    cmd.append(prompt)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(base),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return "CLOUD_LAUNCH_ERR missing bash"
    except subprocess.TimeoutExpired:
        return f"CLOUD_LAUNCH_ERR timeout after {timeout}s"
    except OSError as e:
        return f"CLOUD_LAUNCH_ERR {e}"
    blob = (proc.stdout or "") + (proc.stderr or "")
    text = redact(blob.strip() or f"rc={proc.returncode}")
    if proc.returncode != 0 and "CLOUD_LAUNCH_OK" not in text:
        if "CLOUD_LAUNCH_ERR" not in text:
            return f"CLOUD_LAUNCH_ERR rc={proc.returncode} {text}"
        return text
    return text


def _invoke_launch(
    launch: LaunchFn | None,
    repo: str,
    prompt: str,
    name: str,
) -> str:
    if launch is None:
        return exec_launcher(prompt, name=name)
    try:
        return launch(repo, prompt, name=name)
    except TypeError:
        return launch(repo, prompt)


def director_mind_turn(
    *,
    seat: str,
    mail: str = "",
    rows: list[dict[str, Any]] | None = None,
    launch: LaunchFn | None = None,
    name: str | None = None,
    min_running_override: int | None = None,
) -> dict[str, Any]:
    """Find runStatus RUNNING for the bound repo; exec the launcher when < floor.

    ``mail`` is the mind turn text (ACP_PING / LAUNCH / …). Python does not
    enqueue ticker lines. skipSeats (donald/orchestrator) never exec.
    """
    key = canonical_seat(seat, ROOT)
    _ = mail
    agent_name = (name if name is not None else TURN_AGENT_NAME).strip()
    if is_skip_seat(key):
        return {
            "execd": False,
            "reason": "skipSeats",
            "seat": key,
            "running": 0,
            "script": LAUNCH_REL,
        }
    if is_forbidden_spawn_name(agent_name):
        return {
            "execd": False,
            "reason": "bot-cloudagent",
            "seat": key,
            "running": 0,
            "script": LAUNCH_REL,
            "name": agent_name,
        }
    repo = bound_repo()
    if not repo:
        return {
            "execd": False,
            "reason": "no-repo",
            "seat": key,
            "running": 0,
            "script": LAUNCH_REL,
        }
    fleet = rows if rows is not None else fetch_fleet_rows()
    running = count_running_for_repo(fleet, repo)
    floor = min_running() if min_running_override is None else min_running_override
    if running >= floor:
        return {
            "execd": False,
            "reason": "at-floor",
            "seat": key,
            "running": running,
            "script": LAUNCH_REL,
        }
    blob = _invoke_launch(launch, repo, FILL_PROMPT, agent_name)
    ok = "CLOUD_LAUNCH_OK" in (blob or "")
    return {
        "execd": ok,
        "reason": "under-floor" if ok else "launch-fail",
        "seat": key,
        "running": running,
        "script": LAUNCH_REL,
        "name": agent_name,
        "launch": redact(blob),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Director/mind turn: if runStatus RUNNING < 8, exec "
            "scripts/launch-cloud-extra-high.sh"
        )
    )
    parser.add_argument("--seat", required=True, help="Director seat (floor, ops, …)")
    parser.add_argument("--mail-file", default="", help="Optional path to this turn's mail")
    parser.add_argument(
        "--name",
        default=TURN_AGENT_NAME,
        help="Extra High --name (refused for donald / reserved FINISHED name)",
    )
    args = parser.parse_args(argv)
    mail = ""
    if args.mail_file:
        path = Path(args.mail_file)
        if path.is_file():
            mail = path.read_text(encoding="utf-8")
    result = director_mind_turn(seat=args.seat, mail=mail, name=args.name)
    print(json.dumps(result, ensure_ascii=False))
    if result.get("reason") == "launch-fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
