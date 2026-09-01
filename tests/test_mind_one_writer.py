"""LIV-85 / LIV-96: process_once is the sole mind/mail.txt writer."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from test_mind import (
    MIND_PY,
    _argv_log,
    _prep_mind,
    _write_fake_grok,
)


def _write_seat_mail_callers(path: Path) -> list[str]:
    """Function names that call write_seat_mail. process_once must be the only one."""

    class Finder(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []
            self.callers: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if isinstance(func, ast.Name) and func.id == "write_seat_mail":
                self.callers.append(self.stack[-1] if self.stack else "<module>")
            self.generic_visit(node)

    finder = Finder()
    finder.visit(ast.parse(path.read_text(encoding="utf-8")))
    return finder.callers


def test_process_once_is_sole_mail_txt_writer() -> None:
    """Independent hive slice: one writer. Runners bind mail.txt; they do not write it."""
    callers = _write_seat_mail_callers(MIND_PY)
    assert callers == ["process_once"], callers
    src = MIND_PY.read_text(encoding="utf-8")
    assert "def write_seat_mail(" in src
    assert "def bind_seat_mail(" in src


def test_runners_do_not_write_status_ack_over_unread_beat_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """STATUS ACK is an action. grok/cursor runners must not clobber an unread TASK.

    process_once already wrote the beat TASK. Inflight may be cleared (crash /
    leftover). A later STATUS runner still must not be a second mail.txt writer.
    """
    grok_log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="onewriter", grok=grok
    )
    seat = "floor-ops"
    task_text = (
        "TASK from Donald: staff the floor beat until eight Extra High are RUNNING"
    )
    status_text = (
        "STATUS ACK: keep-alive token=tick-floor-ops-1. Quote token in STATUS."
    )
    assert mind.write_seat_mail(seat, task_text) is True
    mind.clear_mail_inflight(seat)
    mail = state / seat / "mind" / "mail.txt"
    before = mail.read_text(encoding="utf-8")
    assert task_text in before
    assert "STATUS ACK" not in before

    grok_try = mind.grok_cli_runner(status_text, seat=seat)
    cursor_try = mind.cursor_cli_runner(status_text, seat=seat)
    assert int(grok_try.get("returncode") or 1) != 0
    assert int(cursor_try.get("returncode") or 1) != 0
    after = mail.read_text(encoding="utf-8")
    assert after == before
    assert task_text in after
    assert "STATUS ACK" not in after
    assert mind.bind_seat_mail(seat, status_text) is False
    assert mind.bind_seat_mail(seat, task_text) is True
    assert _argv_log(grok_log) == []
