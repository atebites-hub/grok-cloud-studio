"""LIV-63 remaining (beat1740): harvest Hermes mailbox PRs must not land.

GCS #26 and #28 are CLOSED unmerged. They harvested Hermes mailbox helpers
into the grok mailbox and must stay out of main. #47 (LIV-63) supersedes them.

This slice is NOT the #114/#134/#90 plugin port (grok-bot-like mind
plugins / plugin.json / gcs-root handshake). Mailbox+spawn is already
on main via #76. skipSeats stay orchestrator/donald. Do not edit those
plugin branches. Do not stack-merge them. Do not vendor Hermes.

Network GitHub is not consulted: live PR state is flaky in CI. The source
of truth for this gate is the in-repo pointer
docs/studio/LIV63_HERMES_BEAT1740.md plus FORBIDDEN_HARVEST_PRS below.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIV63_POINTER = REPO / "docs" / "studio" / "LIV63_HERMES_BEAT1740.md"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_BOT_LIKE = REPO / "scripts" / "a2a" / "mind_bot_like.py"
STUDIO_MIND_SERVER = REPO / "plugins" / "studio-mind" / "server.py"
GITMODULES = REPO / ".gitmodules"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"

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
    table_rows = [
        line
        for line in text.splitlines()
        if line.startswith("|")
        and any(f"#{number}" in line for number in FORBIDDEN_HARVEST_PRS)
    ]
    assert len(table_rows) >= len(FORBIDDEN_HARVEST_PRS), table_rows
    for line in table_rows:
        assert "closed unmerged" in line.lower(), line
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


def test_studio_pointer_keeps_skipseats_orchestrator_donald() -> None:
    """Harvest remainder must not staff Grok Bot seats as minds."""
    assert LIV63_POINTER.is_file(), LIV63_POINTER
    text = LIV63_POINTER.read_text(encoding="utf-8")
    low = text.lower()
    assert "skipseats" in low.replace(" ", "")
    assert "orchestrator" in low
    assert "donald" in low
    assert REGISTRY.is_file(), REGISTRY
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    skip = [str(s) for s in (registry.get("skipSeats") or [])]
    assert "orchestrator" in skip
    assert "donald" in skip


def test_studio_pointer_names_mailbox_spawn_already_on_main() -> None:
    """#76 mailbox+spawn is on main; this slice is harvest-closed, not a plugin twin."""
    text = LIV63_POINTER.read_text(encoding="utf-8")
    assert "#76" in text
    low = text.lower()
    assert "mailbox" in low
    assert "#134" in text or "#114" in text or "#90" in text


def test_harvest_mailbox_helpers_absent_from_mind_bot_like() -> None:
    """#76 remaining file must not restack #26/#28 harvest helpers."""
    assert MIND_BOT_LIKE.is_file(), MIND_BOT_LIKE
    src = MIND_BOT_LIKE.read_text(encoding="utf-8")
    for marker in HARVEST_MAILBOX_MARKERS:
        assert marker not in src, marker
    low = src.lower()
    assert "plugin.yaml" not in low
    assert "nousresearch/hermes" not in low
    assert "format_mail_turn" not in src


def test_mind_grok_argv_is_prompt_file_never_bare_dash_p() -> None:
    """Mind path is grok --resume pinned UUID --prompt-file, never bare -p."""
    mind = MIND_PY.read_text(encoding="utf-8")
    assert "def grok_cli_argv" in mind
    assert "--prompt-file" in mind
    assert "--resume" in mind
    argv_src = mind.split("def grok_cli_argv", 1)[1].split("\ndef ", 1)[0]
    assert '"-p"' not in argv_src
    assert "'-p'" not in argv_src
    assert "session/prompt" not in argv_src
