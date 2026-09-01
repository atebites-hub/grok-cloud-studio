"""LIV-63 remaining (beat1740): harvest Hermes mailbox PRs must not land.

GCS #26 and #28 are CLOSED unmerged. They harvested Hermes mailbox helpers
into the grok mailbox and must stay out of main. #47 (LIV-63) supersedes them.

This slice is NOT the #114 plugin port (grok-bot-like mind plugins /
plugin.json / gcs-root handshake). Do not edit #114's branch. Do not
stack-merge #114. Do not vendor Hermes.

Network GitHub is not consulted: live PR state is flaky in CI. The source
of truth for this gate is the in-repo pointer
docs/studio/LIV63_HERMES_BEAT1740.md plus FORBIDDEN_HARVEST_PRS below.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIV63_POINTER = REPO / "docs" / "studio" / "LIV63_HERMES_BEAT1740.md"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
STUDIO_MIND_SERVER = REPO / "plugins" / "studio-mind" / "server.py"
GITMODULES = REPO / ".gitmodules"

# Harvest mailbox PRs. CLOSED unmerged. Must not land. Do not query GitHub
# from this module; the in-repo pointer is the fixture.
FORBIDDEN_HARVEST_PRS: tuple[int, ...] = (26, 28)

# Directories under vendor-like roots that are a vendored Hermes mailbox tree.
FORBIDDEN_VENDOR_DIR_NAMES = frozenset(
    {
        "hermes",
        "hermes-agent",
        "hermes_agent",
        "hermes-bots",
        "nousresearch",
        "nous-hermes",
        "mind-hive",
        "mind-hive-os",
        "harvest-mailbox",
        "hermes-mailbox",
    }
)

VENDOR_TREE_ROOTS = ("vendor", "third_party", "third-party", "external", "vendored")

# Unique helpers #26/#28 would land. In-repo proxy that those PRs stayed
# closed unmerged. Not ACP leftover "harvest" wording in acp_inject.py.
HARVEST_MAILBOX_MARKERS = (
    "format_mail_turn",
    "filter_inbound_mail",
    "MAIL_MAX_CHARS",
)


def vendored_hermes_mailbox_hits(root: Path) -> list[str]:
    """Return relative paths that are a vendored Hermes / harvest-mailbox tree.

    Docs that mention Hermes are allowed. A ``vendor/hermes`` directory
    (or equivalent vendored mailbox) is not.
    """
    hits: list[str] = []
    root = root.resolve()
    gitmodules = root / ".gitmodules"
    if gitmodules.is_file():
        text = gitmodules.read_text(encoding="utf-8", errors="replace").lower()
        if (
            "hermes-agent" in text
            or "nousresearch/hermes" in text
            or "vendor/hermes" in text
        ):
            hits.append(".gitmodules")
    for vendor_root_name in VENDOR_TREE_ROOTS:
        vendor = root / vendor_root_name
        if not vendor.is_dir():
            continue
        for child in vendor.iterdir():
            name = child.name.lower()
            if name in FORBIDDEN_VENDOR_DIR_NAMES or name.startswith("hermes"):
                if child.is_dir() or child.is_symlink():
                    hits.append(str(child.relative_to(root)))
    for name in FORBIDDEN_VENDOR_DIR_NAMES:
        candidate = root / name
        if candidate.is_dir() or candidate.is_symlink():
            hits.append(name)
    return sorted(set(hits))


def test_forbidden_harvest_pr_fixture_is_26_and_28() -> None:
    assert FORBIDDEN_HARVEST_PRS == (26, 28)


def test_studio_pointer_lists_forbidden_harvest_prs_closed_unmerged() -> None:
    """#26/#28 must stay closed unmerged — asserted from in-repo docs, not GitHub."""
    assert LIV63_POINTER.is_file(), LIV63_POINTER
    text = LIV63_POINTER.read_text(encoding="utf-8")
    low = text.lower()
    for number in FORBIDDEN_HARVEST_PRS:
        assert f"#{number}" in text, f"pointer must list forbidden harvest PR #{number}"
    assert "closed unmerged" in low
    assert "must not land" in low
    assert "#47" in text
    assert "liv-63" in low


