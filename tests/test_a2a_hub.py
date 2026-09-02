"""A2A hub send/ack + registry seats."""
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

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "scripts" / "a2a" / "hub.py"
LIB = ROOT / "scripts" / "a2a" / "lib.py"
SEND = ROOT / "scripts" / "a2a" / "send.sh"
MIND_PY = ROOT / "scripts" / "directors" / "mind.py"
ARCH_DOC = ROOT / "docs" / "ARCHITECTURE.md"
A2A_DOC = ROOT / "docs" / "A2A.md"
MIND_DOC = ROOT / "docs" / "studio" / "MIND.md"
GROK_MIND_MODEL = "grok-4.6"
GROK_MIND_REASONING_EFFORT = "xhigh"


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


def test_registry_example_seats() -> None:
    seats = subprocess.check_output(["python3", str(LIB), "launch-seats"], cwd=str(ROOT), text=True)
    names = seats.strip().splitlines()
    for seat in (
        "floor",
        "ops",
        "cloud",
        "floor-ops",
        "studio-ops",
        "art",
        "content",
        "systems",
        "qa-a",
        "qa-b",
        "audio",
        "narrative",
    ):
        assert seat in names
    assert "orchestrator" not in names
    assert "donald" not in names


def test_hub_health_and_send_ack(hub: dict) -> None:
    with urllib.request.urlopen(f"{hub['url']}/health", timeout=2) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    assert body["ok"] is True
    assert body["service"] == "gcs-a2a-hub"

    proc = subprocess.run(
        ["bash", str(SEND), "floor", "ping from test"],
        cwd=str(ROOT),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "A2A_SEND_OK" in proc.stdout
    inbox = Path(hub["state"]) / "floor" / "inbox.jsonl"
    assert inbox.is_file()
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert record["parts"][0]["text"] == "ping from test"


def test_hub_send_routes_audio_narrative_title_aliases(hub: dict) -> None:
    """Remaining aliases: send.sh + hub fold titles onto first-class inboxes."""
    cases = (
        ("audio-director", "audio", "mix notes from audio-director"),
        ("narrative-lead", "narrative", "lore ping from narrative-lead"),
        ("audio", "audio", "first-class audio stays audio"),
        ("narrative", "narrative", "first-class narrative stays narrative"),
    )
    for title, seat, text in cases:
        proc = subprocess.run(
            ["bash", str(SEND), title, text],
            cwd=str(ROOT),
            env=hub["env"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "A2A_SEND_OK" in proc.stdout
        assert f"seat={seat}" in proc.stdout
        inbox = Path(hub["state"]) / seat / "inbox.jsonl"
        assert inbox.is_file(), title
        record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
        assert record["parts"][0]["text"] == text
        assert not (Path(hub["state"]) / title).exists() or title == seat


def test_hub_send_from_seat(hub: dict) -> None:
    proc = subprocess.run(
        ["bash", str(SEND), "--from", "ops", "floor", "ack via from"],
        cwd=str(ROOT),
        env=hub["env"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    inbox = Path(hub["state"]) / "floor" / "inbox.jsonl"
    record = json.loads(inbox.read_text(encoding="utf-8").splitlines()[-1])
    assert record["parts"][0]["text"] == "ack via from"
    data_parts = [p for p in record["parts"] if p.get("kind") == "data" or "data" in p]
    assert data_parts
    assert data_parts[0]["data"]["from"] == "ops"
    assert record.get("from") == "ops"


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


def _status_text(task: dict) -> str:
    parts = ((task.get("status") or {}).get("message") or {}).get("parts") or []
    bits: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("text"):
            bits.append(str(part["text"]))
    return " ".join(bits)


def _ack_text(task: dict) -> str:
    return _status_text(task)


def _mind_offset(state: Path, seat: str) -> int:
    path = state / seat / "mind" / "offset"
    if not path.is_file():
        return 0
    return int(path.read_text(encoding="utf-8").strip() or "0")


def _load_mind(name: str):
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


def _seed_linear_grok_home(mind, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy-path grok harvests still need Living Sky Linear in GROK_HOME."""
    orig_home = mind.grok_home_dir

    def _grok_home_with_linear(seat: str) -> Path:
        d = orig_home(seat)
        cfg = d / "config.toml"
        if not cfg.is_file():
            cfg.write_text(
                "[mcp_servers.linear]\n"
                f'url = "{mind.LINEAR_MCP_URL}"\n'
                'headers = { Authorization = "Bearer ${LINEAR_API_KEY}" }\n',
                encoding="utf-8",
            )
        return d

    monkeypatch.setattr(mind, "grok_home_dir", _grok_home_with_linear)


def test_hub_complete_send_ack_is_receipt_not_mind_turn(hub: dict) -> None:
    """Hub COMPLETE / send.sh ACK is a receipt. That is not mail consumed."""
    proc = _send(hub, "floor", "queued until runner exit 0")
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "A2A_SEND_OK" in proc.stdout
    assert "TASK_STATE_COMPLETED" in proc.stdout
    assert "kind=receipt" in proc.stdout
    assert "TASK_STATE_SUBMITTED" not in proc.stdout
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
    assert "ACK" in _ack_text(task)
    assert (task.get("metadata") or {}).get("kind") == "ack"
    note = _receipt_note(task).lower()
    assert "receipt" in note
    assert "not mind-turn" in note or "not mind turn" in note
    assert "exit 0" in note
    on_disk = json.loads((state / "floor" / "tasks.json").read_text(encoding="utf-8"))
    assert on_disk[task_id]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") == 0
    assert not (state / "floor" / "mind" / "transcript.jsonl").is_file()

    send_src = SEND.read_text(encoding="utf-8")
    hub_src = HUB.read_text(encoding="utf-8")
    assert "kind=receipt" in send_src
    assert "not mind-turn done" in hub_src
    assert "not mind-turn done" in send_src
    docs = (
        ARCH_DOC.read_text(encoding="utf-8")
        + "\n"
        + A2A_DOC.read_text(encoding="utf-8")
        + "\n"
        + MIND_DOC.read_text(encoding="utf-8")
    ).lower()
    assert "receipt" in docs
    assert "not mind-turn" in docs or "not mind turn" in docs


def test_mind_turn_only_after_grok_runner_exit_0_hub_stays_receipt(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MIND_TURN / offset only after grok actually ran the line and exited 0."""
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

    mind = _load_mind("gcs_mind_hub_ack_receipt")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    _seed_linear_grok_home(mind, monkeypatch)

    result = mind.process_once("floor")
    assert result.get("consumed") == 1, result
    assert result.get("reason") == "ok"
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") > 0
    argv = json.loads(grok_log.read_text(encoding="utf-8"))[0]["argv"]
    assert "--prompt-file" in argv
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == GROK_MIND_MODEL
    effort = "--reasoning-effort" if "--reasoning-effort" in argv else "--effort"
    assert argv[argv.index(effort) + 1] in {
        GROK_MIND_REASONING_EFFORT,
        "extra-high",
        "max",
    }
    mail = Path(argv[argv.index("--prompt-file") + 1])
    assert mail.name == "mail.txt"
    assert "mind must harvest this" in mail.read_text(encoding="utf-8")


def test_grok_nonzero_leaves_mail_unconsumed_hub_still_receipt(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _send(hub, "floor", "keep queued on grok fail")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    state = Path(hub["state"])
    inbox = state / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok-fail",
        "#!/usr/bin/env python3\nimport sys\nsys.stderr.write('boom\\n')\nraise SystemExit(1)\n",
    )
    mind = _load_mind("gcs_mind_hub_ack_fail")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.setenv("GCS_MIND_RUNNER", "grok")
    _seed_linear_grok_home(mind, monkeypatch)
    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "runner-fail"
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") == 0
    assert not (state / "floor" / "mind" / "transcript.jsonl").is_file()
    mail = state / "floor" / "mind" / "mail.txt"
    assert mail.is_file()
    assert "keep queued on grok fail" in mail.read_text(encoding="utf-8")


def test_hub_completed_after_harvest_is_receipt_not_mind_turn_status(
    hub: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """After runner exit 0, harvest COMPLETED status is ACK/receipt, not MIND_TURN."""
    proc = _send(hub, "floor", "harvest then receipt complete")
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
        "sys.stdout.write(json.dumps({'ok': True}))\n"
        "raise SystemExit(0)\n",
    )

    mind = _load_mind("gcs_mind_complete_receipt")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    _seed_linear_grok_home(mind, monkeypatch)

    result = mind.process_once("floor")
    captured = capsys.readouterr()
    assert result.get("consumed") == 1, result
    assert result.get("reason") == "ok"
    task = _get_task(hub, "floor", task_id)
    assert (task.get("status") or {}).get("state") == "TASK_STATE_COMPLETED"
    status = _status_text(task)
    assert "MIND_TURN" not in status
    assert "ACK" in status or "receipt" in status.lower() or "kind=receipt" in status
    assert "MIND_TURN" in captured.out
    assert _mind_offset(state, "floor") > 0
    argv = json.loads(grok_log.read_text(encoding="utf-8"))[0]["argv"]
    assert "--prompt-file" in argv
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "grok-4.6"
    assert argv[argv.index("--reasoning-effort") + 1] == "xhigh"


def test_none_runner_after_hub_ack_is_not_mail_consumed(
    hub: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runner that did not run (None) must not consume mail after the receipt."""

    def silent(_prompt: str, **_kwargs: object):
        return None

    proc = _send(hub, "floor", "must not fake success")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    state = Path(hub["state"])
    inbox = state / "floor" / "inbox.jsonl"
    task_id = _task_id_from_send(proc.stdout, inbox)
    mind = _load_mind("gcs_mind_hub_ack_none")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", ROOT)
    monkeypatch.setattr(mind, "DEFAULT_RUNNER", silent)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    _seed_linear_grok_home(mind, monkeypatch)
    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "runner-fail"
    assert _get_task(hub, "floor", task_id)["status"]["state"] == "TASK_STATE_COMPLETED"
    assert _mind_offset(state, "floor") == 0
    assert not (state / "floor" / "mind" / "transcript.jsonl").is_file()
