"""LIV-85 evidence gate: ACK is a receipt; in-flight TASK hold.

Hub TASK_STATE_COMPLETED / send.sh ACK is a protocol receipt, not a mind
turn. STATUS ACK must not overwrite an in-flight Donald TASK in
mind/mail.txt until grok exits 0.

Unique remaining already on origin/main via GCS #27 MERGED (queue mail +
bot-bridge default off). Do not remint CLOSED unmerged GCS #81/#83.
Never Bot CloudAgent. Never Hermes vendor. Never palemon #165/#167.

Isolated ship-gate: tmp GCS_A2A_STATE, fake grok, no live Palemon bus.
Empty GitHub checks are not merge evidence.

Executable binding for tests/features/liv85_ack_is_receipt.feature.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import test_a2a_hub as hub_tests
import test_mind as tm

REPO = tm.REPO
FEATURE = REPO / "tests" / "features" / "liv85_ack_is_receipt.feature"
MIND_PY = tm.MIND_PY
HUB_PY = REPO / "scripts" / "a2a" / "hub.py"
SEND_SH = REPO / "scripts" / "a2a" / "send.sh"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
MIND_DOC = tm.MIND_DOC
AGENTS_DOC = tm.AGENTS_DOC
BOT_LIKE = REPO / "scripts" / "a2a" / "mind_bot_like.py"
GITMODULES = REPO / ".gitmodules"
PRIVATE_GAME = "atebites-hub/" + "palemon"
SCENARIO_BINDINGS = {
    "send.sh ACK is a receipt, not mind-turn done": (
        "test_send_sh_ack_is_receipt_not_mind_turn"
    ),
    "STATUS ACK must not overwrite an in-flight Donald TASK": (
        "test_status_ack_does_not_overwrite_in_flight_donald_task"
    ),
    "Do not remint CLOSED #81/#83 or Palemon leftovers": (
        "test_does_not_remint_closed_81_83_or_palemon_leftovers"
    ),
}

DONALD_TASK = (
    "TASK from Donald: staff the floor beat until eight Extra High are RUNNING"
)
STATUS_ACK = (
    "STATUS ACK: keep-alive token=tick-floor-ops-1. Quote token in STATUS."
)
ACP_PING = (
    "ACP_PING STATUS/CONTINUE seat=floor-ops token=tick-1. Keep-alive turn."
)


def _gherkin_scenarios(text: str) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Scenario:"):
            titles.append(stripped[len("Scenario:") :].strip())
    return titles


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def hub(tmp_path: Path):
    """Isolated hub. Does not bind the live Palemon GCS_A2A_STATE."""
    port = _free_port()
    state = tmp_path / "a2a-state"
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_A2A_HOST": "127.0.0.1",
        "GCS_A2A_PORT": str(port),
        "GCS_A2A_STATE": str(state),
        "GCS_A2A_HUB": f"http://127.0.0.1:{port}",
    }
    proc = subprocess.Popen(
        ["python3", str(HUB_PY)],
        cwd=str(REPO),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=0.3) as resp:
                if resp.status == 200:
                    yield {"url": url, "env": env, "state": state, "port": port}
                    proc.terminate()
                    proc.wait(timeout=3)
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.05)
    proc.kill()
    raise RuntimeError("isolated hub did not start")


def _write_blocking_fake_grok(
    tmp_path: Path,
    log: Path,
    *,
    gate: Path,
    snapshots: Path,
    started: Path,
) -> Path:
    """Fake grok that snapshots --prompt-file at start and again before exit 0."""
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        f"gate = Path({str(gate)!r})\n"
        f"snapshots = Path({str(snapshots)!r})\n"
        f"started = Path({str(started)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({\n"
        "    'argv': sys.argv[1:],\n"
        "    'cwd': os.getcwd(),\n"
        "})\n"
        "log.write_text(json.dumps(rows))\n"
        "mail = Path()\n"
        "argv = sys.argv[1:]\n"
        "if '--prompt-file' in argv:\n"
        "    mail = Path(argv[argv.index('--prompt-file') + 1])\n"
        "snaps = []\n"
        "snaps.append({'phase': 'start', 'text': mail.read_text() if mail.is_file() else ''})\n"
        "started.write_text('1\\n')\n"
        "deadline = time.time() + 8\n"
        "while time.time() < deadline:\n"
        "    if gate.is_file():\n"
        "        break\n"
        "    time.sleep(0.02)\n"
        "snaps.append({'phase': 'before_exit', 'text': mail.read_text() if mail.is_file() else ''})\n"
        "snapshots.write_text(json.dumps(snaps))\n"
        "sys.stdout.write(json.dumps({'ok': True, 'role': 'assistant'}))\n"
        "raise SystemExit(0)\n"
    )
    path = tmp_path / "fake-bin" / "grok"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_feature_binds_liv85_ack_is_receipt_law() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "receipt" in fold
    assert "not a mind turn" in fold or "not mind-turn" in fold
    assert "status ack" in fold
    assert "in-flight" in fold
    assert "donald" in fold
    assert "mind/mail.txt" in fold
    assert "grok exits 0" in fold
    assert "task_state_submitted" in fold
    assert "kind=receipt" in fold
    assert "#27" in text
    assert "#81" in text and "#83" in text
    assert "do not remint" in fold
    assert "bot cloudagent" in fold
    assert "hermes" in fold
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in fold
    assert ".venv/bin/pytest -q" in text
    assert "python3 scripts/secret_scan.py" in text
    assert PRIVATE_GAME not in text
    titles = _gherkin_scenarios(text)
    assert set(SCENARIO_BINDINGS) <= set(titles)
    for title, fn in SCENARIO_BINDINGS.items():
        assert title in titles
        assert callable(globals()[fn])


def test_status_ack_detector_does_not_treat_donald_task_as_ack() -> None:
    """Ack is an action. A Donald TASK is not a STATUS ACK."""
    mind = tm._load(MIND_PY, "gcs_liv85_status_ack_kind")
    assert mind.is_status_ack(STATUS_ACK)
    assert mind.is_status_ack(ACP_PING)
    assert mind.is_status_ack("ACK seat=floor-ops task=abc kind=receipt")
    assert not mind.is_status_ack(DONALD_TASK)
    assert not mind.is_status_ack("TASK_ASSIGN: launch extra high for playability")
    wrap = mind.wrap_mind_mail("beat-task-1", "ctx-1", DONALD_TASK)
    assert not mind.is_status_ack(wrap)


def test_send_sh_ack_is_receipt_not_mind_turn(hub: dict) -> None:
    proc = hub_tests._send(hub, "floor-ops", "ack is a receipt, not a mind turn")
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "A2A_SEND_OK" in proc.stdout
    assert "TASK_STATE_SUBMITTED" in proc.stdout
    assert "kind=receipt" in proc.stdout
    assert "TASK_STATE_COMPLETED" not in blob
    assert "MIND_TURN" not in blob
    assert "HANDOFF" not in blob
    state = Path(hub["state"])
    inbox = state / "floor-ops" / "inbox.jsonl"
    assert inbox.is_file()
    task_id = hub_tests._task_id_from_send(proc.stdout, inbox)
    task = hub_tests._get_task(hub, "floor-ops", task_id)
    assert (task.get("status") or {}).get("state") == "TASK_STATE_SUBMITTED"
    note = hub_tests._receipt_note(task).lower()
    assert "receipt" in note
    assert "not mind-turn" in note or "not mind turn" in note
    assert hub_tests._mind_offset(state, "floor-ops") == 0
    assert not (state / "floor-ops" / "mind" / "mail.txt").is_file()
    assert not (state / "floor-ops" / "mind" / "transcript.jsonl").is_file()
    send_src = SEND_SH.read_text(encoding="utf-8")
    assert "kind=receipt" in send_src or "kind={kind}" in send_src
    assert "MIND_TURN" not in send_src


def test_status_ack_does_not_overwrite_in_flight_donald_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hive example: ack is an action. Hold the Donald TASK until grok exits 0."""
    grok_log = tmp_path / "grok.argv.json"
    gate = tmp_path / "release-grok"
    snapshots = tmp_path / "mail-snapshots.json"
    started = tmp_path / "grok-started"
    grok = _write_blocking_fake_grok(
        tmp_path, grok_log, gate=gate, snapshots=snapshots, started=started
    )
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    mind, state = tm._prep_mind(
        tmp_path, monkeypatch, unique="liv85hold", grok=grok
    )
    monkeypatch.setenv("GCS_MIND_RUNNER", "grok")
    seat = "floor-ops"
    tm._append_inbox(state, seat, "beat-task-1", DONALD_TASK)
    tm._append_inbox(state, seat, "status-ack-1", STATUS_ACK)

    result_box: dict[str, object] = {}

    def _run() -> None:
        result_box["result"] = mind.process_once(seat)

    worker = threading.Thread(target=_run, name="mind-liv85-hold")
    worker.start()
    deadline = time.time() + 5
    while time.time() < deadline and not started.is_file():
        time.sleep(0.02)
    assert started.is_file(), "fake grok never started the TASK turn"

    mail = state / seat / "mind" / "mail.txt"
    argv0 = tm._argv_log(grok_log)[0]["argv"]
    prompt_file = Path(tm._flag_value(argv0, "--prompt-file"))
    assert prompt_file.resolve() == mail.resolve()
    held = mail.read_text(encoding="utf-8")
    assert DONALD_TASK in held
    assert "STATUS ACK" not in held

    clobber = mind.cursor_cli_runner(STATUS_ACK, seat=seat)
    assert int(clobber.get("returncode") or 1) != 0
    grok_clobber = mind.grok_cli_runner(STATUS_ACK, seat=seat)
    assert int(grok_clobber.get("returncode") or 1) != 0
    nested = mind.process_once(seat)
    assert nested.get("consumed") == 0
    assert nested.get("reason") == "in-flight"
    still = mail.read_text(encoding="utf-8")
    assert DONALD_TASK in still
    assert "STATUS ACK" not in still
    assert tm._offset(state, seat) == 0

    gate.write_text("go\n", encoding="utf-8")
    worker.join(timeout=8)
    assert not worker.is_alive()
    result = result_box.get("result")
    assert isinstance(result, dict)
    assert result.get("consumed") == 1
    assert result.get("reason") == "ok"
    snaps = json.loads(snapshots.read_text(encoding="utf-8"))
    assert snaps[0]["phase"] == "start"
    assert snaps[1]["phase"] == "before_exit"
    assert DONALD_TASK in snaps[0]["text"]
    assert DONALD_TASK in snaps[1]["text"]
    assert "STATUS ACK" not in snaps[0]["text"]
    assert "STATUS ACK" not in snaps[1]["text"]
    argv = tm._argv_log(grok_log)[0]["argv"]
    tm._assert_no_banned_flags(argv)
    assert "--prompt-file" in argv
    assert "--model" in argv
    assert tm._flag_value(argv, "--model") == tm.GROK_MIND_MODEL
    assert tm._flag_value(argv, "--reasoning-effort") == tm.GROK_MIND_REASONING_EFFORT


