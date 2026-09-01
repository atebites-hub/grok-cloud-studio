"""Rotate huge seat inbox.jsonl without dropping unread lines.

Consumed prefix is cut. wake.offset / mind/offset (and leftover
dispatch.offset when present) stay consistent so leftover dispatch and
mind harvest do not reread megabyte tails. Distinct from leftover ACP
wake FAT (GCS #103).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "a2a" / "lib.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
WAKE_PY = REPO / "scripts" / "a2a" / "wake-daemon.py"
DISPATCH_PY = REPO / "scripts" / "a2a" / "dispatch.py"
A2A_DOC = REPO / "docs" / "A2A.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _lib() -> ModuleType:
    return _load(LIB, "gcs_lib_inbox_rotate")


def _line(task_id: str, text: str) -> bytes:
    rec = {
        "taskId": task_id,
        "contextId": "ctx-1",
        "parts": [{"kind": "text", "text": text}],
    }
    return (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")


def _write_inbox(seat_dir: Path, chunks: list[bytes]) -> list[int]:
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    ends: list[int] = []
    with inbox.open("wb") as fh:
        for raw in chunks:
            fh.write(raw)
            ends.append(fh.tell())
    return ends


def _write_int(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(value) + "\n", encoding="utf-8")


def _read_int(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").strip() or "0")


def _inbox_tasks(seat_dir: Path) -> list[str]:
    inbox = seat_dir / "inbox.jsonl"
    if not inbox.is_file():
        return []
    out: list[str] = []
    for line in inbox.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        out.append(str(rec.get("taskId") or ""))
    return out


def test_rotate_drops_consumed_prefix_keeps_unread(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "floor"
    pad = _line("consumed-1", "x" * 400)
    unread = _line("unread-1", "keep me")
    ends = _write_inbox(seat, [pad, unread])
    _write_int(seat / "wake.offset", ends[0])
    _write_int(seat / "mind" / "offset", ends[0])
    result = lib.rotate_inbox(seat, max_bytes=100)
    assert result["rotated"] is True
    assert result["cut"] == ends[0]
    assert _inbox_tasks(seat) == ["unread-1"]
    assert (seat / "inbox.jsonl").stat().st_size == len(unread)
    assert _read_int(seat / "wake.offset") == 0
    assert _read_int(seat / "mind" / "offset") == 0


def test_rotate_keeps_unread_when_mind_lags_wake(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "ops"
    a = _line("a", "one")
    b = _line("b", "two")
    c = _line("c", "three")
    ends = _write_inbox(seat, [a, b, c])
    # wake consumed a+b; mind only consumed a. Cut at mind (do not drop b).
    _write_int(seat / "wake.offset", ends[1])
    _write_int(seat / "mind" / "offset", ends[0])
    result = lib.rotate_inbox(seat, max_bytes=1)
    assert result["rotated"] is True
    assert result["cut"] == ends[0]
    assert _inbox_tasks(seat) == ["b", "c"]
    assert _read_int(seat / "mind" / "offset") == 0
    assert _read_int(seat / "wake.offset") == ends[1] - ends[0]


def test_rotate_does_not_drop_unread_when_min_offset_is_zero(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "floor"
    ends = _write_inbox(seat, [_line("u1", "y" * 400), _line("u2", "still unread")])
    _write_int(seat / "wake.offset", 0)
    _write_int(seat / "mind" / "offset", 0)
    result = lib.rotate_inbox(seat, max_bytes=10)
    assert result["rotated"] is False
    assert result["reason"] == "unread-at-head"
    assert _inbox_tasks(seat) == ["u1", "u2"]
    assert _read_int(seat / "wake.offset") == 0
    assert _read_int(seat / "mind" / "offset") == 0
    assert (seat / "inbox.jsonl").stat().st_size == ends[-1]


def test_rotate_skips_under_max_bytes(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "floor"
    ends = _write_inbox(seat, [_line("a", "small"), _line("b", "also")])
    _write_int(seat / "wake.offset", ends[0])
    result = lib.rotate_inbox(seat, max_bytes=10_000)
    assert result["rotated"] is False
    assert result["reason"] == "under-max"
    assert _inbox_tasks(seat) == ["a", "b"]
    assert _read_int(seat / "wake.offset") == ends[0]


def test_rotate_full_consume_empties_file_and_zeros_offsets(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "floor"
    ends = _write_inbox(seat, [_line("done", "z" * 200)])
    _write_int(seat / "wake.offset", ends[0])
    _write_int(seat / "mind" / "offset", ends[0])
    _write_int(seat / "dispatch.offset", ends[0])
    result = lib.rotate_inbox(seat, max_bytes=10)
    assert result["rotated"] is True
    assert (seat / "inbox.jsonl").stat().st_size == 0
    assert _inbox_tasks(seat) == []
    assert _read_int(seat / "wake.offset") == 0
    assert _read_int(seat / "mind" / "offset") == 0
    assert _read_int(seat / "dispatch.offset") == 0


def test_rotate_keeps_incomplete_trailing_line(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "floor"
    complete = _line("done", "w" * 180)
    partial = b'{"taskId":"partial"'
    ends = _write_inbox(seat, [complete, partial])
    _write_int(seat / "mind" / "offset", len(complete))
    result = lib.rotate_inbox(seat, max_bytes=10)
    assert result["rotated"] is True
    raw = (seat / "inbox.jsonl").read_bytes()
    assert raw == partial
    assert _read_int(seat / "mind" / "offset") == 0


def test_rotate_missing_offset_files_are_not_treated_as_zero(tmp_path: Path) -> None:
    """leftover dispatch.offset is often absent on GROW/mind seats.

    Treating a missing dispatch.offset as 0 would pin cut at head and
    never drop the consumed prefix.
    """
    lib = _lib()
    seat = tmp_path / "floor"
    pad = _line("old", "p" * 300)
    unread = _line("new", "keep")
    ends = _write_inbox(seat, [pad, unread])
    _write_int(seat / "mind" / "offset", ends[0])
    result = lib.rotate_inbox(seat, max_bytes=50)
    assert result["rotated"] is True
    assert _inbox_tasks(seat) == ["new"]
    assert not (seat / "dispatch.offset").is_file()
    assert _read_int(seat / "mind" / "offset") == 0


def test_physical_offset_accounts_for_rotate_during_inflight(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "floor"
    a = _line("a", "consumed-prefix-" + ("x" * 80))
    b = _line("b", "in-flight")
    c = _line("c", "later")
    ends = _write_inbox(seat, [a, b, c])
    _write_int(seat / "mind" / "offset", ends[0])
    dropped_at_start = lib.inbox_dropped(seat)
    # Harvest saw line b ending at ends[1] in old coordinates, then rotate.
    result = lib.rotate_inbox(seat, max_bytes=1)
    assert result["rotated"] is True
    physical = lib.physical_inbox_offset(ends[1], dropped_at_start, seat)
    assert physical == ends[1] - ends[0]
    lib.write_inbox_offset(seat / "mind" / "offset", physical)
    assert _inbox_tasks(seat) == ["b", "c"]
    assert _read_int(seat / "mind" / "offset") == physical


def test_append_after_rotate_is_not_lost(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "floor"
    ends = _write_inbox(seat, [_line("old", "q" * 220), _line("unread", "keep")])
    _write_int(seat / "wake.offset", ends[0])
    lib.rotate_inbox(seat, max_bytes=10)
    lib.append_inbox_record(seat, {
        "taskId": "fresh",
        "parts": [{"kind": "text", "text": "appended after rotate"}],
    })
    assert _inbox_tasks(seat) == ["unread", "fresh"]


def test_threaded_append_during_rotate_does_not_drop_unread(tmp_path: Path) -> None:
    lib = _lib()
    seat = tmp_path / "floor"
    pad = _line("old", "r" * 8000)
    unread = _line("unread", "keep-unread")
    ends = _write_inbox(seat, [pad, unread])
    _write_int(seat / "wake.offset", ends[0])
    errors: list[BaseException] = []

    def _rotate() -> None:
        try:
            lib.rotate_inbox(seat, max_bytes=100)
        except BaseException as exc:  # noqa: BLE001 — capture for join
            errors.append(exc)

    def _append() -> None:
        try:
            time.sleep(0.01)
            lib.append_inbox_record(seat, {
                "taskId": "race",
                "parts": [{"kind": "text", "text": "during rotate"}],
            })
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    rot = threading.Thread(target=_rotate)
    app = threading.Thread(target=_append)
    rot.start()
    app.start()
    rot.join(timeout=5)
    app.join(timeout=5)
    assert errors == []
    tasks = _inbox_tasks(seat)
    assert "unread" in tasks
    assert "race" in tasks
    assert "old" not in tasks


def test_mind_harvest_after_rotate_does_not_reread_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind = _load(MIND_PY, "gcs_mind_inbox_rotate")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_INBOX_MAX_BYTES", "120")
    seen: list[str] = []

    def fake_runner(prompt: str, *, seat: str = "", **_kwargs: object) -> dict:
        seen.append(prompt)
        return {"text": json.dumps({"ok": True}), "returncode": 0, "stderr": ""}

    monkeypatch.setattr(mind, "DEFAULT_RUNNER", fake_runner)
    seat = state / "floor"
    pad = _line("consumed", "n" * 200)
    unread = _line("keep-mind", "second harvest")
    ends = _write_inbox(seat, [pad, unread])
    _write_int(seat / "mind" / "offset", ends[0])
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert seen == ["second harvest"]
    assert "n" * 20 not in "".join(seen)
    assert _inbox_tasks(seat) == [] or _inbox_tasks(seat) == ["keep-mind"]
    # Consumed prefix must be gone so a later harvest cannot reread it.
    tasks = _inbox_tasks(seat)
    assert "consumed" not in tasks
    again = mind.process_once("floor")
    assert again["consumed"] == 0
    assert seen == ["second harvest"]


def test_leftover_dispatch_after_rotate_does_not_reread_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch = _load(DISPATCH_PY, "gcs_dispatch_inbox_rotate")
    state = tmp_path / "a2a-state"
    inject_stamp = tmp_path / "inject.extra"
    fake_inject = tmp_path / "fake_acp_inject.py"
    fake_inject.write_text(
        "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
        f"Path({str(inject_stamp)!r}).write_text(sys.argv[-1], encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_inject.chmod(fake_inject.stat().st_mode | 0o111)
    monkeypatch.setattr(dispatch, "STATE_DIR", state)
    monkeypatch.setattr(dispatch, "ACP_INJECT", fake_inject)
    monkeypatch.setattr(dispatch, "GROW_SEATS", frozenset())
    monkeypatch.setattr(dispatch, "_daemon_healthy", lambda seat: True)
    monkeypatch.setattr(dispatch, "_ensure_daemon", lambda seat: True)
    monkeypatch.setattr(dispatch, "_CHILDREN", {})
    monkeypatch.setattr(dispatch, "_wake_owns_inbox", lambda seat: False)
    monkeypatch.setattr(dispatch, "_mind_owns_inbox", lambda seat: False)
    monkeypatch.setenv("GCS_INBOX_MAX_BYTES", "80")
    seat = state / "qa-a"
    pad = _line("old-dispatch", "d" * 240)
    unread = _line("new-dispatch", "LAUNCH ONLY leftover after rotate")
    ends = _write_inbox(seat, [pad, unread])
    _write_int(seat / "dispatch.offset", ends[0])
    got = dispatch._read_new_records("qa-a")
    records = got[0]
    texts = []
    for _end, rec in records:
        if rec.get("__corrupt__"):
            continue
        texts.append(json.dumps(rec))
    blob = "\n".join(texts)
    assert "old-dispatch" not in blob
    assert "new-dispatch" in blob
    assert "d" * 40 not in blob
    assert _read_int(seat / "dispatch.offset") == 0
    assert "old-dispatch" not in _inbox_tasks(seat)


def test_leftover_dispatch_skip_still_rotates_mind_owned_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = _load(DISPATCH_PY, "gcs_dispatch_rotate_on_skip")
    state = tmp_path / "a2a-state"
    monkeypatch.setattr(dispatch, "STATE_DIR", state)
    monkeypatch.setattr(dispatch, "GROW_SEATS", frozenset())
    monkeypatch.setattr(dispatch, "_CHILDREN", {})
    monkeypatch.setenv("GCS_INBOX_MAX_BYTES", "60")
    monkeypatch.setenv("GCS_MIND_SEATS", "qa-a")
    seat = state / "qa-a"
    (seat / "mind").mkdir(parents=True)
    (seat / "mind" / "pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    pad = _line("old-mind", "m" * 300)
    unread = _line("keep-mind", "unread mind line")
    ends = _write_inbox(seat, [pad, unread])
    _write_int(seat / "mind" / "offset", ends[0])
    started = dispatch._process_seat("qa-a", dry_run=False)
    assert started == 0
    out = capsys.readouterr().out
    assert "mind-owns-inbox" in out
    assert not (seat / "dispatch.offset").is_file()
    assert _inbox_tasks(seat) == ["keep-mind"]
    assert _read_int(seat / "mind" / "offset") == 0


def test_wait_for_inbox_rereads_offset_after_rotate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib = _lib()
    wake = _load(WAKE_PY, "gcs_wake_wait_rotate")
    state = tmp_path / "a2a-state"
    monkeypatch.setattr(wake, "STATE_DIR", state)
    seat = state / "floor"
    pad = _line("old", "s" * 400)
    ends = _write_inbox(seat, [pad])
    _write_int(seat / "wake.offset", ends[0])
    # Stale in-memory offset would miss growth after compact.
    def _rotate_then_append() -> None:
        time.sleep(0.05)
        lib.rotate_inbox(seat, max_bytes=10)
        lib.append_inbox_record(seat, {
            "taskId": "after-wait",
            "parts": [{"kind": "text", "text": "new after rotate"}],
        })

    worker = threading.Thread(target=_rotate_then_append)
    worker.start()
    t0 = time.time()
    wake.wait_for_inbox("floor", timeout=2.0)
    elapsed = time.time() - t0
    worker.join(timeout=3)
    assert elapsed < 1.8, f"waited {elapsed:.2f}s; rotate must not pin stale offset"
    assert "after-wait" in _inbox_tasks(seat)


def test_inbox_max_bytes_env(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = _lib()
    monkeypatch.delenv("GCS_INBOX_MAX_BYTES", raising=False)
    assert lib.inbox_max_bytes() == 1_048_576
    monkeypatch.setenv("GCS_INBOX_MAX_BYTES", "4096")
    assert lib.inbox_max_bytes() == 4096


def test_docs_cover_inbox_rotate_not_gcs_103_fat() -> None:
    a2a = A2A_DOC.read_text(encoding="utf-8").lower()
    mind = MIND_DOC.read_text(encoding="utf-8").lower()
    blob = a2a + "\n" + mind
    assert "inbox.jsonl" in blob
    assert "wake.offset" in a2a
    assert "mind/offset" in mind or "mind/offset" in a2a
    assert "rotate" in blob
    assert "unread" in blob
    src_lib = LIB.read_text(encoding="utf-8")
    assert "rotate_inbox" in src_lib
    assert "inbox.lock" in src_lib
    wake_src = WAKE_PY.read_text(encoding="utf-8")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    disp_src = DISPATCH_PY.read_text(encoding="utf-8")
    assert "rotate_inbox" in wake_src
    assert "rotate_inbox" in mind_src
    assert "rotate_inbox" in disp_src
    # Distinct from leftover ACP wake FAT: this slice is mailbox compact.
    assert "session/prompt" in A2A_DOC.read_text(encoding="utf-8")
    assert "fake_acp_serve" not in src_lib
    assert "vendor/hermes" not in src_lib.lower()
    a2a_raw = A2A_DOC.read_text(encoding="utf-8")
    assert "Bot CloudAgent" in a2a_raw
    assert "do not launch bot cloudagent" in a2a_raw.lower()
