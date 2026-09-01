"""LIV-85: mail is a turn. Hub COMPLETE is a receipt, not mind-turn done.

Living Sky Linear (LIV, not Black Swan). Does not remint Hermes harvest
#26/#28 (format_mail_turn / envelope / defang / 16k / heartbeat) or
mind-skip-dup-mail #54. Never Bot CloudAgent. grok-4.6 xhigh, fast=false.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "scripts" / "a2a" / "hub.py"
SEND = ROOT / "scripts" / "a2a" / "send.sh"
MIND_PY = ROOT / "scripts" / "directors" / "mind.py"
MIND_DOC = ROOT / "docs" / "studio" / "MIND.md"
A2A_DOC = ROOT / "docs" / "A2A.md"
ARCH_DOC = ROOT / "docs" / "ARCHITECTURE.md"
AGENTS_DOC = ROOT / "AGENTS.md"
GROK_MIND_MODEL = "grok-4.6"
GROK_MIND_REASONING_EFFORT = "xhigh"
CURSOR_MIND_MODEL = "cursor-grok-4.6-xhigh"
BLACK_SWAN = "blackswan" + ".money"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def hub(tmp_path: Path):
    port = _free_port()
    state = tmp_path / "a2a-state"
    env = {
        **os.environ,
        "GCS_ROOT": str(ROOT),
        "GCS_A2A_HOST": "127.0.0.1",
        "GCS_A2A_PORT": str(port),
        "GCS_A2A_STATE": str(state),
        "GCS_A2A_HUB": f"http://127.0.0.1:{port}",
    }
    proc = subprocess.Popen(
        ["python3", str(HUB)],
        cwd=str(ROOT),
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
    raise RuntimeError("hub did not start")


def _send(hub: dict, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SEND), *args],
        cwd=str(ROOT),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )


def _task_id_from_send(stdout: str, inbox: Path) -> str:
    for line in stdout.splitlines():
        if line.startswith("A2A_SEND_OK") and "task=" in line:
            for part in line.split():
                if part.startswith("task="):
                    tid = part.split("=", 1)[1].strip()
                    if tid:
                        return tid
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    return str(record["taskId"])


def _get_task(hub: dict, seat: str, task_id: str) -> dict:
    with urllib.request.urlopen(
        f"{hub['url']}/a2a/{seat}/tasks/{task_id}", timeout=2
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _receipt_note(task: dict) -> str:
    for art in task.get("artifacts") or []:
        if art.get("name") != "receipt":
            continue
        for part in art.get("parts") or []:
            if not isinstance(part, dict):
                continue
            data = part.get("data") or {}
            if isinstance(data, dict) and data.get("note"):
                return str(data["note"])
    return ""


def _mind_offset(state: Path, seat: str) -> int:
    path = state / seat / "mind" / "offset"
    if not path.is_file():
        return 0
    return int(path.read_text(encoding="utf-8").strip() or "0")


def _load_mind(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MIND_PY)
    assert spec is not None and spec.loader is not None
    mind = importlib.util.module_from_spec(spec)
    sys.modules[name] = mind
    spec.loader.exec_module(mind)
    return mind


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_liv85_law_does_not_remint_hermes_or_skip_dup_or_bot() -> None:
    """Mailbox-is-a-turn without reminting #26/#28/#54 or launching Bot CloudAgent."""
    src = MIND_PY.read_text(encoding="utf-8")
    docs = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (MIND_DOC, A2A_DOC, ARCH_DOC, AGENTS_DOC)
    )
    blob = src + "\n" + docs
    low = blob.lower()
    assert "format_mail_turn" not in src
    assert "MAIL_MAX_CHARS" not in src
    assert "filter_inbound_mail" not in src
    assert "last-fleet-done" not in src
    assert "duplicate-fleet-done" not in src
    assert "Bot CloudAgent" not in src
    assert "ACP_INJECT_HANDOFF" not in src
    assert "HANDOFF" not in src
    assert BLACK_SWAN not in low
    assert "black swan" not in low
    assert "grok-4.6" in src
    assert "xhigh" in src
    assert "fast=false" in docs
    assert "receipt" in docs.lower()
    assert "not mind-turn" in docs.lower() or "not mind turn" in docs.lower()
    assert "liv-85" in low or "living sky" in low
    assert GROK_MIND_MODEL in src
    assert GROK_MIND_REASONING_EFFORT in src
    assert CURSOR_MIND_MODEL in src


