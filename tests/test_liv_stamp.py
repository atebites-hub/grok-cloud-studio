"""PAL-43 / LIV-43: every mind turn stamps Living Sky Linear (LIV-*).

Director souls and scripts/directors/common_footer.txt must require a
Living Sky Linear stamp on every mind turn. Palemon Linear is Living Sky
(linear.app/livingsky, team Livingsky / LIV). NEVER Black Swan.

Does not add Linear MCP (PAL-45 / GCS #38/#46). Does not remint GCS #26-#46.
Never Grok Bot CloudAgent. Extra High stays grok-4.6 xhigh fast=false.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
SOULS = REPO / "docs" / "studio" / "directors" / "souls"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
INSTALL_GROK_MCP = REPO / "scripts" / "directors" / "install-grok-mcp.sh"
ARCHITECTURE = REPO / "docs" / "ARCHITECTURE.md"

PRIVATE_GAME = "atebites-hub/" + "palemon"
LINEAR_MCP_URL = "https://mcp.linear.app/mcp"

LIV_STAMP_NEEDLES = (
    "Living Sky",
    "linear.app/livingsky",
    "Livingsky",
    "LIV-*",
    "Black Swan",
)


def _soul_paths() -> list[Path]:
    paths = sorted(SOULS.glob("*/SOUL.md"))
    assert paths, f"no SOUL.md under {SOULS}"
    return paths


def _assert_liv_stamp_law(text: str, *, label: str) -> None:
    assert text, label
    for needle in LIV_STAMP_NEEDLES:
        assert needle in text, f"{label} missing {needle!r}"
    assert "stamp" in text.lower(), f"{label} missing stamp"
    low = text.lower()
    assert "every mind turn" in low, f"{label} missing every mind turn"
    assert "never black swan" in low, f"{label} must forbid Black Swan"
    assert PRIVATE_GAME not in text, f"{label} leaked private game repo"
    assert LINEAR_MCP_URL not in text, f"{label} must not add Linear MCP"


def test_footer_requires_liv_stamp_every_mind_turn() -> None:
    text = FOOTER.read_text(encoding="utf-8")
    _assert_liv_stamp_law(text, label="common_footer.txt")
    assert "liv=<LIV-" in text or "liv=<LIV-*" in text or "liv=LIV-" in text
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in text
    assert "Bot CloudAgent" in text or "Grok Bot CloudAgent" in text
    assert "LINEAR_API_KEY" not in text


def test_director_souls_require_liv_stamp_and_forbid_black_swan() -> None:
    souls = _soul_paths()
    names = {path.parent.name for path in souls}
    for required in (
        "floor",
        "floor-ops",
        "studio-ops",
        "ops",
        "art",
        "content",
        "systems",
        "qa-a",
        "qa-b",
        "audio",
        "narrative",
        "cloud",
    ):
        assert required in names, required
    for path in souls:
        text = path.read_text(encoding="utf-8")
        _assert_liv_stamp_law(text, label=str(path.relative_to(REPO)))
        assert "LINEAR_API_KEY" not in text


def test_this_ticket_does_not_add_linear_mcp() -> None:
    data = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") or {}
    assert isinstance(servers, dict)
    lowered = {str(name).lower() for name in servers}
    assert "linear" not in lowered
    assert "taskboard" in lowered
    blob = json.dumps(data)
    assert LINEAR_MCP_URL not in blob
    assert "LINEAR_API_KEY" not in blob
    common = SEAT_COMMON.read_text(encoding="utf-8")
    install = INSTALL_GROK_MCP.read_text(encoding="utf-8")
    assert "mcp_servers.linear" not in common
    assert "mcp_servers.linear" not in install
    assert LINEAR_MCP_URL not in common
    assert LINEAR_MCP_URL not in install


def test_architecture_points_footer_at_liv_stamp() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "scripts/directors/common_footer.txt" in text
    assert "Living Sky" in text
    assert "LIV-*" in text
    assert "Black Swan" in text
    assert PRIVATE_GAME not in text
    assert LINEAR_MCP_URL not in text