def test_studio_pointer_forbids_vendoring_hermes() -> None:
    text = LIV63_POINTER.read_text(encoding="utf-8")
    low = text.lower()
    assert "vendor/hermes" in low
    assert "hermes" in low
    assert (
        "must not vendor" in low
        or "must **not** vendor" in low
        or "do not vendor" in low
        or "do **not** vendor" in low
    )


def test_this_module_does_not_query_live_github() -> None:
    """Guard: this gate is the in-repo fixture, not a GitHub HTTP client."""
    src = Path(__file__).read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert "urllib" not in stripped
            assert "requests" not in stripped
            assert "httpx" not in stripped
            assert "subprocess" not in stripped
            assert "socket" not in stripped


def test_repo_has_no_vendored_hermes_or_mailbox_tree() -> None:
    hits = vendored_hermes_mailbox_hits(REPO)
    assert hits == [], hits
    assert not (REPO / "vendor" / "hermes").exists()
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert not (REPO / "vendor" / "hermes_agent").exists()
    assert not (REPO / "hermes-agent").exists()


def test_scanner_fails_when_vendor_hermes_tree_exists(tmp_path: Path) -> None:
    tree = tmp_path / "vendor" / "hermes"
    tree.mkdir(parents=True)
    (tree / "mailbox.py").write_text("# vendored Hermes mailbox\n", encoding="utf-8")
    hits = vendored_hermes_mailbox_hits(tmp_path)
    assert hits, "scanner must fail when vendor/hermes exists"
    assert any(h == "vendor/hermes" or h.startswith("vendor/hermes/") for h in hits)


def test_scanner_fails_when_equivalent_vendored_mailbox_tree_exists(
    tmp_path: Path,
) -> None:
    tree = tmp_path / "vendor" / "hermes-agent"
    tree.mkdir(parents=True)
    (tree / "README.md").write_text("NousResearch hermes-agent\n", encoding="utf-8")
    hits = vendored_hermes_mailbox_hits(tmp_path)
    assert hits, "scanner must fail when vendor/hermes-agent exists"
    assert any("hermes-agent" in h for h in hits)


def test_scanner_fails_when_gitmodules_pins_hermes(tmp_path: Path) -> None:
    (tmp_path / ".gitmodules").write_text(
        '[submodule "vendor/hermes-agent"]\n'
        "\tpath = vendor/hermes-agent\n"
        "\turl = https://github.com/NousResearch/hermes-agent.git\n",
        encoding="utf-8",
    )
    hits = vendored_hermes_mailbox_hits(tmp_path)
    assert hits, "scanner must fail when .gitmodules vendors hermes-agent"
    assert ".gitmodules" in hits


def test_scanner_allows_vendor_taskboard_and_hermes_mentions_in_docs(
    tmp_path: Path,
) -> None:
    board = tmp_path / "vendor" / "taskboard"
    board.mkdir(parents=True)
    (board / "README.md").write_text("tcarac/taskboard\n", encoding="utf-8")
    docs = tmp_path / "docs" / "studio"
    docs.mkdir(parents=True)
    (docs / "note.md").write_text(
        "Do not vendor Hermes. #26 and #28 CLOSED unmerged must not land.\n",
        encoding="utf-8",
    )
    assert vendored_hermes_mailbox_hits(tmp_path) == []


def test_gitmodules_does_not_pin_hermes() -> None:
    text = GITMODULES.read_text(encoding="utf-8")
    low = text.lower()
    assert "hermes" not in low
    assert "nousresearch" not in low
    assert "vendor/taskboard" in text


def test_harvest_mailbox_helpers_from_26_28_are_absent() -> None:
    """In-repo proxy that harvest PRs #26/#28 stayed closed unmerged."""
    mind = MIND_PY.read_text(encoding="utf-8")
    plugin = STUDIO_MIND_SERVER.read_text(encoding="utf-8")
    for marker in HARVEST_MAILBOX_MARKERS:
        assert marker not in mind, marker
        assert marker not in plugin, marker