def test_hub_complete_ack_is_receipt_not_mind_turn(hub: dict) -> None:
    """Hub COMPLETE / A2A ACK is a receipt. That is not mail consumed."""
    proc = _send(hub, "floor", "queued until runner exit 0")
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "A2A_SEND_OK" in proc.stdout
    assert "TASK_STATE_COMPLETED" in proc.stdout
    assert "TASK_STATE_SUBMITTED" not in proc.stdout
    assert "kind=receipt" in proc.stdout
    assert "HANDOFF" not in blob
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "MIND_TURN" not in blob
    assert "Bot CloudAgent" not in blob

    state = Path(hub["state"])
    inbox = state / "floor" / "inbox.jsonl"
    assert inbox.is_file()
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert record["parts"][0]["text"] == "queued until runner exit 0"
    task_id = _task_id_from_send(proc.stdout, inbox)
    task = _get_task(hub, "floor", task_id)
    assert (task.get("status") or {}).get("state") == "TASK_STATE_COMPLETED"
    assert (task.get("metadata") or {}).get("kind") == "ack"
    note = _receipt_note(task).lower()
    assert "receipt" in note
    assert "not mind-turn" in note or "not mind turn" in note
    assert "mind/offset" in note or "mind seats" in note
    assert "exit 0" in note
    on_disk = json.loads((state / "floor" / "tasks.json").read_text(encoding="utf-8"))
    assert on_disk[task_id]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") == 0
    assert not (state / "floor" / "mind" / "transcript.jsonl").is_file()


def test_mail_consumed_only_after_grok_runner_exit_0(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mind consumes mail only after grok actually ran the line and exited 0."""
    proc = _send(hub, "floor", "mind must harvest this")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "kind=receipt" in proc.stdout
    state = Path(hub["state"])
    inbox = state / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") == 0

    grok_log = tmp_path / "grok.argv.json"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(grok_log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:]})\n"
        "log.write_text(json.dumps(rows))\n"
        "sys.stdout.write(json.dumps({'ok': True}))\n"
        "raise SystemExit(0)\n",
    )

    mind = _load_mind("gcs_liv85_hub_ack_complete")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)

    result = mind.process_once("floor")
    assert result.get("consumed") == 1, result
    assert result.get("reason") == "ok"
    assert result.get("task_id") == task_id
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") > 0
    argv_rows = json.loads(grok_log.read_text(encoding="utf-8"))
    assert argv_rows, "grok CLI must actually run the harvested mail line"
    argv = argv_rows[0]["argv"]
    assert "--prompt-file" in argv
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == GROK_MIND_MODEL
    assert argv[argv.index("--reasoning-effort") + 1] == GROK_MIND_REASONING_EFFORT
    mail = (state / "floor" / "mind" / "mail.txt").read_text(encoding="utf-8")
    assert "mind must harvest this" in mail


def test_grok_nonzero_leaves_mail_unconsumed_hub_still_receipt(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _send(hub, "floor", "keep queued on grok fail")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "kind=receipt" in proc.stdout
    state = Path(hub["state"])
    inbox = state / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)

    grok = _write_exec(
        tmp_path / "fake-bin" / "grok-fail",
        "#!/usr/bin/env python3\nimport sys\nsys.stderr.write('boom\\n')\nraise SystemExit(1)\n",
    )

    mind = _load_mind("gcs_liv85_hub_ack_fail")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.setenv("GCS_MIND_RUNNER", "grok")

    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "runner-fail"
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") == 0
    assert not (state / "floor" / "mind" / "transcript.jsonl").is_file()


def test_cursor_nonzero_leaves_mail_unconsumed_hub_still_receipt(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _send(hub, "floor", "keep queued on cursor fail")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    state = Path(hub["state"])
    inbox = state / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)

    cursor = _write_exec(
        tmp_path / "fake-bin" / "agent",
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if 'create-chat' in sys.argv[1:]:\n"
        "    sys.stdout.write('11111111-2222-3333-4444-555555555555\\n')\n"
        "    raise SystemExit(0)\n"
        "sys.stderr.write('cursor boom\\n')\n"
        "raise SystemExit(1)\n",
    )

    mind = _load_mind("gcs_liv85_hub_ack_curfail")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_CURSOR_BIN", str(cursor))
    monkeypatch.setenv("GCS_MIND_RUNNER", "cursor")
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")

    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "runner-fail"
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") == 0


def test_none_runner_after_hub_ack_is_not_harvest_fake_success(
    hub: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runner that did not run (None) must not consume mail after the receipt."""

    def silent(_prompt: str, **_kwargs: object):
        return None

    proc = _send(hub, "floor", "must not fake success")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "kind=receipt" in proc.stdout
    state = Path(hub["state"])
    inbox = state / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)

    mind = _load_mind("gcs_liv85_hub_ack_none")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setattr(mind, "DEFAULT_RUNNER", silent)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))

    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "runner-fail"
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") == 0
    assert not (state / "floor" / "mind" / "transcript.jsonl").is_file()


