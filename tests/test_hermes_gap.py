"""LIV-62: Hermes gap analysis is a Linear-ready GCS hive doc, not a vendor.

Does not copy NousResearch/hermes-agent. Directors stay Grok Build minds.
Specialists stay Cursor Cloud Extra High. Board stays tcarac/taskboard.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HIVE = REPO / "docs" / "studio" / "HIVE.md"
GAP = REPO / "docs" / "studio" / "HERMES_GAP.md"
ARCHITECTURE = REPO / "docs" / "ARCHITECTURE.md"
GITMODULES = REPO / ".gitmodules"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
PRIVATE_GAME = "atebites-hub/" + "palemon"

# Specialist roster that must stay Extra High grunts, not registry seats.
SPECIALIST_NOT_SEATS = (
    "composer",
    "mixer",
    "foley",
    "animator",
    "quest-designer",
    "lore-keeper",
)


def _blob() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in (HIVE, GAP, ARCHITECTURE))


def test_liv62_hive_and_gap_docs_exist() -> None:
    assert HIVE.is_file(), "docs/studio/HIVE.md is the Linear document on Grok Cloud Studio"
    assert GAP.is_file(), "docs/studio/HERMES_GAP.md is the Hermes vs GCS gap matrix"


def test_architecture_points_at_hive_and_gap() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "docs/studio/HIVE.md" in text
    assert "docs/studio/HERMES_GAP.md" in text


def test_docs_are_analysis_not_a_hermes_copy() -> None:
    blob = _blob().lower()
    assert "do not vendor" in blob or "does not vendor" in blob
    assert "nousresearch/hermes-agent" in blob
    assert "liv-62" in blob
    assert "linear" in blob
    assert "not a copy of hermes" in blob
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert not (REPO / "vendor" / "hermes").exists()
    modules = GITMODULES.read_text(encoding="utf-8")
    assert "hermes-agent" not in modules
    assert "tcarac/taskboard" in modules
    tree = "\n".join(
        str(p.relative_to(REPO))
        for p in REPO.rglob("*")
        if p.is_file() and ".git" not in p.parts
    )
    for marker in ("vendor/hermes-agent", "vendor/hermes/"):
        assert marker not in tree


def test_gap_matrix_covers_pantheon_surfaces() -> None:
    gap = GAP.read_text(encoding="utf-8").lower()
    for needle in (
        "bot mode",
        "mail is a turn",
        "mcp command center",
        "cron",
        "kanban",
        "delegate",
        "memory",
        "skills",
        "browser",
        "no fake complete",
        "49",
        "extra high",
        "taskboard",
        "two-runtime",
        "v0.21",
    ):
        assert needle in gap, needle


def test_hive_doc_describes_gcs_control_plane() -> None:
    hive = HIVE.read_text(encoding="utf-8").lower()
    for needle in (
        "grok cloud studio",
        "director",
        "extra high",
        "a2a",
        "mind",
        "taskboard",
        "ccgs",
        "living sky",
        "do not vendor",
        "scripts/launch-cloud-extra-high.sh",
    ):
        assert needle in hive, needle
    assert PRIVATE_GAME not in hive
    assert PRIVATE_GAME not in GAP.read_text(encoding="utf-8")


def test_gap_classifies_borrow_skip_and_already_have() -> None:
    gap = GAP.read_text(encoding="utf-8").lower()
    assert "borrow" in gap
    assert "skip" in gap or "do not copy" in gap
    assert "already" in gap or "gcs has" in gap
    assert "intentional" in gap


def test_no_hermes_source_vendored_in_tree() -> None:
    forbidden_names = {
        "message_agent.py",
        "hermes-bots",
        "plugin.yaml",
    }
    hits: list[str] = []
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", ".venv", "node_modules", "vendor"} for part in path.parts):
            continue
        if path.name in forbidden_names:
            hits.append(str(path.relative_to(REPO)))
    assert hits == [], hits
    # vendor/ may only pin taskboard, never hermes.
    vendor = REPO / "vendor"
    if vendor.is_dir():
        names = {p.name for p in vendor.iterdir()}
        assert "hermes-agent" not in names
        assert "hermes" not in names


def test_registry_still_leads_not_hermes_roster() -> None:
    seats = set((json.loads(REGISTRY.read_text(encoding="utf-8")).get("seats") or {}))
    assert len(seats) < 20
    for specialist in SPECIALIST_NOT_SEATS:
        assert specialist not in seats
