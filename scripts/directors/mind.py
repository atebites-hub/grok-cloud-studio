#!/usr/bin/env python3
"""Grok Build seat mind: mailbox + pin + stay-up.

Python is not the agent. It harvests one inbox line, pins a grok session UUID,
runs one `grok --prompt-file` turn, persists json stdout, and stays up. Grok is
the agent for that turn (its own tool loop, `--max-turns 40`). Default
`GCS_MIND_RUNNER=auto` persists `$GCS_A2A_STATE/<seat>/mind/runner` (`grok` or
`cursor`). Each mail line uses that file. On quota / HTTP 402, flip the file
and retry that same mail line once on the other runner (`MIND_SWITCH`). Forced
`GCS_MIND_RUNNER=grok|cursor` does not flip. Never remint the grok UUID because
harvest was empty or because the runner switched. Hub TASK_STATE_COMPLETED is
a receipt, not mind-turn done. Offset advances only on runner exit 0. A runner
that did not run (None) is runner-fail, not harvest-fake success.

Do not parse grok stdout for function calls. Do not run a second tool-calling
loop. Do not use grok agent serve or leftover ACP inject on opted-in mind
seats. Pin one UUID in mind/session; first turn `--session-id`, later turns
`--resume` that id. Never remint because harvest was empty. Never bare `-p` on
grok (`--single` requires a prompt; `--prompt-file` is the prompt). Cursor
CLI uses `-p` (print mode) and a positional prompt. `--agent-profile`,
`--trust`, and `--plugin-dir` are grok agent flags, not grok headless.

Stdlib only. Donald/orchestrator (skipSeats) are not mind seats.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import canonical_seat, skip_seats  # noqa: E402

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))

_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(CURSOR_API_KEY|GCS_WEBHOOK_SECRET|Authorization|Bearer|"
    r"server-key|ACP_SECRET|api[_-]?key)\s*[=:]\s*\S+"
)
_SESSION_IN_USE_RE = re.compile(
    r"session.*already in use|already in use.*session",
    re.IGNORECASE | re.DOTALL,
)
_USAGE_EXHAUSTED_RE = re.compile(
    r"usage balance exhausted|\bHTTP\s*402\b",
    re.IGNORECASE,
)
MIND_FAIL_STDERR_CHARS = 240
CURSOR_MIND_MODEL = "cursor-grok-4.6-xhigh"
GROK_MIND_MODEL = "grok-4.6"
GROK_MIND_REASONING_EFFORT = "xhigh"  # extra-high


@dataclass(frozen=True)
class Plugin:
    """Fallback helper callable plus JSON schema. Not a second agent loop.

    Grok sees tools via builtins, seat GROK_HOME taskboard MCP, and
    `grok plugin install --trust` of `plugins/studio-mind` into that GROK_HOME.
    This dict stays for `call_plugin` / tests / the studio-mind MCP server.
    """

    schema: dict[str, Any]
    call: Callable[[dict[str, Any]], str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(text: str) -> str:
    """Strip credential assignments from plugin/runner output. Never print secrets."""
    if not text:
        return text
    return _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)


def stderr_log_snippet(text: str) -> str:
    """Redact, collapse whitespace, and cap MIND_FAIL stderr at 240 chars."""
    blob = redact(text or "")
    blob = " ".join(blob.split())
    return blob[:MIND_FAIL_STDERR_CHARS]


def mind_dir(seat: str) -> Path:
    d = STATE_DIR / seat / "mind"
    d.mkdir(parents=True, exist_ok=True)
    return d


def grok_home_dir(seat: str) -> Path:
    d = STATE_DIR / seat / "grok-home"
    d.mkdir(parents=True, exist_ok=True)
    return d


def taskboard_db() -> Path:
    raw = os.environ.get("GCS_TASKBOARD_DB") or os.environ.get("TASKBOARD_DB")
    if raw:
        return Path(raw)
    return STATE_DIR / "taskboard" / "taskboard.db"


def _write_pid(seat: str) -> None:
    try:
        (mind_dir(seat) / "pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    except OSError:
        pass


def _read_offset(seat: str) -> int:
    path = mind_dir(seat) / "offset"
    if not path.is_file():
        return 0
    try:
        return max(0, int(path.read_text(encoding="utf-8").strip() or "0"))
    except ValueError:
        return 0


def _write_offset(seat: str, offset: int) -> None:
    path = mind_dir(seat) / "offset"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(offset) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_transcript(seat: str, row: dict[str, Any]) -> None:
    path = mind_dir(seat) / "transcript.jsonl"
    rec = dict(row)
    rec.setdefault("ts", _now())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def session_file(seat: str) -> Path:
    return mind_dir(seat) / "session"


def session_minted_file(seat: str) -> Path:
    return mind_dir(seat) / "session.minted"


def load_or_create_session(seat: str) -> str:
    """UUID once. Never rewrite because a later harvest was empty."""
    path = session_file(seat)
    if path.is_file():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            return raw
    sid = str(uuid.uuid4())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(sid + "\n", encoding="utf-8")
    tmp.replace(path)
    return sid


def session_is_minted(seat: str) -> bool:
    return session_minted_file(seat).is_file()


def mark_session_minted(seat: str) -> None:
    session_minted_file(seat).write_text("1\n", encoding="utf-8")


def cursor_session_file(seat: str) -> Path:
    return mind_dir(seat) / "cursor-session"


def load_cursor_session(seat: str) -> str:
    """Pinned Cursor chat id. Separate from grok mind/session. Never -1."""
    path = cursor_session_file(seat)
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not raw or raw == "-1":
        return ""
    return raw


def save_cursor_session(seat: str, chat_id: str) -> None:
    path = cursor_session_file(seat)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(chat_id + "\n", encoding="utf-8")
    tmp.replace(path)


def soul_profile(seat: str) -> str | None:
    """Candidate `--agent` path: seat SOUL.md, else docs souls, else omit."""
    local = STATE_DIR / seat / "SOUL.md"
    if local.is_file():
        return str(local)
    src = ROOT / "docs" / "studio" / "directors" / "souls" / seat / "SOUL.md"
    if src.is_file():
        return str(src)
    return None


def yaml_agent_file(path: str | Path | None) -> str | None:
    """`--agent PATH` only if PATH is a file starting with YAML ---."""
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_file():
        return None
    try:
        with candidate.open("r", encoding="utf-8") as fh:
            start = fh.read(3)
    except OSError:
        return None
    if start == "---":
        return str(candidate)
    return None


def _session_already_in_use(stderr: str, stdout: str = "") -> bool:
    blob = f"{stderr}\n{stdout}"
    return bool(_SESSION_IN_USE_RE.search(blob))


def _extract_text(parts: Any) -> str:
    bits: list[str] = []
    if not isinstance(parts, list):
        return ""
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("kind") == "text" or "text" in p:
            t = p.get("text")
            if t is not None:
                bits.append(str(t))
        elif p.get("kind") == "data" and "data" in p:
            try:
                bits.append(json.dumps(p["data"], ensure_ascii=False))
            except (TypeError, ValueError):
                bits.append(str(p["data"]))
    return "\n".join(bits).strip()


def _read_new_records(seat: str) -> list[tuple[int, dict[str, Any]]]:
    path = STATE_DIR / seat / "inbox.jsonl"
    if not path.is_file():
        return []
    size = path.stat().st_size
    offset = _read_offset(seat)
    if offset > size:
        offset = size
    records: list[tuple[int, dict[str, Any]]] = []
    with path.open("rb") as fh:
        fh.seek(offset)
        while True:
            line_start = fh.tell()
            raw = fh.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                break
            end = fh.tell()
            try:
                rec = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(
                    f"MIND_WARN seat={seat} bad_json offset={line_start}: {e}",
                    file=sys.stderr,
                )
                records.append((end, {"__corrupt__": True}))
                continue
            if not isinstance(rec, dict):
                records.append((end, {"__corrupt__": True}))
                continue
            records.append((end, rec))
    return records


def _argv_list(arguments: dict[str, Any]) -> list[str]:
    raw = arguments.get("argv")
    if raw is None:
        raw = arguments.get("args")
    if raw is None:
        raw = arguments.get("command")
    if isinstance(raw, str):
        return raw.split()
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def _run_cmd(cmd: list[str], *, timeout: int = 60) -> str:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "GCS_ROOT": str(ROOT), "GCS_A2A_STATE": str(STATE_DIR)},
        )
    except FileNotFoundError:
        return f"PLUGIN_ERR missing binary: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"PLUGIN_ERR timeout after {timeout}s: {cmd[0]}"
    except OSError as e:
        return f"PLUGIN_ERR {e}"
    out = (proc.stdout or "") + (proc.stderr or "")
    blob = redact(out.strip() or f"rc={proc.returncode}")
    if proc.returncode != 0 and "PLUGIN_ERR" not in blob:
        return f"PLUGIN_ERR rc={proc.returncode} {blob}"
    return blob


def plugin_ticket(arguments: dict[str, Any]) -> str:
    """Exec TASKBOARD_BIN --db GCS_TASKBOARD_DB ticket <argv>."""
    candidates: list[Path] = []
    env_bin = (os.environ.get("TASKBOARD_BIN") or "").strip()
    if env_bin:
        candidates.append(Path(env_bin))
    candidates.append(ROOT / "bin" / "taskboard")
    binary: Path | None = None
    for cand in candidates:
        try:
            if cand.is_file() and os.access(cand, os.X_OK):
                binary = cand
                break
        except OSError:
            continue
    if binary is None:
        return "PLUGIN_ERR ticket: missing TASKBOARD_BIN (set TASKBOARD_BIN)"
    argv = _argv_list(arguments)
    db = str(taskboard_db())
    cmd = [str(binary), "--db", db, "ticket", *argv]
    return _run_cmd(cmd, timeout=60)


def plugin_a2a_send(arguments: dict[str, Any]) -> str:
    """scripts/a2a/send.sh [--from SEAT] <seat> <text>."""
    script = ROOT / "scripts" / "a2a" / "send.sh"
    if not script.is_file():
        return "PLUGIN_ERR a2a_send: missing scripts/a2a/send.sh"
    seat = str(arguments.get("seat") or "").strip()
    text = str(arguments.get("text") or "")
    if not seat or not text:
        return "PLUGIN_ERR a2a_send: seat and text are required"
    cmd = ["bash", str(script)]
    from_seat = str(arguments.get("from") or arguments.get("from_seat") or "").strip()
    if from_seat:
        cmd.extend(["--from", from_seat])
    cmd.extend([seat, text])
    return _run_cmd(cmd, timeout=60)


def plugin_cloud_launch(arguments: dict[str, Any]) -> str:
    """scripts/launch-cloud-extra-high.sh [--name NAME] PROMPT."""
    script = ROOT / "scripts" / "launch-cloud-extra-high.sh"
    if not script.is_file():
        return "PLUGIN_ERR cloud_launch: missing scripts/launch-cloud-extra-high.sh"
    prompt = str(arguments.get("prompt") or "").strip()
    if not prompt:
        return "PLUGIN_ERR cloud_launch: prompt is required"
    cmd = ["bash", str(script)]
    name = str(arguments.get("name") or "").strip()
    if name:
        cmd.extend(["--name", name])
    cmd.append(prompt)
    return _run_cmd(cmd, timeout=180)


TICKET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "argv": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Arguments after `ticket`, e.g. [\"list\"] or "
                "[\"move\", \"T-1\", \"--status\", \"done\"]."
            ),
        }
    },
    "required": ["argv"],
    "additionalProperties": False,
}

A2A_SEND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "seat": {"type": "string", "description": "Destination seat id"},
        "text": {"type": "string", "description": "Message body"},
        "from": {"type": "string", "description": "Optional caller seat for --from"},
    },
    "required": ["seat", "text"],
    "additionalProperties": False,
}

CLOUD_LAUNCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "name": {"type": "string", "description": "Short Extra High agent name"},
    },
    "required": ["prompt"],
    "additionalProperties": False,
}

PLUGINS: dict[str, Plugin] = {
    "ticket": Plugin(schema=TICKET_SCHEMA, call=plugin_ticket),
    "a2a_send": Plugin(schema=A2A_SEND_SCHEMA, call=plugin_a2a_send),
    "cloud_launch": Plugin(schema=CLOUD_LAUNCH_SCHEMA, call=plugin_cloud_launch),
}


def call_plugin(name: str, arguments: dict[str, Any] | None = None) -> str:
    plugin = PLUGINS.get(name)
    if plugin is None:
        return f"PLUGIN_ERR unknown plugin: {name}"
    try:
        return redact(plugin.call(arguments or {}))
    except Exception as e:
        return f"PLUGIN_ERR {name}: {e}"


def grok_cli_argv(
    *,
    session_id: str,
    minted: bool,
    mail_path: Path,
    agent: str | Path | None = None,
    grok: str | None = None,
) -> list[str]:
    """Pinned-session grok CLI. First turn mints; later turns resume that UUID.

    Headless law (never bare `-p`; never grok-agent `--agent-profile` /
    `--trust` / `--plugin-dir`). Pin grok-4.6 extra-high (`xhigh` is the CLI
    extra-high alias). Cursor fallback stays `cursor-grok-4.6-xhigh`.

        grok --resume $UUID --prompt-file $mail --verbatim --output-format json \\
            --always-approve --permission-mode bypassPermissions --max-turns 40 \\
            --model grok-4.6 --reasoning-effort xhigh

    First turn uses `--session-id $UUID` instead of `--resume`.
    """
    binary = grok or os.environ.get("GROK_BIN") or "grok"
    argv: list[str] = [binary]
    if minted:
        argv.extend(["--resume", session_id])
    else:
        argv.extend(["--session-id", session_id])
    argv.extend(
        [
            "--prompt-file",
            str(mail_path),
            "--verbatim",
            "--output-format",
            "json",
            "--always-approve",
            "--permission-mode",
            "bypassPermissions",
            "--max-turns",
            "40",
            "--model",
            GROK_MIND_MODEL,
            "--reasoning-effort",
            GROK_MIND_REASONING_EFFORT,
        ]
    )
    agent_path = yaml_agent_file(agent)
    if agent_path:
        argv.extend(["--agent", agent_path])
    return argv


def grok_cli_runner(prompt: str, *, seat: str = "", **_kwargs: Any) -> dict[str, Any]:
    grok_home = grok_home_dir(seat)
    session_id = load_or_create_session(seat)
    minted = session_is_minted(seat)
    mail_path = mind_dir(seat) / "mail.txt"
    mail_path.write_text(prompt, encoding="utf-8")
    agent = yaml_agent_file(soul_profile(seat))
    env = os.environ.copy()
    env["GCS_ROOT"] = str(ROOT)
    env["GCS_A2A_STATE"] = str(STATE_DIR)
    env["GROK_HOME"] = str(grok_home)
    env["GROK_MEMORY"] = "1"
    timeout_raw = os.environ.get("GCS_MIND_TURN_TIMEOUT", "").strip()
    timeout: float | None = float(timeout_raw) if timeout_raw else None

    def _run(minted_flag: bool) -> dict[str, Any]:
        argv = grok_cli_argv(
            session_id=session_id,
            minted=minted_flag,
            mail_path=mail_path,
            agent=agent,
        )
        try:
            proc = subprocess.run(
                argv,
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return {
                "text": "PLUGIN_ERR grok CLI missing on PATH",
                "returncode": 127,
                "stderr": "",
            }
        except subprocess.TimeoutExpired:
            return {"text": "PLUGIN_ERR grok CLI timeout", "returncode": 124, "stderr": ""}
        except OSError as e:
            return {"text": f"PLUGIN_ERR grok CLI: {e}", "returncode": 1, "stderr": ""}
        text = redact((proc.stdout or "").strip())
        stderr = redact((proc.stderr or "").strip())
        return {"text": text, "returncode": int(proc.returncode), "stderr": stderr}

    result = _run(minted)
    if (
        not minted
        and int(result.get("returncode") or 0) != 0
        and _session_already_in_use(
            str(result.get("stderr") or ""), str(result.get("text") or "")
        )
    ):
        mark_session_minted(seat)
        result = _run(True)
    if isinstance(result, dict):
        result.setdefault("backend", "grok")
    return result


def grok_usage_exhausted(text: str, stderr: str = "") -> bool:
    """True when a runner refused the turn for HTTP 402 / usage balance exhausted."""
    blob = f"{text}\n{stderr}"
    return bool(_USAGE_EXHAUSTED_RE.search(blob))


MIND_RUNNERS = ("grok", "cursor")


def mind_runner_file(seat: str) -> Path:
    return mind_dir(seat) / "runner"


def load_persisted_mind_runner(seat: str) -> str | None:
    path = mind_runner_file(seat)
    if not path.is_file():
        return None
    try:
        val = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    if val in MIND_RUNNERS:
        return val
    return None


def persist_mind_runner(seat: str, runner: str) -> None:
    if runner not in MIND_RUNNERS:
        return
    path = mind_runner_file(seat)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(runner + "\n", encoding="utf-8")
    tmp.replace(path)


def mind_runner_mode() -> str:
    raw = (os.environ.get("GCS_MIND_RUNNER") or "auto").strip().lower()
    if raw in ("grok", "cursor", "auto"):
        return raw
    return "auto"


def other_mind_runner(runner: str) -> str:
    return "cursor" if runner == "grok" else "grok"


def cursor_agent_env_path() -> Path:
    raw = (os.environ.get("CURSOR_AGENT_ENV") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".config" / "cursor" / "agent.env"


def load_cursor_api_key() -> str:
    """CURSOR_API_KEY from the environment or agent.env. Never print the value."""
    existing = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if existing:
        return existing
    path = cursor_agent_env_path()
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


def cursor_cli_binary() -> str:
    """Prefer GCS_CURSOR_BIN, then cursor-grok on PATH, else agent."""
    explicit = (os.environ.get("GCS_CURSOR_BIN") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("cursor-grok")
    if found:
        return found
    return "agent"


def cursor_create_chat_argv(*, binary: str | None = None) -> list[str]:
    return [binary or cursor_cli_binary(), "create-chat"]


def cursor_cli_argv(
    *,
    chat_id: str,
    prompt: str,
    binary: str | None = None,
) -> list[str]:
    """Pinned-chat Cursor CLI. Mint with create-chat; every turn resumes that id.

    Headless law (model pin is cursor-grok-4.6-xhigh only; never grok UUID;
    never latest-in-cwd; Cursor has no --session-id / --prompt-file):

        agent --resume $CHAT_ID -p --force --output-format json --trust \\
            --approve-mcps --model cursor-grok-4.6-xhigh $PROMPT
    """
    exe = binary or cursor_cli_binary()
    return [
        exe,
        "--resume",
        chat_id,
        "-p",
        "--force",
        "--output-format",
        "json",
        "--trust",
        "--approve-mcps",
        "--model",
        CURSOR_MIND_MODEL,
        prompt,
    ]


def parse_create_chat_id(stdout: str, stderr: str = "") -> str:
    """Best-effort parse of `agent create-chat` stdout. Reject empty and -1."""
    for blob in ((stdout or "").strip(), (stderr or "").strip()):
        if not blob:
            continue
        data: Any = None
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for key in ("id", "chatId", "chat_id", "sessionId", "session_id"):
                val = str(data.get(key) or "").strip()
                if val and val != "-1":
                    return val
        elif isinstance(data, str) and data.strip() and data.strip() != "-1":
            return data.strip()
        line = blob.splitlines()[0].strip()
        parts = line.split()
        token = parts[-1].strip().strip("'\"") if parts else ""
        if token and token not in {"-1", "create-chat"}:
            return token
    return ""


def _cursor_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GCS_ROOT"] = str(ROOT)
    env["GCS_A2A_STATE"] = str(STATE_DIR)
    env.pop("GROK_HOME", None)
    env.pop("GROK_MEMORY", None)
    key = load_cursor_api_key()
    if key:
        env["CURSOR_API_KEY"] = key
    return env


def _run_cursor_cmd(
    argv: list[str],
    *,
    env: dict[str, str],
    timeout: float | None,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {
            "text": "PLUGIN_ERR cursor CLI missing on PATH",
            "returncode": 127,
            "stderr": "",
            "backend": "cursor",
        }
    except subprocess.TimeoutExpired:
        return {
            "text": "PLUGIN_ERR cursor CLI timeout",
            "returncode": 124,
            "stderr": "",
            "backend": "cursor",
        }
    except OSError as e:
        return {
            "text": f"PLUGIN_ERR cursor CLI: {e}",
            "returncode": 1,
            "stderr": "",
            "backend": "cursor",
        }
    return {
        "text": redact((proc.stdout or "").strip()),
        "returncode": int(proc.returncode),
        "stderr": redact((proc.stderr or "").strip()),
        "backend": "cursor",
    }


def cursor_cli_runner(prompt: str, *, seat: str = "", **_kwargs: Any) -> dict[str, Any]:
    """One Cursor CLI turn. Pins mind/cursor-session, not grok mind/session."""
    mind_dir(seat)
    mail_path = mind_dir(seat) / "mail.txt"
    mail_path.write_text(prompt, encoding="utf-8")
    env = _cursor_subprocess_env()
    if not (env.get("CURSOR_API_KEY") or "").strip():
        return {
            "text": (
                "PLUGIN_ERR CURSOR_API_KEY missing "
                "(export it or source ~/.config/cursor/agent.env)"
            ),
            "returncode": 1,
            "stderr": "",
            "backend": "cursor",
        }
    timeout_raw = os.environ.get("GCS_MIND_TURN_TIMEOUT", "").strip()
    timeout: float | None = float(timeout_raw) if timeout_raw else None
    create_timeout = timeout if timeout is not None else 60.0
    binary = cursor_cli_binary()
    chat_id = load_cursor_session(seat)
    if not chat_id:
        minted = _run_cursor_cmd(
            cursor_create_chat_argv(binary=binary),
            env=env,
            timeout=create_timeout,
        )
        if int(minted.get("returncode") or 0) != 0:
            return minted
        chat_id = parse_create_chat_id(
            str(minted.get("text") or ""), str(minted.get("stderr") or "")
        )
        if not chat_id:
            return {
                "text": "PLUGIN_ERR cursor create-chat did not return a chat id",
                "returncode": 1,
                "stderr": str(minted.get("stderr") or ""),
                "backend": "cursor",
            }
        save_cursor_session(seat, chat_id)
    argv = cursor_cli_argv(chat_id=chat_id, prompt=prompt, binary=binary)
    return _run_cursor_cmd(argv, env=env, timeout=timeout)


def _invoke_mind_backend(
    runner: str, prompt: str, *, seat: str = "", **kwargs: Any
) -> dict[str, Any]:
    if runner == "cursor":
        return cursor_cli_runner(prompt, seat=seat, **kwargs)
    return grok_cli_runner(prompt, seat=seat, **kwargs)


def mind_turn_runner(prompt: str, *, seat: str = "", **kwargs: Any) -> dict[str, Any]:
    """Use persisted mind/runner. Switch once on quota. Forced env does not flip."""
    mode = mind_runner_mode()
    forced = mode in MIND_RUNNERS
    current = mode if forced else (load_persisted_mind_runner(seat) or "grok")
    result = _invoke_mind_backend(current, prompt, seat=seat, **kwargs)
    text, rc, stderr = _runner_payload(result)
    if rc == 0:
        if not forced:
            persist_mind_runner(seat, current)
        return result
    if forced or not grok_usage_exhausted(text, stderr):
        return result
    nxt = other_mind_runner(current)
    print(
        f"MIND_SWITCH seat={seat} from={current} to={nxt} reason=quota-exhausted",
        flush=True,
    )
    persist_mind_runner(seat, nxt)
    return _invoke_mind_backend(nxt, prompt, seat=seat, **kwargs)


DEFAULT_RUNNER: Callable[..., Any] = mind_turn_runner


def _runner_payload(raw: Any) -> tuple[str, int, str]:
    if raw is None:
        return "", 1, ""
    if isinstance(raw, dict):
        text = str(raw.get("text") or "")
        stderr = str(raw.get("stderr") or "")
        rc = raw.get("returncode")
        if rc is None:
            rc = 0
        try:
            code = int(rc)
        except (TypeError, ValueError):
            code = 1
        return text, code, stderr
    return str(raw), 0, ""


def _is_skip_seat(seat: str) -> bool:
    skipped = skip_seats(ROOT)
    key = canonical_seat(seat, ROOT)
    return key in skipped or seat.strip().lower() in skipped


def process_once(seat: str, *, runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One inbox line → one agent turn. Offset advances only on runner exit 0.

    Hub TASK_STATE_COMPLETED / A2A ACK is a receipt, not mind-turn done.
    Do not treat a COMPLETE hub task as mail consumed. A runner that did
    not run (None) is runner-fail, not harvest-fake success.
    """
    seat = canonical_seat(seat, ROOT)
    if _is_skip_seat(seat):
        print(f"MIND_SKIP seat={seat} reason=skipSeats", flush=True)
        return {"consumed": 0, "reason": "skipSeats"}

    mind_dir(seat)
    grok_home_dir(seat)
    records = _read_new_records(seat)
    if not records:
        return {"consumed": 0, "reason": "empty", "offset": _read_offset(seat)}

    run = runner if runner is not None else DEFAULT_RUNNER
    for end_offset, rec in records:
        if rec.get("__corrupt__"):
            _write_offset(seat, end_offset)
            continue
        task_id = str(rec.get("taskId") or "")
        context_id = str(rec.get("contextId") or "")
        text = _extract_text(rec.get("parts"))
        prompt = text or json.dumps(rec, ensure_ascii=False)
        try:
            raw = run(prompt, seat=seat)
        except Exception as e:
            print(
                f"MIND_FAIL seat={seat} task={task_id} reason=runner-fail "
                f"err={stderr_log_snippet(str(e))}",
                file=sys.stderr,
            )
            return {"consumed": 0, "reason": "runner-fail", "task_id": task_id}

        assistant_text, returncode, stderr = _runner_payload(raw)
        if returncode != 0:
            print(
                f"MIND_FAIL seat={seat} task={task_id} reason=runner-fail "
                f"rc={returncode} stderr={stderr_log_snippet(stderr)}",
                file=sys.stderr,
            )
            return {
                "consumed": 0,
                "reason": "runner-fail",
                "task_id": task_id,
                "returncode": returncode,
            }

        backend = ""
        if isinstance(raw, dict):
            backend = str(raw.get("backend") or "")
        if backend != "cursor":
            mark_session_minted(seat)
        _append_transcript(
            seat,
            {
                "role": "user",
                "content": prompt,
                "taskId": task_id,
                "contextId": context_id,
            },
        )
        _append_transcript(
            seat,
            {
                "role": "assistant",
                "content": assistant_text,
                "format": "json",
            },
        )
        _write_offset(seat, end_offset)
        print(
            f"MIND_TURN seat={seat} task={task_id} offset={end_offset}",
            flush=True,
        )
        return {
            "consumed": 1,
            "reason": "ok",
            "task_id": task_id,
            "offset": end_offset,
        }

    return {"consumed": 0, "reason": "no-actionable", "offset": _read_offset(seat)}


