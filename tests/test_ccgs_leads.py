"""CCGS leads: audio + narrative mind seats. No 49-specialist registry.

Directors and leads spawn specialists only via scripts/launch-cloud-extra-high.sh.
Leftover launch map (hive kit) must keep first-class audio + narrative even
when GCS_ACP_SEATS is the crash-safe grok-serve cap.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "a2a" / "lib.py"
DISPATCH = REPO / "scripts" / "a2a" / "dispatch.py"
LAUNCH_DIRECTOR = REPO / "scripts" / "directors" / "launch-director.sh"
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
ACP_CAP = "floor,studio-ops"

CCGS_LEAD_MAP = {
    "producer": "floor-ops",
    "creative": "floor",
    "technical": "systems",
    "game-designer": "content",
    "lead-programmer": "systems",
    "art-director": "art",
    "qa-lead": "qa-a",
    "release-manager": "studio-ops",
}

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


def _load_dispatch(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, DISPATCH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _acp_cap_env() -> dict[str, str]:
    env = {**os.environ, "GCS_ROOT": str(REPO), "GCS_ACP_SEATS": ACP_CAP}
    env.pop("GCS_SKIP_SEATS", None)
    env.pop("GCS_MIND_SEATS", None)
    return env


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
            "audio,narrative,producer,creative"
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
    assert "composer" not in seats
    assert "donald" not in seats


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
    assert "hive" in low or "leftover launch" in low


def test_ccgs_lead_aliases_stay_in_hive_kit() -> None:
    """Fail if CCGS_LEAD_ALIASES drops out of lib.py (do not remint #25)."""
    lib = _load_lib()
    assert lib.CCGS_LEAD_ALIASES == CCGS_LEAD_MAP
    assert "audio" not in lib.CCGS_LEAD_ALIASES
    assert "narrative" not in lib.CCGS_LEAD_ALIASES
    assert "composer" not in lib.CCGS_LEAD_ALIASES


def test_hive_seats_keep_audio_narrative_when_acp_capped() -> None:
    """Leftover launch map is the hive kit, not the GCS_ACP_SEATS serve cap."""
    env = _acp_cap_env()
    proc = subprocess.run(
        ["python3", str(LIB), "hive-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    seats = {s.strip() for s in proc.stdout.splitlines() if s.strip()}
    for name in FIRST_CLASS_LEADS:
        assert name in seats, name
    assert "qa-b" in seats
    for role, seat in CCGS_LEAD_MAP.items():
        assert seat in seats, role
        assert role not in seats
    assert "composer" not in seats
    assert "donald" not in seats
    assert "orchestrator" not in seats
    acp = subprocess.run(
        ["python3", str(LIB), "launch-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert acp.returncode == 0, acp.stderr
    capped = {s.strip() for s in acp.stdout.splitlines() if s.strip()}
    assert "audio" not in capped
    assert "narrative" not in capped
    assert "floor" in capped
    assert "studio-ops" in capped


def test_leftover_dispatch_launch_map_keeps_audio_narrative_under_acp_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GCS_ACP_SEATS", ACP_CAP)
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.delenv("GCS_SKIP_SEATS", raising=False)
    monkeypatch.delenv("GCS_MIND_SEATS", raising=False)
    dispatch = _load_dispatch("gcs_dispatch_ccgs_hive_map")
    seats = dispatch._launch_seats()
    for name in ("audio", "narrative", "floor", "floor-ops", "qa-a", "qa-b"):
        assert name in seats, name
    for role, seat in CCGS_LEAD_MAP.items():
        assert seat in seats, role
        assert role not in seats
    assert "composer" not in seats
    assert "donald" not in seats


def test_leftover_dispatch_does_not_skip_audio_as_not_in_launch_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GCS_ACP_SEATS", ACP_CAP)
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.delenv("GCS_MIND_SEATS", raising=False)
    monkeypatch.delenv("GCS_SKIP_SEATS", raising=False)
    dispatch = _load_dispatch("gcs_dispatch_ccgs_hive_audio")
    state = tmp_path / "a2a-state"
    monkeypatch.setattr(dispatch, "STATE_DIR", state)
    monkeypatch.setattr(dispatch, "GROW_SEATS", frozenset())
    seat_dir = state / "audio"
    seat_dir.mkdir(parents=True)
    rec = {
        "taskId": "t-audio-hive",
        "contextId": "c-audio",
        "parts": [{"kind": "text", "text": "STATUS ping leftover hive"}],
    }
    (seat_dir / "inbox.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    started = dispatch._process_seat("audio", dry_run=True)
    out = capsys.readouterr().out
    assert started == 0
    assert "not-in-launch-map" not in out
    assert "DISPATCH_DRY_RUN seat=audio" in out


def test_leftover_launch_director_accepts_audio_and_producer_under_acp_cap() -> None:
    env = _acp_cap_env()
    audio = subprocess.run(
        ["bash", str(LAUNCH_DIRECTOR), "--dry-run", "audio"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = audio.stdout + audio.stderr
    assert audio.returncode == 0, blob
    assert "unknown seat" not in blob.lower()
    assert LAUNCH in blob
    assert "audio" in blob.lower()

    producer = subprocess.run(
        ["bash", str(LAUNCH_DIRECTOR), "--dry-run", "producer"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    pblob = producer.stdout + producer.stderr
    assert producer.returncode == 0, pblob
    assert "unknown seat" not in pblob.lower()
    assert "floor-ops" in pblob or "Floor-Ops" in pblob or "Floor-ops" in pblob

    specialist = subprocess.run(
        ["bash", str(LAUNCH_DIRECTOR), "--dry-run", "composer"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert specialist.returncode != 0
    assert "composer" not in {
        s.strip()
        for s in subprocess.check_output(
            ["python3", str(LIB), "hive-seats"],
            cwd=str(REPO),
            env=env,
            text=True,
        ).splitlines()
        if s.strip()
    }


def test_optional_mind_seats_still_accept_audio_narrative() -> None:
    env = _acp_cap_env()
    empty = subprocess.run(
        ["python3", str(LIB), "mind-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert empty.returncode == 0, empty.stderr
    assert empty.stdout.strip() == ""
    env["GCS_MIND_SEATS"] = "audio,narrative,producer"
    opted = subprocess.run(
        ["python3", str(LIB), "mind-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert opted.returncode == 0, opted.stderr
    seats = {s.strip() for s in opted.stdout.splitlines() if s.strip()}
    assert seats == {"audio", "narrative", "floor-ops"}
