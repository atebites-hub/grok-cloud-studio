#!/usr/bin/env python3
"""Directors-spawn law: playability floor via launch-cloud-extra-high.sh.

If playability work is in progress and the RUNNING Extra High count for the
target repo is below GCS_CLOUD_MIN_RUNNING (default 8), cloud mind MUST
invoke scripts/launch-cloud-extra-high.sh.

Never --name gcs-liv41-mind-must-launch (that name is already RUNNING).
Never Bot CloudAgent. Model grok-4.6 xhigh fast=false.
"""
from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

DEFAULT_MIN_RUNNING = 8
IN_FLIGHT_RUN = frozenset({"RUNNING", "CREATING"})
RESERVED_SPAWN_NAME = "gcs-liv41-mind-must-launch"
DEFAULT_SPAWN_NAME = "gcs-liv41-playability"
LAUNCH_REL = "scripts/launch-cloud-extra-high.sh"
_PLAYABILITY_RE = re.compile(r"\bplayability\b", re.IGNORECASE)
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


def min_running(raw: str | None = None) -> int:
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if not text:
        return DEFAULT_MIN_RUNNING
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_MIN_RUNNING
    return value if value > 0 else DEFAULT_MIN_RUNNING


def work_is_playability(text: str) -> bool:
    return bool(_PLAYABILITY_RE.search(text or ""))


def normalize_run_status(status: str | None) -> str:
    text = (status or "").strip()
    if not text:
        return "none"
    upper = text.upper()
    if upper == "NONE":
        return "none"
    return upper


def is_in_flight_run(status: str | None) -> bool:
    return normalize_run_status(status) in IN_FLIGHT_RUN


def _norm_repo(url: str) -> str:
    text = (url or "").strip().lower()
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text.split(":", 1)[1]
    if text.endswith(".git"):
        text = text[:-4]
    return text.rstrip("/")


def agent_repo_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    repo = item.get("repo")
    if isinstance(repo, str) and repo.strip():
        urls.append(repo.strip())
    repos = item.get("repos") or item.get("repositories") or []
    if isinstance(repos, list):
        for entry in repos:
            if isinstance(entry, str) and entry.strip():
                urls.append(entry.strip())
            elif isinstance(entry, dict):
                found = str(entry.get("url") or entry.get("repository") or "").strip()
                if found:
                    urls.append(found)
    source = item.get("source")
    if isinstance(source, dict):
        found = str(source.get("repository") or source.get("url") or "").strip()
        if found:
            urls.append(found)
    return urls


def row_matches_repo(item: dict[str, Any], repo: str | None) -> bool:
    if not (repo or "").strip():
        return True
    wanted = _norm_repo(repo or "")
    urls = agent_repo_urls(item)
    if not urls:
        return True
    return any(_norm_repo(url) == wanted for url in urls)


def count_running_for_repo(rows: list[dict[str, Any]], repo: str | None = None) -> int:
    n = 0
    for row in rows:
        if not row_matches_repo(row, repo):
            continue
        if is_in_flight_run(str(row.get("runStatus") or row.get("run_status") or "")):
            n += 1
    return n


def must_launch(
    *,
    work: str,
    running_count: int,
    cap: int | None = None,
) -> bool:
    if not work_is_playability(work):
        return False
    limit = min_running() if cap is None else cap
    if limit <= 0:
        return False
    return running_count < limit


def is_bot_cloudagent(name: str, bot_agent_id: str = "") -> bool:
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


def _taken_names(agents: Iterable[dict[str, Any]], repo: str | None) -> set[str]:
    taken = {RESERVED_SPAWN_NAME.lower()}
    for row in agents:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        if row_matches_repo(row, repo) and is_in_flight_run(
            str(row.get("runStatus") or row.get("run_status") or "")
        ):
            taken.add(name.lower())
    return taken


def choose_spawn_name(
    requested: str | None,
    taken_names: Iterable[str],
    *,
    bot_agent_id: str = "",
) -> str:
    taken = {n.strip().lower() for n in taken_names if str(n).strip()}
    taken.add(RESERVED_SPAWN_NAME.lower())
    candidate = (requested or "").strip()
    if (
        candidate
        and candidate.lower() not in taken
        and not is_bot_cloudagent(candidate, bot_agent_id=bot_agent_id)
    ):
        return candidate
    base = DEFAULT_SPAWN_NAME
    if base.lower() not in taken and not is_bot_cloudagent(base, bot_agent_id=bot_agent_id):
        return base
    i = 2
    while True:
        nxt = f"{base}-{i}"
        if nxt.lower() not in taken and not is_bot_cloudagent(nxt, bot_agent_id=bot_agent_id):
            return nxt
        i += 1


def launch_argv(*, root: Path, prompt: str, name: str) -> list[str]:
    script = Path(root) / LAUNCH_REL
    return ["bash", str(script), "--name", name, prompt]


def _default_launch(argv: list[str], *, cwd: Path) -> str:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError:
        return f"CLOUD_LAUNCH_ERR missing binary: {argv[0]}"
    except subprocess.TimeoutExpired:
        return "CLOUD_LAUNCH_ERR timeout"
    except OSError as exc:
        return f"CLOUD_LAUNCH_ERR {exc}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0 and "CLOUD_LAUNCH_ERR" not in out:
        return f"CLOUD_LAUNCH_ERR rc={proc.returncode} {out}"
    return out or f"rc={proc.returncode}"


def cloud_mind_spawn_if_required(
    *,
    work: str,
    agents: list[dict[str, Any]],
    repo: str,
    root: Path,
    launch: Callable[[list[str]], str] | None = None,
    requested_name: str | None = None,
    cap: int | None = None,
    bot_agent_id: str = "",
) -> dict[str, Any]:
    """Cloud mind MUST launch Extra High when playability is below the floor.

    Does not reuse --name gcs-liv41-mind-must-launch. Never Bot CloudAgent.
    """
    running = count_running_for_repo(agents, repo)
    if not must_launch(work=work, running_count=running, cap=cap):
        reason = "not-playability" if not work_is_playability(work) else "at-floor"
        return {
            "launched": False,
            "reason": reason,
            "running": running,
            "name": None,
            "argv": [],
            "output": "",
        }
    taken = _taken_names(agents, repo)
    name = choose_spawn_name(
        requested_name,
        taken,
        bot_agent_id=bot_agent_id,
    )
    if is_bot_cloudagent(name, bot_agent_id=bot_agent_id) or name.lower() == RESERVED_SPAWN_NAME:
        return {
            "launched": False,
            "reason": "refused-name",
            "running": running,
            "name": name,
            "argv": [],
            "output": "",
        }
    prompt = (
        f"{work.strip()}\n\n"
        "Mechanic Extra High. Open a PR. Model grok-4.6 xhigh fast=false. "
        "Linear=Living Sky LIV."
    )
    argv = launch_argv(root=Path(root), prompt=prompt, name=name)
    runner = launch or (lambda cmd: _default_launch(cmd, cwd=Path(root)))
    output = runner(argv)
    return {
        "launched": True,
        "reason": "below-floor",
        "running": running,
        "name": name,
        "argv": argv,
        "output": output,
    }
