#!/usr/bin/env python3
"""Capacity beat: launch Extra High until runStatus RUNNING >= floor.

Python mailbox side-effect for opted-in mind seats (LIV-41). Not a second
agent loop. Count only latest-run ``runStatus=RUNNING``. Agent ``status=ACTIVE``
leftovers (FINISHED shells) are not workers. ``CREATING`` is not ``RUNNING``.

Bound remotes (``GCS_CLOUD_REPOS``, ``GCS_CLOUD_REPO`` / ``CLOUD_REPO_URL``,
``GCS_GAME_REPO``) are counted separately. Floor is ``GCS_CLOUD_MIN_RUNNING``
(default 8). Creates go only through ``scripts/launch-cloud-extra-high.sh``
(grok-4.6 xhigh, fast=false). Never Bot CloudAgent.

Unbound agents (no ``repos[0].url`` and no run ``git.branches[].repoUrl``)
are dropped (fail closed). Stdlib only. Never prints API keys. Does not remint
``list.sh --repo``. Living Sky Linear is LIV, not Black Swan.
"""
from __future__ import annotations

import base64
import fcntl
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

DEFAULT_MIN_RUNNING = 8
DEFAULT_LIST_LIMIT = 100
RUNNING_STATUS = "RUNNING"
DEFAULT_FILL_PROMPT = (
    "CAPACITY_BEAT fill. Implement the next assigned outcome. Open a PR. "
    "Model grok-4.6 extra-high (xhigh), fast=false. Never Bot CloudAgent. "
    "Linear is Living Sky LIV."
)
_CAPACITY_BEAT_RE = re.compile(
    r"CAPACITY_BEAT|capacity\s+beat|\bACP_PING\b|STATUS/CONTINUE|\bCLOUD_CAPACITY\b",
    re.IGNORECASE,
)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(CURSOR_API_KEY|GCS_WEBHOOK_SECRET|Authorization|Bearer|"
    r"server-key|ACP_SECRET|api[_-]?key)\s*[=:]\s*\S+"
)


def _root() -> Path:
    raw = (os.environ.get("GCS_ROOT") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2]


def _state_dir() -> Path:
    raw = (os.environ.get("GCS_A2A_STATE") or "").strip()
    if raw:
        return Path(raw)
    return _root() / ".a2a-state"


def redact(text: str) -> str:
    if not text:
        return text
    return _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)


def min_running(raw: str | None = None) -> int:
    """GCS_CLOUD_MIN_RUNNING default 8. Explicit 0 disables launches."""
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if not text:
        return DEFAULT_MIN_RUNNING
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_MIN_RUNNING
    if value < 0:
        return DEFAULT_MIN_RUNNING
    return value


def is_capacity_beat(text: str) -> bool:
    """Host clock ACP_PING / explicit CAPACITY_BEAT. Not generic keep-alive chatter."""
    return bool(_CAPACITY_BEAT_RE.search(text or ""))


def choose_fill_prompt(text: str = "") -> str:
    """Do not send ACP_PING keep-alive prose to Extra High as the grunt prompt."""
    blob = (text or "").strip()
    if not blob or is_capacity_beat(blob):
        return DEFAULT_FILL_PROMPT
    return blob


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


def display_repo(url: str) -> str:
    key = normalize_repo(url)
    return key or (url or "").strip()


def bound_cloud_repos(env: dict[str, str] | None = None) -> list[str]:
    """Unique bound remotes. GCS_CLOUD_REPOS first, then single-repo knobs."""
    source = env if env is not None else os.environ
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        blob = raw.replace(";", ",")
        for part in blob.split(","):
            url = part.strip()
            if not url or url.startswith("#"):
                continue
            key = normalize_repo(url)
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(url)

    add(str(source.get("GCS_CLOUD_REPOS") or ""))
    for name in (
        "GCS_CLOUD_REPO",
        "CLOUD_REPO_URL",
        "CURSOR_CLOUD_REPO",
        "GCS_GAME_REPO",
    ):
        add(str(source.get(name) or ""))
    return found


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


