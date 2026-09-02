#!/usr/bin/env python3
"""Fail-closed Higgsfield/Sentry art-env leak sentry.

Art MCP leaks keys when Higgsfield (or Sentry) config puts secrets on argv
(ps), stores literals in MCP env/headers, or git-tracks assignments. Never
prints matched values — only path, line, and rule id.

doctor.sh and recover.sh call this against the checkout plus live
$GCS_A2A_STATE grok-home configs. Vault files (studio.env, higgsfield.env,
sentry.env) are not scanned for assignments; MCP documents are.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ART_LEAK_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "higgsfield_key_assignment",
        re.compile(
            r"HIGGSFIELD_(?:API_KEY|SECRET|API_SECRET|TOKEN)\s*=\s*"
            r"['\"]?(?!\$\{)(?!\$[A-Za-z_])[A-Za-z0-9_\-]{16,}"
        ),
    ),
    (
        "sentry_dsn_assignment",
        re.compile(
            r"(?:GCS_)?SENTRY_DSN\s*=\s*['\"]?https://[A-Za-z0-9._\-]+@"
        ),
    ),
]

ARGV_SECRET_FLAGS = {
    "--api-key",
    "--apikey",
    "--api_key",
    "--secret",
    "--token",
    "--dsn",
    "--auth",
    "--authorization",
}

SECRET_ENV_NAMES = {
    "HIGGSFIELD_API_KEY",
    "HIGGSFIELD_SECRET",
    "HIGGSFIELD_API_SECRET",
    "HIGGSFIELD_TOKEN",
    "SENTRY_DSN",
    "GCS_SENTRY_DSN",
    "SENTRY_AUTH_TOKEN",
}

VAULT_NAMES = {
    "studio.env",
    "higgsfield.env",
    "sentry.env",
    "linear.env",
    "agent.env",
    ".env",
}

Hit = tuple[str, str, int]


def is_secret_expansion(value: str) -> bool:
    """True when empty or a ${VAR}/$VAR expansion, not a literal secret."""
    s = (value or "").strip().strip("'\"")
    if not s:
        return True
    if s.startswith("${") and s.endswith("}") and len(s) > 3:
        inner = s[2:-1]
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", inner))
    if s.startswith("$") and re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", s):
        return True
    return False


def scan_text(rel: str, text: str) -> list[Hit]:
    hits: list[Hit] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for rule_id, pattern in ART_LEAK_RULES:
            if pattern.search(line):
                hits.append((rel, rule_id, i))
    return hits


def _line_of(text: str, needle: str) -> int:
    low = text.lower()
    find = needle.lower()
    idx = low.find(find)
    if idx < 0:
        return 1
    return text[:idx].count("\n") + 1


def _is_art_server(name: str, spec: dict[str, Any]) -> bool:
    blob = " ".join(
        [
            str(name),
            str(spec.get("command") or ""),
            str(spec.get("url") or ""),
            " ".join(str(x) for x in (spec.get("args") or [])),
        ]
    ).lower()
    return "higgsfield" in blob or "sentry" in blob


def _env_rule(key: str) -> str:
    upper = str(key).upper()
    if "SENTRY" in upper:
        return "sentry_dsn_literal"
    return "higgsfield_env_literal"


def _scan_mcp_spec(rel: str, text: str, name: str, spec: dict[str, Any]) -> list[Hit]:
    hits: list[Hit] = []
    if not isinstance(spec, dict):
        return hits
    args = spec.get("args") or []
    if not isinstance(args, list):
        args = []
    for item in args:
        token = str(item).strip().lower()
        flag = token.split("=", 1)[0]
        if flag in ARGV_SECRET_FLAGS or token.split(" ", 1)[0] in ARGV_SECRET_FLAGS:
            hits.append((rel, "higgsfield_argv_key", _line_of(text, str(item))))
            break
    env = spec.get("env") or {}
    if isinstance(env, dict):
        for key, raw in env.items():
            if str(key).upper() not in SECRET_ENV_NAMES:
                continue
            if is_secret_expansion(str(raw)):
                continue
            hits.append((rel, _env_rule(str(key)), _line_of(text, str(key))))
    headers = spec.get("headers") or {}
    if isinstance(headers, dict):
        for key, raw in headers.items():
            if str(key).lower() not in {"authorization", "x-api-key", "x-sentry-auth"}:
                continue
            if is_secret_expansion(str(raw)) or "${" in str(raw):
                continue
            hits.append((rel, "higgsfield_bearer_literal", _line_of(text, str(key))))
    return hits


def _walk_mcp_servers(rel: str, text: str, servers: Any) -> list[Hit]:
    hits: list[Hit] = []
    if not isinstance(servers, dict):
        return hits
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        if not _is_art_server(str(name), spec):
            continue
        hits.extend(_scan_mcp_spec(rel, text, str(name), spec))
    return hits


def scan_mcp_document(rel: str, text: str) -> list[Hit]:
    """Scan JSON (mcpServers) or TOML (mcp_servers) for art-tool leaks."""
    hits: list[Hit] = []
    stripped = (text or "").lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            hits.extend(_walk_mcp_servers(rel, text, data.get("mcpServers")))
            return hits
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            data = None
        if isinstance(data, dict):
            servers = data.get("mcp_servers")
            hits.extend(_walk_mcp_servers(rel, text, servers))
            return hits
    # Structural parse failed: still catch argv flags next to higgsfield.
    low = text.lower()
    if "higgsfield" in low:
        for i, line in enumerate(text.splitlines(), start=1):
            tokens = {t.strip().lower().split("=", 1)[0] for t in line.replace(",", " ").split()}
            if tokens & ARGV_SECRET_FLAGS:
                hits.append((rel, "higgsfield_argv_key", i))
    return hits


def _unique_files(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def iter_mcp_files(
    root: Path | None,
    state: Path | None,
    grok_home: Path | None,
) -> list[Path]:
    found: list[Path] = []
    if root is not None:
        for rel in (".cursor/mcp.json", "mcp.json"):
            path = root / rel
            if path.is_file():
                found.append(path)
    if grok_home is not None:
        cfg = grok_home / "config.toml"
        if cfg.is_file():
            found.append(cfg)
    if state is not None and state.is_dir():
        for path in state.rglob("config.toml"):
            if not path.is_file() or path.is_symlink():
                continue
            if "grok-home" in path.parts:
                found.append(path)
        for path in state.rglob("*.json"):
            if not path.is_file() or path.is_symlink():
                continue
            if path.name in VAULT_NAMES:
                continue
            try:
                sample = path.read_text(encoding="utf-8", errors="replace")[:8000]
            except OSError:
                continue
            if "mcpServers" in sample or "higgsfield" in sample.lower():
                found.append(path)
    return _unique_files(found)


def collect_hits(
    root: Path | None = None,
    state: Path | None = None,
    grok_home: Path | None = None,
) -> list[Hit]:
    hits: list[Hit] = []
    for path in iter_mcp_files(root, state, grok_home):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if root is not None:
            try:
                rel = str(path.resolve().relative_to(root.resolve()))
            except ValueError:
                rel = str(path)
        else:
            rel = str(path)
        hits.extend(scan_mcp_document(rel, text))
        if path.name not in VAULT_NAMES:
            hits.extend(scan_text(rel, text))
    return hits


def format_report(hits: list[Hit]) -> str:
    if not hits:
        return "higgsfield_sentry=clean\n"
    lines = ["higgsfield_sentry=FAIL"]
    for rel, rule_id, line in hits:
        lines.append(f"  {rel}:{line} rule={rule_id}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Higgsfield/Sentry art MCP leak sentry")
    parser.add_argument("--root", default="", help="checkout root (mcp.json)")
    parser.add_argument("--state", default="", help="GCS_A2A_STATE (grok-home configs)")
    parser.add_argument("--grok-home", default="", dest="grok_home")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    state = Path(args.state).resolve() if args.state else None
    grok_home = Path(args.grok_home).resolve() if args.grok_home else None
    hits = collect_hits(root=root, state=state, grok_home=grok_home)
    sys.stdout.write(format_report(hits))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