def test_empty_harvest_does_not_invoke_cli_or_consume_leftover_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok-empty",
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(grok_log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:]})\n"
        "log.write_text(json.dumps(rows))\n"
        "raise SystemExit(0)\n",
    )
    mind = _load_mind("gcs_liv85_empty_harvest")
    empty_state = tmp_path / "empty-state"
    empty_state.mkdir()
    monkeypatch.setattr(mind, "STATE_DIR", empty_state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(empty_state))
    monkeypatch.setenv("GROK_BIN", str(grok))
    leftover = "task-leftover-receipt"
    tasks_path = empty_state / "floor" / "tasks.json"
    tasks_path.parent.mkdir(parents=True)
    tasks_path.write_text(
        json.dumps(
            {
                leftover: {
                    "id": leftover,
                    "status": {
                        "state": "TASK_STATE_COMPLETED",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                    },
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "empty"
    assert not grok_log.is_file()
    on_disk = json.loads(tasks_path.read_text(encoding="utf-8"))
    assert on_disk[leftover]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(empty_state, "floor") == 0
    assert not (empty_state / "floor" / "mind" / "session").is_file()


def test_cursor_exit_0_consumes_mail_hub_stays_receipt(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _send(hub, "floor", "cursor mail line")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    state = Path(hub["state"])
    inbox = state / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)
    grok_log = tmp_path / "grok.argv.json"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(grok_log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:]})\n"
        "log.write_text(json.dumps(rows))\n"
        "raise SystemExit(0)\n",
    )
    cursor_log = tmp_path / "cursor.argv.json"
    cursor = _write_exec(
        tmp_path / "fake-bin" / "agent",
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(cursor_log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:]})\n"
        "log.write_text(json.dumps(rows))\n"
        "if 'create-chat' in sys.argv[1:]:\n"
        "    sys.stdout.write('11111111-2222-3333-4444-555555555555\\n')\n"
        "    raise SystemExit(0)\n"
        "sys.stdout.write(json.dumps({'ok': True}))\n"
        "raise SystemExit(0)\n",
    )
    mind = _load_mind("gcs_liv85_hub_ack_cur0")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.setenv("GCS_CURSOR_BIN", str(cursor))
    monkeypatch.setenv("GCS_MIND_RUNNER", "cursor")
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")

    result = mind.process_once("floor")
    assert result.get("consumed") == 1, result
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") > 0
    assert not grok_log.is_file()
    cursor_rows = json.loads(cursor_log.read_text(encoding="utf-8"))
    assert cursor_rows[0]["argv"] == ["create-chat"]
    turn = cursor_rows[1]["argv"]
    assert "--model" in turn
    assert turn[turn.index("--model") + 1] == CURSOR_MIND_MODEL
    assert turn[-1] == "cursor mail line"
