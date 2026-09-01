"""Capacity beat: mind MUST launch until runStatus RUNNING >= 8 per bound repo.

LIV-41 (Living Sky, not Black Swan). Count only latest-run RUNNING. Never
count agent ACTIVE leftovers. CREATING is not RUNNING.

Does not remint list --repo (#50), count-running (#55), print-runStatus list
rows (#44), refuse --name (#59), webhook (#57), follow-up refuse (#49), or
shepherd leftover skip (#32). Never Bot CloudAgent. Never vendor Hermes.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parents[1]
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
CAP_PY = REPO / "scripts" / "directors" / "cloud_capacity.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
PLUGIN_DIR = REPO / "plugins" / "studio-mind"
LIST_SH = REPO / "scripts" / "cloud" / "list.sh"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
COUNT_RUNNING = REPO / "scripts" / "cloud" / "count-running.sh"
RUNNING_COUNT = REPO / "scripts" / "cloud" / "running-count.sh"
CLOUD_CAPACITY_PY = REPO / "scripts" / "cloud" / "capacity.py"

STUDIO_REPO = "https://github.com/atebites-hub/grok-cloud-studio"
GAME_REPO = "https://github.com/" + "atebites-hub/" + "palemon"
PRIVATE_GAME = "atebites-hub/" + "palemon"
RESERVED_SPAWN_NAME = "gcs-liv41-mind-must-launch"


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


def _row(
    *,
    agent_id: str,
    repo: str,
    run_status: str,
    agent_status: str = "ACTIVE",
    unbound: bool = False,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "id": agent_id,
        "agentStatus": agent_status,
        "status": agent_status,
        "runStatus": run_status,
    }
    if not unbound:
        rec["repo"] = repo
        rec["repos"] = [repo]
    return rec


def test_source_contract_capacity_is_mind_plugin_not_list_remint() -> None:
    assert CAP_PY.is_file(), "scripts/directors/cloud_capacity.py is the mind slice"
    cap = CAP_PY.read_text(encoding="utf-8")
    mind = MIND_PY.read_text(encoding="utf-8")
    doc = MIND_DOC.read_text(encoding="utf-8")
    plugin_readme = (PLUGIN_DIR / "README.md").read_text(encoding="utf-8")
    list_sh = LIST_SH.read_text(encoding="utf-8")
    for blob in (cap, mind, doc, plugin_readme):
        assert PRIVATE_GAME not in blob
        assert "/home/box" not in blob
        assert "black swan" not in blob.lower() or "never" in blob.lower()
    assert "cloud_capacity" in mind
    assert "cloud_capacity" in plugin_readme
    assert "runStatus" in cap
    assert "RUNNING" in cap
    assert "launch-cloud-extra-high.sh" in cap
    assert "GCS_CLOUD_MIN_RUNNING" in cap
    assert "Bot CloudAgent" in cap
    assert "fast=false" in cap
    assert RESERVED_SPAWN_NAME not in cap or "never" in cap.lower()
    assert "CAPACITY_BEAT" in doc or "capacity beat" in doc.lower()
    assert "runStatus" in doc
    assert "GCS_CLOUD_MIN_RUNNING" in mind or "GCS_CLOUD_MIN_RUNNING" in doc
    assert LIST_SH.is_file()
    assert LAUNCH.is_file()
    assert "--repo" not in list_sh
    assert not COUNT_RUNNING.is_file(), "do not remint count-running #55"
    assert not RUNNING_COUNT.is_file(), "do not remint running-count #44"
    assert not CLOUD_CAPACITY_PY.is_file(), "do not remint scripts/cloud/capacity.py #44"
    assert "Hermes" not in cap
    assert "hermes" not in mind.lower()


def test_leftover_active_finished_is_not_running() -> None:
    cap = _load(CAP_PY, "gcs_cap_leftover")
    rows = [
        _row(agent_id="bc-dead", repo=STUDIO_REPO, run_status="FINISHED"),
        _row(agent_id="bc-dead2", repo=STUDIO_REPO, run_status="FINISHED", agent_status="ACTIVE"),
        _row(agent_id="bc-create", repo=STUDIO_REPO, run_status="CREATING"),
        _row(agent_id="bc-live", repo=STUDIO_REPO, run_status="RUNNING"),
    ]
    assert cap.count_running_for_repo(rows, STUDIO_REPO) == 1
    assert cap.is_running_status("RUNNING") is True
    assert cap.is_running_status("running") is True
    assert cap.is_running_status("FINISHED") is False
    assert cap.is_running_status("CREATING") is False
    assert cap.is_running_status("ACTIVE") is False
    assert cap.is_running_status("") is False


def test_bound_repos_counted_separately() -> None:
    cap = _load(CAP_PY, "gcs_cap_two_repos")
    rows = [
        _row(agent_id="bc-s1", repo=STUDIO_REPO, run_status="RUNNING"),
        _row(agent_id="bc-s2", repo=STUDIO_REPO, run_status="FINISHED"),
        _row(agent_id="bc-g1", repo=GAME_REPO, run_status="RUNNING"),
        _row(agent_id="bc-g2", repo=GAME_REPO, run_status="RUNNING"),
        _row(agent_id="bc-other", repo="https://github.com/example/other", run_status="RUNNING"),
        _row(agent_id="bc-unbound", repo="", run_status="RUNNING", unbound=True),
    ]
    assert cap.count_running_for_repo(rows, STUDIO_REPO) == 1
    assert cap.count_running_for_repo(rows, GAME_REPO) == 2
    assert cap.count_running_for_repo(rows, "atebites-hub/grok-cloud-studio") == 1
    git_form = GAME_REPO + ".git"
    assert cap.count_running_for_repo(rows, git_form) == 2
    assert cap.count_running_for_repo(rows, "https://github.com/example/other") == 1


def test_unbound_running_is_fail_closed() -> None:
    cap = _load(CAP_PY, "gcs_cap_unbound")
    rows = [_row(agent_id="bc-x", repo="", run_status="RUNNING", unbound=True)]
    assert cap.count_running_for_repo(rows, STUDIO_REPO) == 0


def test_org_name_https_and_ssh_normalize() -> None:
    cap = _load(CAP_PY, "gcs_cap_norm")
    https = cap.normalize_repo(STUDIO_REPO)
    org = cap.normalize_repo("atebites-hub/grok-cloud-studio")
    git = cap.normalize_repo(STUDIO_REPO + ".git")
    ssh = cap.normalize_repo("git@github.com:atebites-hub/grok-cloud-studio.git")
    assert https == org == git == ssh == "atebites-hub/grok-cloud-studio"


def test_bound_cloud_repos_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _load(CAP_PY, "gcs_cap_bound_env")
    env = {
        "GCS_CLOUD_REPOS": f"{STUDIO_REPO},{GAME_REPO}",
        "GCS_CLOUD_REPO": STUDIO_REPO,
        "GCS_GAME_REPO": GAME_REPO,
    }
    repos = cap.bound_cloud_repos(env)
    keys = [cap.normalize_repo(r) for r in repos]
    assert keys == [
        "atebites-hub/grok-cloud-studio",
        cap.normalize_repo(GAME_REPO),
    ]


def test_is_capacity_beat_clock_not_generic_keepalive() -> None:
    cap = _load(CAP_PY, "gcs_cap_beat_detect")
    assert cap.is_capacity_beat(
        "ACP_PING STATUS/CONTINUE seat=floor token=tick-1. Keep-alive turn."
    )
    assert cap.is_capacity_beat("CAPACITY_BEAT fill the floor")
    assert cap.is_capacity_beat("capacity beat: launch until RUNNING >= 8")
    assert cap.is_capacity_beat("CLOUD_CAPACITY fill")
    wrapped = (
        "A2A_TASK_ID=tick-floor-1\nMESSAGE:\n"
        "ACP_PING STATUS/CONTINUE seat=floor token=tick-floor-1. Keep-alive turn."
    )
    assert cap.is_capacity_beat(wrapped)
    assert not cap.is_capacity_beat(
        "Keep-alive received. Scanning A2A inboxes, fleet ledgers"
    )
    assert not cap.is_capacity_beat("please list tickets")
    assert not cap.is_capacity_beat("A2A_REPLY from ops: thanks")


def test_capacity_beat_launches_deficit_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cap = _load(CAP_PY, "gcs_cap_deficit")
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    launched: list[tuple[str, str]] = []

    def fake_launch(repo: str, prompt: str) -> str:
        launched.append((repo, prompt))
        return "CLOUD_LAUNCH_OK id=bc-new\n"

    rows = [
        _row(agent_id="bc-dead", repo=STUDIO_REPO, run_status="FINISHED"),
        _row(agent_id="bc-live", repo=STUDIO_REPO, run_status="RUNNING"),
        _row(agent_id="bc-live2", repo=STUDIO_REPO, run_status="RUNNING"),
        _row(agent_id="bc-create", repo=STUDIO_REPO, run_status="CREATING"),
        _row(agent_id="bc-g-dead", repo=GAME_REPO, run_status="FINISHED"),
    ]
    out = cap.run_capacity_beat(
        prompt="ACP_PING STATUS/CONTINUE token=t1",
        repos=[STUDIO_REPO, GAME_REPO],
        rows=rows,
        launch=fake_launch,
        min_running_override=8,
        lock=False,
    )
    studio_launches = [
        r for r, _p in launched if cap.normalize_repo(r) == cap.normalize_repo(STUDIO_REPO)
    ]
    game_launches = [
        r for r, _p in launched if cap.normalize_repo(r) == cap.normalize_repo(GAME_REPO)
    ]
    assert len(studio_launches) == 6, out
    assert len(game_launches) == 8, out
    fill = launched[0][1]
    assert "Bot CloudAgent" in fill
    assert "ACP_PING" not in fill
    assert RESERVED_SPAWN_NAME not in fill
    assert "donald" not in fill.lower()
    assert "orchestrator" not in fill.lower()
    assert "CLOUD_CAPACITY_OK" in out
    assert "running=2" in out
    assert "launched=6" in out
    assert "running=0" in out
    assert "launched=8" in out


def test_at_floor_does_not_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _load(CAP_PY, "gcs_cap_at_floor")
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    launched: list[str] = []

    def fake_launch(repo: str, prompt: str) -> str:
        launched.append(repo)
        return "CLOUD_LAUNCH_OK\n"

    rows = [_row(agent_id=f"bc-{i}", repo=STUDIO_REPO, run_status="RUNNING") for i in range(8)]
    out = cap.run_capacity_beat(
        prompt="CAPACITY_BEAT",
        repos=[STUDIO_REPO],
        rows=rows,
        launch=fake_launch,
        min_running_override=8,
        lock=False,
    )
    assert launched == []
    assert "launched=0" in out
    assert "CLOUD_CAPACITY_OK" in out


def test_launch_extra_high_invokes_real_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cap = _load(CAP_PY, "gcs_cap_real_script")
    log = tmp_path / "launch.argv"
    root = tmp_path / "tree"
    script = root / "scripts" / "launch-cloud-extra-high.sh"
    _write_exec(
        script,
        "#!/bin/sh\n"
        f'echo "repo=$GCS_CLOUD_REPO prompt=$1 argv=$*" >> "{log}"\n'
        "echo CLOUD_LAUNCH_OK id=bc-fill\n",
    )
    monkeypatch.setenv("GCS_ROOT", str(root))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "state"))
    blob = cap.launch_extra_high(STUDIO_REPO, "CAPACITY_BEAT fill. Open a PR.", root=root)
    assert "CLOUD_LAUNCH_OK" in blob
    argv = log.read_text(encoding="utf-8")
    assert STUDIO_REPO in argv
    assert "CAPACITY_BEAT fill" in argv
    assert RESERVED_SPAWN_NAME not in argv
    assert " --name donald" not in argv
    assert "orchestrator" not in argv


@dataclass
class MockFleetAPI:
    agents: list[dict[str, Any]] = field(default_factory=list)
    run_by_id: dict[str, str] = field(default_factory=dict)
    agent_repos: dict[str, str] = field(default_factory=dict)
    unbound: set[str] = field(default_factory=set)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "MockFleetAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _send(self, code: int, payload: dict[str, Any] | None = None) -> None:
                blob = b"" if payload is None else json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                if blob:
                    self.wfile.write(blob)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents"]:
                    items = []
                    for agent in api.agents:
                        items.append(
                            {
                                "id": agent["id"],
                                "status": agent.get("status") or "ACTIVE",
                                "name": agent.get("name") or "",
                                "url": f"https://cursor.com/agents/{agent['id']}",
                                "latestRunId": agent.get("latestRunId") or "run-1",
                            }
                        )
                    self._send(200, {"items": items})
                    return
                if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
                    agent_id = parts[2]
                    body: dict[str, Any] = {
                        "id": agent_id,
                        "status": "ACTIVE",
                        "latestRunId": "run-1",
                    }
                    if agent_id not in api.unbound:
                        repo = api.agent_repos.get(agent_id) or STUDIO_REPO
                        body["repos"] = [{"url": repo, "startingRef": "main"}]
                    self._send(200, body)
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    agent_id = parts[2]
                    status = api.run_by_id.get(agent_id, "FINISHED")
                    payload: dict[str, Any] = {
                        "id": parts[4],
                        "agentId": agent_id,
                        "status": status,
                    }
                    if agent_id not in api.unbound and agent_id in api.agent_repos:
                        payload["git"] = {
                            "branches": [{"repoUrl": api.agent_repos[agent_id]}]
                        }
                    self._send(200, payload)
                    return
                self._send(404, {"error": "not_found"})

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def test_http_fetch_counts_only_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cap = _load(CAP_PY, "gcs_cap_http")
    agents = [
        {"id": "bc-dead", "status": "ACTIVE", "latestRunId": "run-dead"},
        {"id": "bc-live", "status": "ACTIVE", "latestRunId": "run-live"},
        {"id": "bc-create", "status": "ACTIVE", "latestRunId": "run-c"},
        {"id": "bc-unbound", "status": "ACTIVE", "latestRunId": "run-u"},
        {"id": "bc-game", "status": "ACTIVE", "latestRunId": "run-g"},
    ]
    with MockFleetAPI(
        agents=agents,
        run_by_id={
            "bc-dead": "FINISHED",
            "bc-live": "RUNNING",
            "bc-create": "CREATING",
            "bc-unbound": "RUNNING",
            "bc-game": "RUNNING",
        },
        agent_repos={
            "bc-dead": STUDIO_REPO,
            "bc-live": STUDIO_REPO,
            "bc-create": STUDIO_REPO,
            "bc-game": GAME_REPO,
        },
        unbound={"bc-unbound"},
    ) as api:
        monkeypatch.setenv("CURSOR_API_BASE", api.base)
        monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
        monkeypatch.setenv("CLOUD_CURL_MAX_TIME", "5")
        rows = cap.fetch_fleet_rows()
    ids = {r["id"] for r in rows}
    assert "bc-unbound" not in ids
    assert cap.count_running_for_repo(rows, STUDIO_REPO) == 1
    assert cap.count_running_for_repo(rows, GAME_REPO) == 1
    leftover = next(r for r in rows if r["id"] == "bc-dead")
    assert leftover["agentStatus"] == "ACTIVE"
    assert leftover["runStatus"] == "FINISHED"
    assert cap.is_running_status(leftover["runStatus"]) is False


def test_http_capacity_beat_launches_until_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cap = _load(CAP_PY, "gcs_cap_http_launch")
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    launched: list[str] = []

    def fake_launch(repo: str, prompt: str) -> str:
        launched.append(repo)
        return "CLOUD_LAUNCH_OK id=bc-fill\n"

    agents = [
        {"id": "bc-dead", "latestRunId": "r1"},
        {"id": "bc-live", "latestRunId": "r2"},
    ]
    with MockFleetAPI(
        agents=agents,
        run_by_id={"bc-dead": "FINISHED", "bc-live": "RUNNING"},
        agent_repos={"bc-dead": STUDIO_REPO, "bc-live": STUDIO_REPO},
    ) as api:
        monkeypatch.setenv("CURSOR_API_BASE", api.base)
        monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
        monkeypatch.setenv("CLOUD_CURL_MAX_TIME", "5")
        out = cap.run_capacity_beat(
            prompt="CAPACITY_BEAT",
            repos=[STUDIO_REPO],
            launch=fake_launch,
            min_running_override=8,
            lock=False,
        )
    assert len(launched) == 7, out
    assert "CLOUD_CAPACITY_OK" in out
    assert "running=1" in out
    assert "launched=7" in out


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
    grok: Path | None = None,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_mind_cap_{unique}")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_CLOUD_REPO", STUDIO_REPO)
    monkeypatch.setenv("GCS_GAME_REPO", GAME_REPO)
    if grok is not None:
        monkeypatch.setenv("GROK_BIN", str(grok))
    return mind, state


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> None:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "host-clock",
        "parts": [{"kind": "text", "text": text}],
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _write_fake_grok(tmp_path: Path, log: Path) -> Path:
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "mail = ''\n"
        "if '--prompt-file' in sys.argv:\n"
        "    mail = Path(sys.argv[sys.argv.index('--prompt-file')+1]).read_text()\n"
        "rows.append({'argv': sys.argv[1:], 'mail': mail})\n"
        "log.write_text(json.dumps(rows))\n"
        "sys.stdout.write(json.dumps({'ok': True}))\n"
        "raise SystemExit(0)\n"
    )
    return _write_exec(tmp_path / "fake-bin" / "grok", script)


def test_process_once_capacity_beat_must_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="beat", grok=grok)
    launched: list[tuple[str, str]] = []
    real = mind.run_capacity_beat

    def fake_beat(**kwargs: Any) -> str:
        def launch(repo: str, prompt: str) -> str:
            launched.append((repo, prompt))
            return "CLOUD_LAUNCH_OK\n"

        return real(
            prompt=str(kwargs.get("prompt") or ""),
            repos=[STUDIO_REPO],
            rows=[
                _row(agent_id="bc-dead", repo=STUDIO_REPO, run_status="FINISHED"),
            ],
            launch=launch,
            min_running_override=8,
            lock=False,
        )

    monkeypatch.setattr(mind, "run_capacity_beat", fake_beat)
    _append_inbox(
        state,
        "floor",
        "tick-floor-1",
        "ACP_PING STATUS/CONTINUE seat=floor token=tick-floor-1. "
        "Keep-alive turn: do work, do not idle.",
    )
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert launched, "capacity beat must call launch-cloud-extra-high.sh"
    assert len(launched) == 8
    grok_rows = json.loads(grok_log.read_text(encoding="utf-8"))
    mail = grok_rows[0]["mail"]
    assert "CLOUD_CAPACITY" in mail
    assert "ACP_PING" in mail
    assert "launched=8" in mail
    assert "A2A_TASK_ID=tick-floor-1" in mail


def test_process_once_non_capacity_mail_does_not_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="nobeat", grok=grok)
    called: list[str] = []

    def boom(**_kwargs: Any) -> str:
        called.append("yes")
        return "CLOUD_CAPACITY_ERR should-not-run"

    monkeypatch.setattr(mind, "run_capacity_beat", boom)
    _append_inbox(state, "floor", "task-work", "please list tickets")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert called == []
    mail = json.loads(grok_log.read_text(encoding="utf-8"))[0]["mail"]
    assert "please list tickets" in mail
    assert "CLOUD_CAPACITY" not in mail


def test_capacity_beat_same_task_does_not_double_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="stamp", grok=grok)
    n = {"count": 0}

    def fake_beat(**_kwargs: Any) -> str:
        n["count"] += 1
        return "CLOUD_CAPACITY repo=studio running=0 floor=8 launched=8\nCLOUD_CAPACITY_OK"

    monkeypatch.setattr(mind, "run_capacity_beat", fake_beat)
    _append_inbox(
        state, "floor", "tick-dup", "ACP_PING STATUS/CONTINUE token=tick-dup"
    )
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    assert n["count"] == 1
    (state / "floor" / "mind" / "offset").write_text("0\n", encoding="utf-8")
    (state / "floor" / "mind" / "session.minted").write_text("1\n", encoding="utf-8")
    second = mind.process_once("floor")
    assert second["consumed"] == 1
    assert n["count"] == 1, "same taskId must not launch again"


def test_cloud_capacity_plugin_invokes_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "launch.argv"
    _write_exec(
        tmp_path / "scripts" / "launch-cloud-extra-high.sh",
        "#!/bin/sh\n"
        f'echo "repo=$GCS_CLOUD_REPO prompt=$1" >> "{log}"\n'
        "echo CLOUD_LAUNCH_OK id=bc-cap\n",
    )
    mind = _load(MIND_PY, "gcs_mind_cap_plugin")
    monkeypatch.setattr(mind, "ROOT", tmp_path)
    monkeypatch.setattr(mind, "STATE_DIR", tmp_path / "a2a-state")
    monkeypatch.setenv("GCS_ROOT", str(tmp_path))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    monkeypatch.setenv("GCS_CLOUD_MIN_RUNNING", "2")
    cap_mod = sys.modules["cloud_capacity"]
    monkeypatch.setattr(cap_mod, "fetch_fleet_rows", lambda **_k: [])
    out = mind.call_plugin(
        "cloud_capacity",
        {"prompt": "Implement playability. Open a PR.", "repos": [STUDIO_REPO]},
    )
    assert "CLOUD_CAPACITY" in out
    assert "CLOUD_CAPACITY_OK" in out
    assert "launched=2" in out
    argv = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert STUDIO_REPO in argv
    assert "Implement playability" in argv
    assert "cloud_capacity" in mind.PLUGINS
    assert RESERVED_SPAWN_NAME not in argv


def test_studio_mind_lists_cloud_capacity() -> None:
    server = PLUGIN_DIR / "server.py"
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    env = {**os.environ, "GCS_ROOT": str(REPO), "GCS_MCP_NDJSON": "1"}
    proc = subprocess.run(
        ["python3", str(server)],
        cwd=str(REPO),
        input=msg,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    reply = json.loads(proc.stdout.splitlines()[0])
    names = {t["name"] for t in reply["result"]["tools"]}
    assert "cloud_capacity" in names
    assert "cloud_launch" in names
    assert names == {"ticket", "a2a_send", "cloud_launch", "cloud_capacity"}
