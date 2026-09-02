"""CCGS leads: audio + narrative mind seats. No 49-specialist registry.

Directors and leads spawn specialists only via scripts/launch-cloud-extra-high.sh.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "a2a" / "lib.py"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
SOULS = REPO / "docs" / "studio" / "directors" / "souls"
DOCS_PROMPTS = REPO / "docs" / "studio" / "directors"
PROMPTS = REPO / "prompts"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
LAUNCH = "scripts/launch-cloud-extra-high.sh"
A2A_DOC = REPO / "docs" / "A2A.md"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
STUDIO_ENV = REPO / "studio.env.example"

CCGS_LEAD_MAP = {
    "producer": "floor-ops",
    "creative": "floor",
    "technical": "systems",
    "game-designer": "content",
    "lead-programmer": "systems",
    "art-director": "art",
    "qa-lead": "qa-a",
    "release-manager": "studio-ops",
    # Remaining first-class title aliases (art already has art-director).
    "audio-director": "audio",
    "audio-lead": "audio",
    "narrative-director": "narrative",
    "narrative-lead": "narrative",
}

PALEMON_MIND = (
    "floor-ops,studio-ops,floor,art,content,systems,qa-a,qa-b,audio,narrative"
)
FEATURE = REPO / "tests" / "features" / "ccgs_audio_seat_map.feature"
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"

FIRST_CLASS_LEADS = (
    "floor",
    "floor-ops",
    "studio-ops",
    "art",
    "content",
    "systems",
    "qa-a",
    "audio",
    "narrative",
)

# Sample of the specialist roster that must stay Extra High grunts, not seats.
SPECIALIST_NOT_SEATS = (
    "composer",
    "mixer",
    "sfx",
    "foley",
    "voice-over",
    "writer",
    "editor",
    "quest-designer",
    "level-designer",
    "combat-designer",
    "animator",
    "rigger",
    "lighter",
    "vfx",
    "ui-artist",
    "concept-artist",
    "environment-artist",
    "character-artist",
    "technical-artist",
    "tools-programmer",
    "gameplay-programmer",
    "network-programmer",
    "audio-programmer",
    "narrative-designer",
    "dialogue-writer",
    "lore-keeper",
    "qa-tester",
    "build-engineer",
    "live-ops-specialist",
    "community-manager",
    "localization",
    "cinematics",
    "sound-designer",
    "music-supervisor",
    "implementation-specialist",
    "systems-designer",
    "economy-designer",
    "ux-writer",
    "copywriter",
    "storyboard",
    "mocap",
    "shader-artist",
    "vfx-artist",
    "ui-engineer",
    "backend-engineer",
    "client-engineer",
    "producer-assistant",
    "scrum-master",
    "data-analyst",
)

PRIVATE_GAME = "atebites-hub/" + "palemon"


def _load_lib() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_lib_ccgs", LIB)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _registry_seats() -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    seats = data.get("seats") or {}
    assert isinstance(seats, dict)
    return seats


def _director_prompt(seat: str) -> Path | None:
    name = f"{seat.replace('-', '_')}_director_prompt.txt"
    for directory in (DOCS_PROMPTS, PROMPTS):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def test_audio_and_narrative_are_first_class_registry_seats() -> None:
    seats = _registry_seats()
    assert "audio" in seats
    assert "narrative" in seats
    assert int(seats["audio"]["acpPort"]) == 8754
    assert int(seats["narrative"]["acpPort"]) == 8755
    for name in ("audio", "narrative"):
        card = REPO / seats[name]["card"]
        assert card.is_file(), name
        soul = SOULS / name / "SOUL.md"
        memory = SOULS / name / "MEMORY.md"
        assert soul.is_file(), name
        assert memory.is_file(), name
        prompt = _director_prompt(name)
        assert prompt is not None and prompt.is_file(), name
    skip = json.loads(REGISTRY.read_text(encoding="utf-8")).get("skipSeats") or []
    assert "audio" not in skip
    assert "narrative" not in skip


def test_registry_does_not_mint_specialist_seats() -> None:
    seats = _registry_seats()
    names = set(seats)
    for specialist in SPECIALIST_NOT_SEATS:
        assert specialist not in names, specialist
        assert specialist.replace("_", "-") not in names
    # Leads only — not a 49-specialist floor.
    assert len(names) < 20, sorted(names)
    assert "lead-programmer" not in names


def test_ccgs_lead_aliases_fold_onto_existing_seats() -> None:
    lib = _load_lib()
    for role, seat in CCGS_LEAD_MAP.items():
        assert lib.canonical_seat(role, REPO) == seat, role
    assert lib.canonical_seat("audio", REPO) == "audio"
    assert lib.canonical_seat("narrative", REPO) == "narrative"


def test_mind_seats_accepts_audio_narrative_and_ccgs_aliases() -> None:
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_MIND_SEATS": (
            "floor-ops,studio-ops,floor,art,content,systems,qa-a,qa-b,"
            "audio,narrative,producer,creative,audio-director,narrative-lead,"
            "composer,narrative-designer"
        ),
    }
    env.pop("GCS_SKIP_SEATS", None)
    proc = subprocess.run(
        ["python3", str(LIB), "mind-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    seats = {s.strip() for s in proc.stdout.splitlines() if s.strip()}
    for name in ("audio", "narrative", "floor-ops", "floor"):
        assert name in seats, name
    assert "producer" not in seats
    assert "creative" not in seats
    assert "audio-director" not in seats
    assert "narrative-lead" not in seats
    assert "composer" not in seats
    assert "narrative-designer" not in seats
    assert "donald" not in seats


def test_mind_seats_folds_audio_narrative_titles_without_first_class_names() -> None:
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_MIND_SEATS": "audio-director,narrative-lead,producer",
    }
    env.pop("GCS_SKIP_SEATS", None)
    proc = subprocess.run(
        ["python3", str(LIB), "mind-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    seats = {s.strip() for s in proc.stdout.splitlines() if s.strip()}
    assert seats == {"audio", "narrative", "floor-ops"}


def test_grow_seats_folds_audio_narrative_title_aliases() -> None:
    """Remaining alias work: GROW lists fold CCGS titles, not mint them."""
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_GROW_SEATS": "audio-director,narrative-lead,producer,floor",
    }
    env.pop("GCS_SKIP_SEATS", None)
    proc = subprocess.run(
        ["python3", str(LIB), "grow-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    seats = {s.strip() for s in proc.stdout.splitlines() if s.strip()}
    assert "audio" in seats
    assert "narrative" in seats
    assert "floor-ops" in seats
    assert "floor" in seats
    assert "audio-director" not in seats
    assert "narrative-lead" not in seats
    assert "producer" not in seats


def test_audio_narrative_title_aliases_resolve_director_prompts() -> None:
    lib = _load_lib()
    for title, seat in (
        ("audio-director", "audio"),
        ("audio-lead", "audio"),
        ("narrative-director", "narrative"),
        ("narrative-lead", "narrative"),
    ):
        path = lib.resolve_director_prompt(title, REPO)
        assert path is not None, title
        assert path.name == f"{seat.replace('-', '_')}_director_prompt.txt"


def test_directors_and_leads_spawn_specialists_via_cloud_launcher() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    assert LAUNCH in footer
    assert "specialist" in footer.lower()
    for seat in FIRST_CLASS_LEADS:
        soul = (SOULS / seat / "SOUL.md").read_text(encoding="utf-8")
        assert LAUNCH in soul, seat
        assert PRIVATE_GAME not in soul
        prompt_path = _director_prompt(seat)
        assert prompt_path is not None, seat
        prompt = prompt_path.read_text(encoding="utf-8")
        assert LAUNCH in prompt, seat
        assert PRIVATE_GAME not in prompt


def test_ccgs_map_is_documented() -> None:
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in (A2A_DOC, WIPE, MIND_DOC, STUDIO_ENV)
    )
    low = blob.lower()
    assert "audio" in low and "narrative" in low
    for role, seat in CCGS_LEAD_MAP.items():
        assert role in low, role
        assert seat in low, seat
    assert LAUNCH in blob
    assert "49" in blob or "specialist" in low
    assert PRIVATE_GAME not in blob


def test_wipe_and_mind_name_palemon_audio_narrative_seats() -> None:
    """Remaining WIPE/MIND seats: Palemon mind list includes first-class leads."""
    wipe = WIPE.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    studio = STUDIO_ENV.read_text(encoding="utf-8")
    assert f"GCS_MIND_SEATS={PALEMON_MIND}" in studio
    assert PALEMON_MIND in mind
    assert "audio" in wipe and "narrative" in wipe
    assert "8754" in wipe and "8755" in wipe
    for role in (
        "audio-director",
        "audio-lead",
        "narrative-director",
        "narrative-lead",
    ):
        assert role in wipe, role
        assert role in mind, role
    assert "CCGS_LEAD_ALIASES" in mind or "lib.py" in mind
    assert LAUNCH in wipe and LAUNCH in mind
    assert "49" in wipe or "specialist" in wipe.lower()
    assert PRIVATE_GAME not in wipe and PRIVATE_GAME not in mind


def test_bdd_feature_file_is_remaining_seat_map_not_the_finished_twin() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    low = text.lower()
    assert "audio" in low and "narrative" in low
    assert "alias" in low or "aliases" in low
    assert "wipe" in low and "mind" in low
    assert "launch-cloud-extra-high" in low
    assert "49" in text or "specialist" in low
    assert "gcs-ccgs-audio-narrative-map-beat1849" in text
    assert "do not twin" in low or "distinct from" in low
    assert PRIVATE_GAME not in text
    assert "hive_seats" not in text
    assert "must_launch" not in low


def test_bus_acp_and_wake_canonicalize_ccgs_titles() -> None:
    bus = BUS.read_text(encoding="utf-8")
    acp = bus.split("acp_seats()", 1)[1].split("wake_seats()", 1)[0]
    wake = bus.split("wake_seats()", 1)[1].split("mind_seats()", 1)[0]
    assert "canonical" in acp
    assert "canonical" in wake
    assert "audio-director" not in acp
    assert "composer" not in acp
