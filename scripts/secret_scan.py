#!/usr/bin/env python3
"""Fail-closed scan for secrets and product lore before a public push.

Never prints matched secret values — only path, line, and rule id.

mcp.json (including .cursor/mcp.json) fails on API key literals
(LINEAR_API_KEY JSON values, Bearer tokens). Env refs such as
${LINEAR_API_KEY} / ${env:LINEAR_API_KEY} are allowed. This does not remint
the PAL-45 Linear catalog; checkout Linear MCP already uses env refs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
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
    ("linear_key_assignment", re.compile(r"LINEAR_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}")),
    ("webhook_assignment", re.compile(r"GCS_WEBHOOK_SECRET\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}")),
    (
        "sentry_dsn_literal",
        re.compile(
            r"https://[0-9a-fA-F]{16,}@[A-Za-z0-9._-]*ingest[A-Za-z0-9._-]*sentry\.io/\d+"
        ),
    ),
    (
        "sentry_dsn_assignment",
        re.compile(r"(?:SENTRY_DSN|GCS_SENTRY_DSN)\s*=\s*['\"]?https://"),
    ),
    (
        "higgsfield_key_assignment",
        re.compile(
            r"HIGGSFIELD_(?:API_KEY|TOKEN|SECRET|BEARER)\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}"
        ),
    ),
]


def _art_leak_rules() -> list[tuple[str, re.Pattern[str]]]:
    path = Path(__file__).resolve().parent / "studio" / "higgsfield_sentry.py"
    spec = importlib.util.spec_from_file_location("gcs_higgsfield_sentry", path)
    if spec is None or spec.loader is None:
        raise SystemExit("secret_scan: missing scripts/studio/higgsfield_sentry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rules = getattr(mod, "ART_LEAK_RULES", None)
    if not rules:
        raise SystemExit("secret_scan: higgsfield_sentry.ART_LEAK_RULES empty")
    return list(rules)


SECRET_RULES.extend(_art_leak_rules())

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

# Cursor interpolates ${VAR} and ${env:VAR}. Those are refs, not literals.
_ENV_INTERP_RE = re.compile(r"^\$\{(?:env:)?[A-Za-z_][A-Za-z0-9_]*\}$")
_BEARER_ENV_RE = re.compile(
    r"(?i)^Bearer\s+\$\{(?:env:)?[A-Za-z_][A-Za-z0-9_]*\}$"
)
_SECRET_KEY_RE = re.compile(
    r"(?i)(?:API_KEY|SECRET|TOKEN|PASSWORD|AUTHORIZATION)$"
)
_BEARER_LITERAL_RE = re.compile(r"(?i)Bearer\s+(?!\$\{)\S{12,}")
_LIN_API_LITERAL_RE = re.compile(r"\blin_api_[A-Za-z0-9_\-]{8,}\b")
_MCP_JSON_KEY_LITERAL_RE = re.compile(
    r"""["']LINEAR_API_KEY["']\s*:\s*["'](?!\$\{)[^"']{8,}["']"""
)
_MCP_JSON_BEARER_LITERAL_RE = re.compile(
    r"""(?i)["']Authorization["']\s*:\s*["']Bearer\s+(?!\$\{)[^"']{12,}["']"""
)


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


def _is_env_ref_value(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    return bool(_ENV_INTERP_RE.fullmatch(text) or _BEARER_ENV_RE.fullmatch(text))


def _line_containing(text: str, needle: str) -> int:
    if needle:
        for i, line in enumerate(text.splitlines(), start=1):
            if needle in line:
                return i
    return 1


def _consider_mcp_string(
    rel: str,
    text: str,
    key: str,
    value: str,
    hits: list[tuple[str, str, int]],
) -> None:
    stripped = value.strip()
    if _is_env_ref_value(stripped):
        return
    line = _line_containing(text, value if value in text else stripped)
    bearer_lit = bool(_BEARER_LITERAL_RE.search(stripped))
    secret_key = bool(_SECRET_KEY_RE.search(key))
    lin_lit = bool(_LIN_API_LITERAL_RE.search(stripped))
    if bearer_lit:
        hits.append((rel, "mcp_bearer_literal", line))
        return
    if secret_key and stripped:
        hits.append((rel, "mcp_api_key_literal", line))
        return
    if lin_lit:
        hits.append((rel, "mcp_api_key_literal", line))


def scan_mcp_json_lines(rel: str, text: str) -> list[tuple[str, str, int]]:
    hits: list[tuple[str, str, int]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _MCP_JSON_KEY_LITERAL_RE.search(line) or _LIN_API_LITERAL_RE.search(line):
            hits.append((rel, "mcp_api_key_literal", i))
        if _MCP_JSON_BEARER_LITERAL_RE.search(line) or _BEARER_LITERAL_RE.search(line):
            hits.append((rel, "mcp_bearer_literal", i))
    return hits


def scan_mcp_json(rel: str, text: str) -> list[tuple[str, str, int]]:
    """Fail on API key / Bearer literals in mcp.json. Env refs are allowed."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return scan_mcp_json_lines(rel, text)
    hits: list[tuple[str, str, int]] = []

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(val, str):
                    _consider_mcp_string(rel, text, str(key), val, hits)
                else:
                    walk(val)
            return
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, str):
                    # Empty key: skip API_KEY-field rule so ${workspaceFolder} args
                    # stay clean; still flag Bearer / lin_api_ literals.
                    _consider_mcp_string(rel, text, "", item, hits)
                else:
                    walk(item)

    walk(data)
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
        if path.name == "mcp.json":
            hits.extend(scan_mcp_json(rel, text))
    if hits:
        print("secret_scan=FAIL")
        for rel, rule_id, line in hits:
            print(f"  {rel}:{line} rule={rule_id}")
        return 1
    print("secret_scan=clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
