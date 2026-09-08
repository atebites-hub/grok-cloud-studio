#!/usr/bin/env python3
"""Hive law (LIV-71): one Manning apply-log line per 10-minute studio-ops beat.

Cite a model *title* from the allowlist and a real IaC/Palemon change
(existing kit path). Never paste copyrighted book text. Stdlib only.
Living Sky only. Never Bot CloudAgent.
"""
from __future__ import annotations

import argparse
import calendar
import os
import re
import sys
import time
from pathlib import Path

MANNING_MODELS: tuple[str, ...] = (
    "Grokking Simplicity",
    "Think Distributed Systems",
    "Looks Good to Me",
    "BDD in Action",
    "Acing the System Design Interview",
)

CHANGE_MAX = 240
APPLY_RE = re.compile(
    r"^\s*[-*]\s*APPLY\s+"
    r"beat=(?P<beat>\S+)\s+"
    r"seat=(?P<seat>\S+)\s+"
    r"model=(?P<model>.+?)\s+"
    r"change=(?P<change>.+)\s*$"
)
BEAT_FMT = "%Y-%m-%dT%H:%MZ"
IAC_PATH_TOKEN_RE = re.compile(
    r"(?:^|[\s:=;,])"
    r"((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:sh|py|md|example))"
)
IAC_BASENAME_DIRS: tuple[tuple[str, ...], ...] = (
    (),
    ("scripts", "studio"),
    ("scripts", "directors"),
    ("scripts", "a2a"),
    ("scripts", "cloud"),
    ("docs", "studio"),
)


def beat_interval_sec() -> int:
    raw = os.environ.get("GCS_BEAT_SEC", "").strip() or os.environ.get(
        "GCS_TICKER_SEC", ""
    ).strip()
    if not raw:
        return 600
    try:
        value = int(raw)
    except ValueError:
        return 600
    return value if value > 0 else 600


def now_ts() -> float:
    raw = os.environ.get("GCS_APPLY_NOW", "").strip()
    if raw:
        return float(raw)
    return time.time()


def beat_id(now: float | None = None, interval: int | None = None) -> str:
    interval = beat_interval_sec() if interval is None else interval
    ts = int(now if now is not None else now_ts())
    floored = ts - (ts % interval)
    return time.strftime(BEAT_FMT, time.gmtime(floored))


def beat_epoch(beat: str, interval: int | None = None) -> int:
    parsed = time.strptime(beat, BEAT_FMT)
    epoch = int(calendar.timegm(parsed))
    interval = beat_interval_sec() if interval is None else interval
    return epoch - (epoch % interval)