def _unwrap(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def _collect_repo_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    repo = payload.get("repo")
    if isinstance(repo, str) and repo.strip():
        urls.append(repo.strip())
    for key in ("repoUrl", "repository"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            urls.append(val.strip())
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
    source = payload.get("source")
    if isinstance(source, dict):
        found = str(
            source.get("repository") or source.get("url") or source.get("repoUrl") or ""
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
    urls = _collect_repo_urls(row)
    extra = row.get("repos")
    if isinstance(extra, list):
        for item in extra:
            if isinstance(item, str) and item.strip() and item.strip() not in urls:
                urls.append(item.strip())
    return urls


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


def _list_limit() -> int:
    raw = (os.environ.get("CLOUD_LIST_LIMIT") or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return DEFAULT_LIST_LIMIT


def _extract_run_status(run_payload: Any) -> str:
    if not isinstance(run_payload, dict):
        return "none"
    run = _unwrap(run_payload, "run")
    if not isinstance(run, dict):
        return "none"
    return normalize_run_status(str(run.get("status") or run.get("runStatus") or ""))


def _annotate_agent(item: dict[str, Any], *, key: str, timeout: float) -> dict[str, Any] | None:
    agent = _unwrap(item, "agent")
    if not isinstance(agent, dict):
        return None
    agent_id = str(agent.get("id") or agent.get("agentId") or "").strip()
    if not agent_id:
        return None
    detail = http_get_json(f"/v1/agents/{agent_id}", key=key, timeout=timeout)
    detail_agent: dict[str, Any] = agent
    if isinstance(detail, dict):
        unwrapped = _unwrap(detail, "agent")
        if isinstance(unwrapped, dict):
            detail_agent = unwrapped
    run_id = str(
        detail_agent.get("latestRunId")
        or agent.get("latestRunId")
        or agent.get("runId")
        or ""
    ).strip()
    run_payload: Any = None
    if run_id:
        run_payload = http_get_json(
            f"/v1/agents/{agent_id}/runs/{run_id}", key=key, timeout=timeout
        )
    urls = _collect_repo_urls(detail_agent)
    if run_payload:
        run_obj = _unwrap(run_payload, "run")
        if isinstance(run_obj, dict):
            for extra in _collect_repo_urls(run_obj):
                if extra not in urls:
                    urls.append(extra)
    if not urls:
        return None
    run_status = _extract_run_status(run_payload)
    if run_status == "none":
        nested = detail_agent.get("latestRun") or detail_agent.get("run")
        if isinstance(nested, dict):
            run_status = normalize_run_status(
                str(nested.get("status") or nested.get("runStatus") or "")
            )
    return {
        "id": agent_id,
        "agentStatus": str(detail_agent.get("status") or agent.get("status") or ""),
        "runStatus": run_status,
        "latestRunId": run_id,
        "repos": urls,
        "repo": urls[0],
    }


def fetch_fleet_rows(*, key: str | None = None) -> list[dict[str, Any]]:
    """List agents, bind repo via GET agent (fail closed), runStatus via latest run."""
    api_key = (key if key is not None else load_cursor_api_key()).strip()
    if not api_key:
        return []
    timeout = _http_timeout()
    payload = http_get_json(f"/v1/agents?limit={_list_limit()}", key=api_key, timeout=timeout)
    if not isinstance(payload, dict):
        return []
    items = payload.get("items") or payload.get("agents") or []
    if not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    workers = min(8, max(1, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_annotate_agent, item, key=api_key, timeout=timeout)
            for item in items
            if isinstance(item, dict)
        ]
        for fut in as_completed(futures):
            try:
                row = fut.result()
            except Exception:
                continue
            if row:
                rows.append(row)
    return rows


def launch_extra_high(
    repo: str,
    prompt: str,
    *,
    root: Path | None = None,
    timeout: int = 180,
) -> str:
    """Create one Extra High grunt against ``repo`` via the PATH launcher.

    Does not pass ``--name`` (no twin remint of a reserved live name). Never
    Bot CloudAgent.
    """
    base = root if root is not None else _root()
    script = base / "scripts" / "launch-cloud-extra-high.sh"
    if not script.is_file():
        return "CLOUD_LAUNCH_ERR missing scripts/launch-cloud-extra-high.sh"
    env = os.environ.copy()
    env["GCS_CLOUD_REPO"] = repo
    env["CLOUD_REPO_URL"] = repo
    env["CURSOR_CLOUD_REPO"] = repo
    env["GCS_ROOT"] = str(base)
    try:
        proc = subprocess.run(
            ["bash", str(script), prompt],
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


def _launch_ok(blob: str) -> bool:
    return "CLOUD_LAUNCH_OK" in (blob or "")


def _with_capacity_lock(fn: Callable[[], str]) -> str:
    path = _state_dir() / "cloud-capacity.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def run_capacity_beat(
    *,
    prompt: str = "",
    repos: list[str] | None = None,
    rows: list[dict[str, Any]] | None = None,
    launch: Callable[[str, str], str] | None = None,
    min_running_override: int | None = None,
    root: Path | None = None,
    lock: bool = True,
) -> str:
    """Launch until each bound remote has >= floor runStatus RUNNING.

    Computes the deficit once per repo (this-beat CREATING launches are not
    re-counted as RUNNING). Does not remint list.sh --repo.
    """

    def _run() -> str:
        return _run_capacity_beat_unlocked(
            prompt=prompt,
            repos=repos,
            rows=rows,
            launch=launch,
            min_running_override=min_running_override,
            root=root,
        )

    if lock and rows is None:
        return _with_capacity_lock(_run)
    return _run()


def _run_capacity_beat_unlocked(
    *,
    prompt: str,
    repos: list[str] | None,
    rows: list[dict[str, Any]] | None,
    launch: Callable[[str, str], str] | None,
    min_running_override: int | None,
    root: Path | None,
) -> str:
    floor = min_running() if min_running_override is None else min_running_override
    bound = list(repos) if repos else bound_cloud_repos()
    if not bound:
        return "CLOUD_CAPACITY_ERR no bound repo (set GCS_CLOUD_REPO or GCS_CLOUD_REPOS)"
    if floor == 0:
        lines = [
            f"CLOUD_CAPACITY repo={display_repo(repo)} running=skipped floor=0 launched=0"
            for repo in bound
        ]
        lines.append("CLOUD_CAPACITY_OK")
        return "\n".join(lines)
    fleet = rows if rows is not None else fetch_fleet_rows()
    fill = choose_fill_prompt(prompt)
    launch_fn = launch
    if launch_fn is None:

        def launch_fn(repo: str, text: str, _root: Path | None = root) -> str:
            return launch_extra_high(repo, text, root=_root)

    lines: list[str] = []
    any_fail = False
    for repo in bound:
        running = count_running_for_repo(fleet, repo)
        need = max(0, floor - running)
        launched = 0
        failed = 0
        for _ in range(need):
            blob = launch_fn(repo, fill)
            if _launch_ok(str(blob or "")):
                launched += 1
            else:
                failed += 1
                any_fail = True
        extra = f" failed={failed}" if failed else ""
        lines.append(
            f"CLOUD_CAPACITY repo={display_repo(repo)} running={running} "
            f"floor={floor} launched={launched}{extra}"
        )
    if any_fail:
        lines.append("CLOUD_CAPACITY_ERR launch-fail")
    else:
        lines.append("CLOUD_CAPACITY_OK")
    return redact("\n".join(lines))
