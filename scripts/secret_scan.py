#!/usr/bin/env python3
"""Fail-closed scan for secrets and product lore before a public push.

Never prints matched secret values — only path, line, and rule id.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".a2a-state",
    ".gcs-state",
    "vendor",
}

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".lock"}

SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private_key_block", re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY")),
    ("github_pat", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github_fine_grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("openai_sk", re.compile(r"\bsk-(?:proj-|live-)?[A-Za-z0-9]{20,}\b")),
    ("aws_akia", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("cursor_key_assignment", re.compile(r"CURSOR_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}")),
    ("webhook_assignment", re.compile(r"GCS_WEBHOOK_SECRET\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}")),
    (
        "linear_key_assignment",
        re.compile(r"LINEAR_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    ),
    ("linear_lin_api", re.compile(r"\blin_api_[A-Za-z0-9]{16,}\b")),
]

LORE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "product_lore",
        re.compile(
            r"\b(?:Harbor" + r"light|Lumen" + r"pup|Pok" + "\u00e9mon|Pok" + r"emon)\b",
            re.I,
        ),
    ),
    # Private game GitHub path stays banned. Studio-kit name and PALEMON_*
    # operational knobs (A2A_STATE, TAILSCALE_SERVE, AK_BRIDGE=0) are allowed.
    ("private_game_repo", re.compile("atebites-hub/" + "pale" + "mon", re.I)),
]

TEXT_BYTES_MAX = 1_000_000


def iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_symlink():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        out.append(path)
    return out


def scan_text(rel: str, text: str) -> list[tuple[str, str, int]]:
    hits: list[tuple[str, str, int]] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        for rule_id, pattern in SECRET_RULES + LORE_RULES:
            if pattern.search(line):
                hits.append((rel, rule_id, i))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grok Cloud Studio secret/lore scan")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    hits: list[tuple[str, str, int]] = []
    for path in iter_files(root):
        rel = str(path.relative_to(root))
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:1024]:
            continue
        if len(data) > TEXT_BYTES_MAX:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        hits.extend(scan_text(rel, text))
    if hits:
        print("secret_scan=FAIL")
        for rel, rule_id, line in hits:
            print(f"  {rel}:{line} rule={rule_id}")
        return 1
    print("secret_scan=clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