def rotate_model(beat: str, interval: int | None = None) -> str:
    interval = beat_interval_sec() if interval is None else interval
    idx = (beat_epoch(beat, interval=interval) // interval) % len(MANNING_MODELS)
    return MANNING_MODELS[idx]


def canonical_seat(seat: str) -> str:
    raw = (seat or "studio-ops").strip() or "studio-ops"
    if raw == "ops":
        return "studio-ops"
    return raw


def kit_root() -> Path:
    root = os.environ.get("GCS_ROOT", "").strip()
    if root:
        return Path(root)
    return Path(__file__).resolve().parents[2]


def iter_iac_path_tokens(change: str) -> list[str]:
    return IAC_PATH_TOKEN_RE.findall(change)


def resolve_iac_path(token: str) -> Path | None:
    """Return the kit file for a change= token, or None if it is not real IaC."""
    raw = token.strip()
    if not raw:
        return None
    root = kit_root()
    rel = Path(raw)
    candidates: list[Path] = [rel] if rel.is_absolute() else [root / rel]
    name = rel.name
    for parts in IAC_BASENAME_DIRS:
        candidates.append(root.joinpath(*parts, name) if parts else root / name)
    seen: set[Path] = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def state_root() -> Path:
    env = os.environ.get("GCS_A2A_STATE", "").strip()
    if env:
        return Path(env)
    root = os.environ.get("GCS_ROOT", "").strip()
    if root:
        return Path(root) / ".a2a-state"
    return Path(__file__).resolve().parents[2] / ".a2a-state"


def archive_root() -> Path:
    env = os.environ.get("GCS_STUDIO_ARCHIVE", "").strip()
    if env:
        return Path(env)
    return state_root() / "studio-archive"


def log_path_for_beat(beat: str) -> Path:
    day = beat[:10]
    return archive_root() / "log" / f"{day}.md"


def validate_model(model: str) -> str:
    name = " ".join(model.split())
    if name not in MANNING_MODELS:
        raise ValueError(
            "unknown model (cite one Manning title: "
            + ", ".join(MANNING_MODELS)
            + ")"
        )
    return name


def validate_change(change: str) -> str:
    text = " ".join(change.split())
    if not text:
        raise ValueError("change is required (IaC/Palemon, no book text)")
    if len(text) > CHANGE_MAX:
        raise ValueError(f"change longer than {CHANGE_MAX} chars")
    if "IaC" not in text or "Palemon" not in text:
        raise ValueError("change must cite the IaC/Palemon change")
    tokens = iter_iac_path_tokens(text)
    if not any(resolve_iac_path(tok) is not None for tok in tokens):
        raise ValueError(
            "change must cite a real IaC path "
            "(health_check.sh, apply_log.py, setup.sh, …)"
        )
    return text


def iter_apply_matches(path: Path) -> list[re.Match[str]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    out: list[re.Match[str]] = []
    for line in text.splitlines():
        match = APPLY_RE.match(line)
        if match:
            out.append(match)
    return out


def beat_has_apply(beat: str) -> bool:
    path = log_path_for_beat(beat)
    for match in iter_apply_matches(path):
        if match.group("beat") == beat:
            return True
    return False


def _header(day: str) -> str:
    return (
        f"# Studio apply-log {day}\n\n"
        "Hive law (LIV-71): one APPLY per 10-minute studio-ops beat. "
        "Cite a Manning model title and the IaC/Palemon change. "
        "Never paste copyrighted book text.\n\n"
    )


def format_apply_line(beat: str, seat: str, model: str, change: str) -> str:
    return (
        f"- APPLY beat={beat} seat={seat} model={model} change={change}"
    )


def append_apply(
    *,
    change: str,
    model: str | None = None,
    seat: str = "studio-ops",
    beat: str | None = None,
) -> tuple[str, str]:
    """Append one APPLY line. Returns (status, line). Idempotent per beat."""
    resolved_beat = beat or beat_id()
    resolved_seat = canonical_seat(seat)
    resolved_model = validate_model(model or rotate_model(resolved_beat))
    resolved_change = validate_change(change)
    line = format_apply_line(
        resolved_beat, resolved_seat, resolved_model, resolved_change
    )
    path = log_path_for_beat(resolved_beat)
    if beat_has_apply(resolved_beat):
        return "APPLY_ALREADY", line
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size == 0:
        path.write_text(_header(resolved_beat[:10]), encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return "APPLY_OK", line


def check_apply(beat: str | None = None) -> tuple[int, str]:
    resolved = beat or beat_id()
    path = log_path_for_beat(resolved)
    if beat_has_apply(resolved):
        return 0, f"APPLY_LOG ok beat={resolved} path={path}"
    return 1, f"APPLY_LOG missing beat={resolved} path={path}"


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Studio-ops hive-law apply-log (LIV-71). "
            "Book titles only; never copyrighted book text."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    append_p = sub.add_parser("append", help="Append one APPLY line for a beat")
    append_p.add_argument("--model", default="", help="Manning model title")
    append_p.add_argument("--change", required=True, help="IaC/Palemon change")
    append_p.add_argument("--seat", default="studio-ops")
    append_p.add_argument("--beat", default="")

    beat_p = sub.add_parser("beat", help="Append this beat (rotate model if omitted)")
    beat_p.add_argument("--model", default="")
    beat_p.add_argument("--change", required=True)
    beat_p.add_argument("--seat", default="studio-ops")
    beat_p.add_argument("--beat", default="")

    check_p = sub.add_parser("check", help="Fail if this beat has no APPLY line")
    check_p.add_argument("--beat", default="")

    sub.add_parser("beat-id", help="Print current beat id")
    path_p = sub.add_parser("path", help="Print dated log path for a beat")
    path_p.add_argument("--beat", default="")
    sub.add_parser("models", help="Print allowed Manning model titles")

    args = parser.parse_args(argv)
    if args.cmd == "models":
        print("\n".join(MANNING_MODELS))
        return 0
    if args.cmd == "beat-id":
        print(beat_id())
        return 0
    if args.cmd == "path":
        print(log_path_for_beat(args.beat or beat_id()))
        return 0
    if args.cmd == "check":
        code, text = check_apply(args.beat or None)
        print(text)
        return code
    if args.cmd in ("append", "beat"):
        try:
            status, line = append_apply(
                change=args.change,
                model=args.model or None,
                seat=args.seat,
                beat=args.beat or None,
            )
        except ValueError as exc:
            return _fail(str(exc))
        print(f"{status} {line}")
        return 0
    return _fail(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
