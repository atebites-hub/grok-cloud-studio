"""LIV-93: Higgsfield + Sentry on Grok Build and Cursor Cloud art env.

Two catalogs stay two. Cloud-env is LIV-84 (do not remint). Cursor
`.cursor/mcp.json` stays Linear HTTP + taskboard; Extra High Higgsfield is
the existing cloud-env snapshot login plus dashboard Secrets — never a
GROK_HOME dump. Grok-home Higgsfield is grok-only. No OAuth retry loop.
PAL-8 Dewcave generate stays HOLD without a session. Never invent PNG.
Never print credentials.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
ART_DIR = REPO / "docs" / "studio" / "art"
CATALOGS = ART_DIR / "catalogs.json"
GROK_HIGGS = ART_DIR / "grok-home-higgsfield.toml.example"
CLOUD_SECRETS = ART_DIR / "cloud-env-secrets.example"
PAL8 = ART_DIR / "pal8-hold.json"
ART_ENV_DOC = ART_DIR / "ART_ENV.md"
SENTRY_ENV = REPO / "scripts" / "art" / "sentry_env.py"
SECRET_SCAN = REPO / "scripts" / "secret_scan.py"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
CLOUD_ENV_CARD = REPO / "docs" / "a2a" / "cards" / "cloud-env.json"
CLOUD_ENV_PROMPT = REPO / "prompts" / "cloud_env.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
AGENTS = REPO / "AGENTS.md"
ART_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "art" / "SOUL.md"
ART_MEMORY = REPO / "docs" / "studio" / "directors" / "souls" / "art" / "MEMORY.md"
GITIGNORE = REPO / ".gitignore"
DOT_ENV_EXAMPLE = REPO / ".env.example"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"

HIGGSFIELD_MCP_URL = "https://mcp.higgsfield.ai/mcp"
BLACK_SWAN = "Black Swan Money"
PRIVATE_GAME = "atebites-hub/" + "palemon"

_OAUTH_WHILE_LOOP = re.compile(
    r"(?is)while\s+True\s*:[\s\S]{0,1200}?(?:mcp_auth|CallMcpAuth|oauth\s+login)"
)
_OAUTH_RANGE_LOOP = re.compile(
    r"(?is)for\s+\w+\s+in\s+range\s*\(\s*[2-9]\d*\s*\)\s*:[\s\S]{0,1200}?(?:mcp_auth|CallMcpAuth)"
)
_OAUTH_RETRY_CALL = re.compile(
    r"(?is)(?:mcp_auth|CallMcpAuth)\s*\([\s\S]{0,200}?\bretry\b"
)


def _load_json(path: Path) -> dict:
    assert path.is_file(), f"missing {path.relative_to(REPO)}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), path
    return data


def _load_sentry() -> ModuleType:
    assert SENTRY_ENV.is_file(), "scripts/art/sentry_env.py is required"
    spec = importlib.util.spec_from_file_location("gcs_art_sentry_env", SENTRY_ENV)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mcp_servers() -> dict:
    data = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = data.get("mcpServers")
    assert isinstance(servers, dict), data
    return servers


def _code_files() -> list[Path]:
    out: list[Path] = []
    for root in (REPO / "scripts", REPO / "plugins"):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if "vendor" in path.parts or ".venv" in path.parts:
                continue
            if path.suffix in {".py", ".sh"}:
                out.append(path)
    return out


def test_cursor_catalog_is_not_merged_with_grok_home_higgsfield() -> None:
    servers = _mcp_servers()
    assert set(servers) == {"taskboard", "linear"}, servers
    blob = json.dumps(servers)
    low = blob.lower()
    for banned in (
        "higgsfield",
        "studio-mind",
        "chrome-devtools",
        "grok_home",
        "grok-home",
        "config.toml",
        "mcp_servers",
    ):
        assert banned not in low, banned
    assert "mcp.higgsfield.ai" not in low
    catalogs = _load_json(CATALOGS)
    assert catalogs.get("catalogs_merged") is False
    cursor = catalogs["cursor_cloud"]
    assert cursor.get("copy_grok_home") is False
    assert "higgsfield" not in cursor.get("mcp_servers", [])


def test_grok_home_higgsfield_template_is_grok_only() -> None:
    assert GROK_HIGGS.is_file(), "grok-home Higgsfield template missing"
    text = GROK_HIGGS.read_text(encoding="utf-8")
    low = text.lower()
    assert HIGGSFIELD_MCP_URL in text
    assert "[mcp_servers.higgsfield]" in text
    assert "grok-only" in low or "grok only" in low
    assert "do not copy" in low
    assert ".cursor/mcp.json" in text
    assert "GROK_HOME" in text
    assert "Bearer " not in text or "${" in text
    assert "ingest.sentry.io" not in low
    assert PRIVATE_GAME not in text
    catalogs = _load_json(CATALOGS)
    grok = catalogs["grok_build"]
    assert grok.get("higgsfield") == "grok-only"
    assert grok.get("template") == "docs/studio/art/grok-home-higgsfield.toml.example"


def test_no_script_copies_grok_home_into_cursor_mcp() -> None:
    needles = (
        "cp GROK_HOME",
        "copy GROK_HOME",
        "shutil.copy",
    )
    hits: list[str] = []
    for path in _code_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        if "do not copy" in low and "grok_home" in low:
            continue
        if ".cursor/mcp.json" in text and "grok-home" in low:
            if any(
                verb in low
                for verb in ("copy", "dump", "merge into cursor", "write_text")
            ) and "do not" not in low:
                hits.append(str(path.relative_to(REPO)))
        for needle in needles:
            if needle.lower() in low and ".cursor" in low:
                hits.append(f"{path.relative_to(REPO)}:{needle}")
    assert hits == []


def test_no_oauth_retry_loop_encoded() -> None:
    catalogs = _load_json(CATALOGS)
    assert catalogs.get("oauth_retry_loop") is False
    hits: list[str] = []
    for path in _code_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if _OAUTH_WHILE_LOOP.search(text) or _OAUTH_RANGE_LOOP.search(text):
            hits.append(str(path.relative_to(REPO)))
            continue
        if _OAUTH_RETRY_CALL.search(text):
            hits.append(str(path.relative_to(REPO)))
    assert hits == [], f"OAuth retry loop encoded in {hits}"
    soul = ART_SOUL.read_text(encoding="utf-8").lower()
    assert "oauth" in soul
    assert "login" in soul
    art_env = ART_ENV_DOC.read_text(encoding="utf-8").lower()
    assert "mcp_auth" in art_env
    assert "oauth" in art_env
    assert "do not" in art_env


def test_pal8_dewcave_generate_stays_hold_without_session() -> None:
    hold = _load_json(PAL8)
    assert hold.get("id") == "PAL-8"
    assert hold.get("status") == "HOLD"
    assert hold.get("blocked_on") == "session"
    assert hold.get("generate") is False
    assert hold.get("invent_png") is False
    if hold.get("generate") is True:
        assert hold.get("session_unblocked") is True
    catalogs = _load_json(CATALOGS)
    pal8 = catalogs["pal8"]
    assert pal8.get("status") == "HOLD"
    assert pal8.get("generate") is False
    soul = ART_SOUL.read_text(encoding="utf-8")
    memory = ART_MEMORY.read_text(encoding="utf-8")
    art_env = ART_ENV_DOC.read_text(encoding="utf-8")
    for label, text in (("SOUL.md", soul), ("MEMORY.md", memory), ("ART_ENV.md", art_env)):
        assert "PAL-8" in text, label
        low = text.lower()
        assert "hold" in low, label
        assert "dewcave" in low, label
        assert "session" in low, label
    for path in _code_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        if "dewcave" in low and (
            "generate_image" in low or "generate_video" in low or "generate_audio" in low
        ):
            raise AssertionError(
                f"PAL-8 generate unblocked without session in {path.relative_to(REPO)}"
            )


def test_art_env_does_not_invent_png() -> None:
    if ART_DIR.is_dir():
        pngs = [p for p in ART_DIR.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        assert pngs == [], f"do not invent PNG: {pngs}"
    hold = _load_json(PAL8)
    assert hold.get("invent_png") is False


def test_cloud_env_is_liv84_not_a_new_product() -> None:
    catalogs = _load_json(CATALOGS)
    assert catalogs.get("cloud_env_ticket") == "LIV-84"
    assert catalogs.get("remint_cloud_env") is False
    assert catalogs.get("ticket") == "LIV-93"
    registry = _load_json(REGISTRY)
    seats = registry.get("seats") or {}
    assert "cloud-env" not in seats
    card = _load_json(CLOUD_ENV_CARD)
    blob = json.dumps(card)
    assert "LIV-84" in blob or "LIV-84" in CLOUD_ENV_CARD.read_text(encoding="utf-8")
    prompt = CLOUD_ENV_PROMPT.read_text(encoding="utf-8")
    assert "LIV-84" in prompt
    assert "do not remint" in prompt.lower()
    assert not (REPO / ".cursor" / "environment.json").exists()
    art_env = ART_ENV_DOC.read_text(encoding="utf-8")
    low = art_env.lower()
    assert "liv-84" in low
    assert "liv-93" in low
    assert "do not remint" in low
    assert "dashboard" in low and "secret" in low


def test_sentry_and_higgsfield_secrets_from_env_only() -> None:
    secrets = CLOUD_SECRETS.read_text(encoding="utf-8")
    assert "SENTRY_DSN" in secrets
    assert "GCS_SENTRY_DSN" in secrets
    assert "cloud-env" in secrets.lower() or "LIV-84" in secrets
    assert "ingest.sentry.io" not in secrets.lower()
    for line in secrets.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.search(r"=\s*\S", stripped):
            raise AssertionError(f"cloud-env secrets template must not assign values: {stripped}")
    for path in (DOT_ENV_EXAMPLE, STUDIO_ENV_EXAMPLE):
        text = path.read_text(encoding="utf-8")
        assert "SENTRY_DSN" in text
        assert "GCS_SENTRY_DSN" in text
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("SENTRY_DSN=") and not stripped.startswith("#"):
                raise AssertionError(f"{path.name} must not assign SENTRY_DSN")
            if stripped.startswith("GCS_SENTRY_DSN=") and not stripped.startswith("#"):
                raise AssertionError(f"{path.name} must not assign GCS_SENTRY_DSN")
            if stripped.startswith("HIGGSFIELD_") and "=" in stripped and not stripped.startswith("#"):
                raise AssertionError(f"{path.name} must not assign Higgsfield secrets")
    ignore = GITIGNORE.read_text(encoding="utf-8")
    assert "sentry.env" in ignore
    assert "higgsfield.env" in ignore
    agents = AGENTS.read_text(encoding="utf-8")
    assert "SENTRY_DSN" in agents
    assert "Higgsfield" in agents or "higgsfield" in agents.lower()


def test_sentry_dsn_from_env_helper(monkeypatch) -> None:
    mod = _load_sentry()
    assert mod.sentry_dsn_from_env({}) is None
    assert mod.sentry_dsn_from_env({"SENTRY_DSN": "from-cloud-env"}) == "from-cloud-env"
    assert (
        mod.sentry_dsn_from_env({"GCS_SENTRY_DSN": "from-gcs"}) == "from-gcs"
    )
    src = SENTRY_ENV.read_text(encoding="utf-8")
    assert "ingest.sentry.io" not in src
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("GCS_SENTRY_DSN", raising=False)
    assert mod.sentry_dsn_from_env() is None
    monkeypatch.setenv("SENTRY_DSN", "process-env")
    assert mod.sentry_dsn_from_env() == "process-env"


def test_secret_scan_flags_sentry_dsn_and_higgsfield_literals(tmp_path: Path) -> None:
    fake_dsn = "https://" + ("ab" * 16) + "@o0.ingest.sentry.io/99"
    fake_hf = "hf_" + ("c" * 24)
    poisoned = tmp_path / "leak.env"
    poisoned.write_text(
        "SENTRY_DSN=" + fake_dsn + "\n"
        "HIGGSFIELD_API_KEY=" + fake_hf + "\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["python3", str(SECRET_SCAN), "--root", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "sentry_dsn" in blob
    assert "higgsfield" in blob.lower()
    assert fake_dsn not in blob
    assert fake_hf not in blob


def test_docs_split_higgsfield_sentry_across_runtimes() -> None:
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    wipe = WIPE.read_text(encoding="utf-8")
    art_env = ART_ENV_DOC.read_text(encoding="utf-8")
    for label, text in (
        ("CLOUD.md", cloud),
        ("WIPE.md", wipe),
        ("ART_ENV.md", art_env),
    ):
        low = text.lower()
        assert "higgsfield" in low, label
        assert "sentry" in low, label
        assert "liv-84" in low, label
        assert "liv-93" in low, label
        assert "two catalogs" in low or "two catalog" in low, label
        assert BLACK_SWAN.lower() in low or "black swan" in low, label
        assert PRIVATE_GAME not in text
    mind_low = mind.lower()
    assert "palemon" not in mind_low
    assert "higgsfield" in mind_low
    assert "sentry" in mind_low
    assert "grok-only" in mind_low or "grok only" in mind_low
    assert "do not copy" in mind_low
    assert ".cursor/mcp.json" in mind
    assert "SENTRY_DSN" in mind or "sentry" in mind_low
    assert "cloud-env" in art_env.lower()
    assert "snapshot" in art_env.lower() or "secret" in art_env.lower()
    catalogs = _load_json(CATALOGS)
    assert catalogs.get("merge_gcs_26") is False
    assert catalogs.get("merge_gcs_28") is False