def wait_for_inbox(seat: str, timeout: float = 30.0) -> None:
    inbox = STATE_DIR / seat / "inbox.jsonl"
    offset = _read_offset(seat)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if inbox.is_file() and inbox.stat().st_size > offset:
                return
        except OSError:
            pass
        time.sleep(0.25)


def run_forever(seat: str) -> int:
    seat = canonical_seat(seat, ROOT)
    if _is_skip_seat(seat):
        print(f"MIND_SKIP seat={seat} reason=skipSeats", file=sys.stderr)
        return 2
    _write_pid(seat)
    print(f"MIND_READY seat={seat} state={STATE_DIR} mode=grok-build-mind", flush=True)
    stopping = False

    def _handle(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        print(f"MIND_STOP seat={seat} signal={signum}", flush=True)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    while not stopping:
        result = process_once(seat)
        if result.get("consumed"):
            continue
        if result.get("reason") == "runner-fail":
            end = time.time() + 2.0
            while not stopping and time.time() < end:
                time.sleep(0.25)
            continue
        wait_for_inbox(seat, timeout=30.0)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grok Build seat mind (mailbox + pin + stay-up; grok is the agent)"
    )
    parser.add_argument("--seat", required=True, help="Director seat (floor, ops, …)")
    parser.add_argument("--once", action="store_true", help="Process one pending line then exit")
    args = parser.parse_args(argv)
    seat = canonical_seat(args.seat, ROOT)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if args.once:
        process_once(seat)
        return 0
    return run_forever(seat)


if __name__ == "__main__":
    sys.exit(main())