def test_does_not_remint_closed_81_83_or_palemon_leftovers() -> None:
    hub_src = HUB_PY.read_text(encoding="utf-8")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    bot_src = BOT_LIKE.read_text(encoding="utf-8")
    feature = FEATURE.read_text(encoding="utf-8")
    launch = LAUNCH.read_text(encoding="utf-8")
    # GCS #27 already on main: enqueue SUBMITTED. Do not restore #83 COMPLETE-on-send.
    assert '"state": TASK_STATE_SUBMITTED,' in hub_src
    assert "TASK_STATE_COMPLETED" in hub_src
    assert "receipt, not mind-turn done" in hub_src
    assert "format_mail_turn" not in hub_src
    # Do not remint CLOSED #81 sole-writer API / filename.
    assert "def write_seat_mail(" not in mind_src
    assert "mail.in-flight" not in mind_src
    assert "def write_seat_mail(" not in bot_src
    assert "mail.in-flight" not in bot_src
    # LIV-63 harvest still writes mail.txt before the runner.
    assert "prepare_mail_turn" in mind_src
    assert "NousResearch" not in mind_src
    gitmodules = GITMODULES.read_text(encoding="utf-8") if GITMODULES.is_file() else ""
    assert "hermes-agent" not in gitmodules
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast=false" in launch
    assert "never Bot CloudAgent" in launch or "Never Bot CloudAgent" in launch
    assert PRIVATE_GAME not in feature
    assert PRIVATE_GAME not in mind_src
    fold = feature.lower()
    assert "palemon #165" in fold or "never palemon #165" in fold
    assert "#81" in feature and "#83" in feature
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    assert "Empty GitHub checks are not merge evidence" in agents
    doc = MIND_DOC.read_text(encoding="utf-8")
    assert "liv85_ack_is_receipt.feature" in doc
    assert "receipt, not mind-turn done" in hub_src
    assert "in-flight" in doc.lower()
