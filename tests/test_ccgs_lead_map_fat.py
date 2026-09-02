"""FAT: CCGS audio/narrative first-class mind seats. Aliases resolve.

Unmapped specialist titles do not mint seats. Not a 49-specialist registry.
Distinct from LIV-41 mind-must-launch clones and leftover hive launch-map.

Never Bot CloudAgent. Never vendor Hermes. Never merge GCS #26+#28.
Palemon Linear is Living Sky (LIV), never Black Swan Money.
Extra High pin: grok-4.6 xhigh fast=false.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "ccgs_audio_narrative_map.feature"
LIB = REPO / "scripts" / "a2a" / "lib.py"
TICKER_PY = REPO / "scripts" / "a2a" / "host-ticker.py"
CLOCK_SH = REPO / "scripts" / "directors" / "host-clock-ticker.sh"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
A2A_DOC = REPO / "docs" / "A2A.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
SPAWN = REPO / "scripts" / "cloud" / "directors_spawn.py"
PRIVATE_GAME = "atebites-hub/" + "palemon"

CCGS_LEAD_ALIASES = {
    "producer": "floor-ops",
    "creative": "floor",
    "technical": "systems",
    "game-designer": "content",
    "lead-programmer": "systems",
    "art-director": "art",
    "qa-lead": "qa-a",
    "release-manager": "studio-ops",
}

UNMAPPED_SPECIALISTS = (
    "composer",
    "mixer",
    "sfx",
    "foley",
    "narrative-designer",
    "dialogue-writer",
    "sound-designer",
    "audio-programmer",
    "quest-designer",
    "live-ops-specialist",
)

SCENARIO_BINDINGS = {
    "Aliases in lib.py resolve onto first-class seats": (
        "test_scenario_aliases_in_lib_py_resolve"
    ),
    "Unmapped specialist titles do not mint seats": (
        "test_scenario_unmapped_specialists_do_not_mint_seats"
    ),
}


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _cli_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["GCS_ROOT"] = str(REPO)
    env.pop("GCS_SKIP_SEATS", None)
    if extra:
        env.update(extra)
    return env


def _lib_lines(cmd: str, *args: str, env: dict[str, str] | None = None) -> tuple[int, list[str], str]:
    proc = subprocess.run(
        ["python3", str(LIB), cmd, *args],
        cwd=str(REPO),
        env=env or _cli_env(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    lines = [s.strip() for s in proc.stdout.splitlines() if s.strip()]
    return proc.returncode, lines, proc.stderr


def test_feature_binds_scenarios_and_stays_off_liv41_hive() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    low = text.lower()
    assert "ccgs" in low
    assert "audio" in low and "narrative" in low
    assert "49" in text or "specialist" in low
    assert "lib.py" in text
    assert "unmapped" in low or "do not mint" in low
    assert "liv-41" in low
    assert "mind-must-launch" in low
    assert "playability" in low
    assert "black swan" in low
    assert "living sky" in low
    assert PRIVATE_GAME not in text
    assert "hive_seats" not in text
    for title, fn in SCENARIO_BINDINGS.items():
        assert title in text, title
        assert fn in globals(), fn
    spawn = SPAWN.read_text(encoding="utf-8") if SPAWN.is_file() else ""
    # Lead-map FAT: do not import or call LIV-41 spawn helpers.
    assert "directors_spawn" not in Path(__file__).read_text(encoding="utf-8").split("SPAWN", 1)[0]
    assert SPAWN.name == "directors_spawn.py"
    assert "must_launch" in spawn
    src = LIB.read_text(encoding="utf-8")
    assert "CCGS_LEAD_ALIASES" in src
    alias_block = src.split("CCGS_LEAD_ALIASES", 1)[1].split("}", 1)[0]
    assert "composer" not in alias_block
    assert "narrative-designer" not in alias_block


def test_scenario_aliases_in_lib_py_resolve() -> None:
    for role, seat in CCGS_LEAD_ALIASES.items():
        rc, lines, err = _lib_lines("canonical", role)
        assert rc == 0, err
        assert lines == [seat], f"{role} -> {lines} (want {seat})"
        rc_known, known, kerr = _lib_lines("known", role)
        assert rc_known == 0, kerr
        assert known == [seat], f"known {role} -> {known}"
    for first in ("audio", "narrative"):
        rc, lines, err = _lib_lines("canonical", first)
        assert rc == 0, err
        assert lines == [first], first
        rc_known, known, kerr = _lib_lines("known", first)
        assert rc_known == 0, kerr
        assert known == [first], first
    rc, lines, err = _lib_lines(
        "mind-seats",
        env=_cli_env(
            {
                "GCS_MIND_SEATS": (
                    "audio,narrative,producer,creative,technical,"
                    "art-director,qa-lead,release-manager"
                )
            }
        ),
    )
    assert rc == 0, err
    seats = set(lines)
    assert {"audio", "narrative", "floor-ops", "floor", "systems", "art", "qa-a", "studio-ops"} <= seats
    for alias in CCGS_LEAD_ALIASES:
        assert alias not in seats, alias


def test_scenario_unmapped_specialists_do_not_mint_seats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mixed_mind = "audio,narrative,producer,composer,narrative-designer,sound-designer"
    mixed_grow = "floor,composer,mixer,foley,narrative-designer"
    mixed_acp = "floor,studio-ops,composer,audio-programmer,quest-designer"
    env = _cli_env(
        {
            "GCS_MIND_SEATS": mixed_mind,
            "GCS_GROW_SEATS": mixed_grow,
            "GCS_ACP_SEATS": mixed_acp,
        }
    )
    rc, mind, err = _lib_lines("mind-seats", env=env)
    assert rc == 0, err
    rc, grow, err = _lib_lines("grow-seats", env=env)
    assert rc == 0, err
    rc, launch, err = _lib_lines("launch-seats", env=env)
    assert rc == 0, err
    for collection, names in (("mind", mind), ("grow", grow), ("launch", launch)):
        got = set(names)
        assert "audio" in got or collection != "mind"
        assert "narrative" in got or collection != "mind"
        if collection == "mind":
            assert "floor-ops" in got
            assert "producer" not in got
        if collection == "grow":
            assert "floor" in got
        if collection == "launch":
            assert "floor" in got
            assert "studio-ops" in got
        for specialist in UNMAPPED_SPECIALISTS:
            assert specialist not in got, f"{collection} minted {specialist}: {sorted(got)}"

    for specialist in UNMAPPED_SPECIALISTS:
        rc, lines, err = _lib_lines("known", specialist, env=env)
        assert rc != 0, f"known {specialist} minted {lines}"
        assert lines == []
        assert "unknown seat" in err.lower() or "not a registry" in err.lower()
        assert specialist not in err.lower() or "unknown" in err.lower()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    names = set(registry.get("seats") or {})
    assert "audio" in names and "narrative" in names
    assert len(names) < 20
    for specialist in UNMAPPED_SPECIALISTS:
        assert specialist not in names

    state = tmp_path / "a2a-state"
    ticker = _load(TICKER_PY, "gcs_ccgs_map_fat_ticker")
    monkeypatch.setattr(ticker, "STATE_DIR", state)
    monkeypatch.setattr(ticker, "ROOT", REPO)
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_MIND_SEATS", mixed_mind)
    monkeypatch.setenv("GCS_GROW_SEATS", mixed_grow)
    monkeypatch.setenv("GCS_ACP_SEATS", mixed_acp)
    n = ticker.tick_once()
    assert n >= 1
    assert (state / "audio" / "inbox.jsonl").is_file()
    assert (state / "narrative" / "inbox.jsonl").is_file()
    assert (state / "floor-ops" / "inbox.jsonl").is_file() or (
        state / "floor" / "inbox.jsonl"
    ).is_file()
    for specialist in UNMAPPED_SPECIALISTS:
        assert not (state / specialist).exists(), f"ticker minted {specialist}"
    assert not (state / "producer").exists()

    n_forced = ticker.tick_once(
        seats=("composer", "narrative-designer", "producer", "audio")
    )
    assert n_forced >= 1
    assert (state / "audio" / "inbox.jsonl").is_file()
    assert (state / "floor-ops" / "inbox.jsonl").is_file()
    assert not (state / "composer").exists()
    assert not (state / "narrative-designer").exists()
    assert not (state / "producer").exists()

    clock_state = tmp_path / "clock-state"
    clock_env = _cli_env({"GCS_A2A_STATE": str(clock_state)})
    for specialist in ("composer", "narrative-designer", "sound-designer"):
        proc = subprocess.run(
            ["bash", str(CLOCK_SH), "enqueue_continue", specialist],
            cwd=str(REPO),
            env=clock_env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "HOST_CLOCK_SKIP" in blob or "not-a-registry-seat" in blob
        assert not (clock_state / specialist).exists(), f"clock minted {specialist}"
    producer = subprocess.run(
        ["bash", str(CLOCK_SH), "enqueue_continue", "producer"],
        cwd=str(REPO),
        env=clock_env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert producer.returncode == 0, producer.stdout + producer.stderr
    assert (clock_state / "floor-ops" / "inbox.jsonl").is_file()
    assert not (clock_state / "producer").exists()
    audio = subprocess.run(
        ["bash", str(CLOCK_SH), "enqueue_continue", "audio"],
        cwd=str(REPO),
        env=clock_env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert audio.returncode == 0, audio.stdout + audio.stderr
    assert (clock_state / "audio" / "inbox.jsonl").is_file()


def test_bus_start_does_not_mint_unmapped_specialist_dirs(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "GCS_MIND_SEATS",
            "GCS_GROW_SEATS",
            "GCS_ACP_SEATS",
            "GCS_WAKE_SEATS",
            "GCS_START_SEAT_DAEMONS",
            "GCS_ACP_STOP_WITH_BUS",
            "GCS_MIND_PLUS_ACP_WAKE",
            "GCS_BOT_BRIDGE",
            "GCS_SKIP_SEATS",
        }
    }
    env.update(
        {
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(state),
            "GCS_MIND_SEATS": "audio,narrative,producer,composer,narrative-designer",
            "GCS_GROW_SEATS": "floor,composer,sound-designer",
            "GCS_ACP_SEATS": "floor,studio-ops",
            "GCS_START_SEAT_DAEMONS": "0",
            "GCS_ACP_STOP_WITH_BUS": "1",
            "GCS_BOT_BRIDGE": "0",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LC_ALL": "C",
            "TERM": "dumb",
        }
    )
    try:
        proc = subprocess.run(
            ["bash", str(BUS_SH), "start"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
        )
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "STUDIO_BUS_MIND_START seat=audio" in blob or "STUDIO_BUS_MIND_ALREADY seat=audio" in blob
        assert "STUDIO_BUS_MIND_START seat=narrative" in blob or "STUDIO_BUS_MIND_ALREADY seat=narrative" in blob
        assert "STUDIO_BUS_MIND_START seat=floor-ops" in blob or "STUDIO_BUS_MIND_ALREADY seat=floor-ops" in blob
        assert "seat=composer" not in blob
        assert "seat=narrative-designer" not in blob
        assert "seat=producer" not in blob or "floor-ops" in blob
        persist = (state / "dispatch.mind-seats").read_text(encoding="utf-8")
        persisted = {p.strip() for p in persist.replace(",", "\n").split() if p.strip()}
        assert "audio" in persisted and "narrative" in persisted
        assert "floor-ops" in persisted
        assert "composer" not in persisted
        ticker_log = state / "host-ticker.log"
        deadline = time.time() + 8.0
        while time.time() < deadline:
            log = ticker_log.read_text(encoding="utf-8") if ticker_log.is_file() else ""
            if "TICKER_ENQUEUE" in log or "TICKER_READY" in log:
                break
            time.sleep(0.05)
        log = ticker_log.read_text(encoding="utf-8") if ticker_log.is_file() else ""
        assert "TICKER_ENQUEUE" in log or "TICKER_READY" in log, blob + "\n" + log
        for specialist in ("composer", "narrative-designer", "sound-designer", "producer"):
            assert specialist not in persisted
            assert f"seat={specialist}" not in log
            assert not (state / specialist).exists(), f"bus minted {specialist}"
        assert (state / "audio" / "mind").is_dir()
        assert (state / "narrative" / "mind").is_dir()
        assert (state / "floor-ops" / "mind").is_dir()
    finally:
        subprocess.run(
            ["bash", str(BUS_SH), "stop"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
        )


def test_docs_name_the_map_and_the_fat() -> None:
    a2a = A2A_DOC.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    blob = a2a + "\n" + mind
    low = blob.lower()
    assert "ccgs_audio_narrative_map.feature" in blob
    assert "unmapped" in low
    assert "audio" in low and "narrative" in low
    assert "49" in blob or "specialist" in low
    assert "CCGS_LEAD_ALIASES" in blob or "lib.py" in blob
    assert PRIVATE_GAME not in blob
    assert "hive_seats" not in blob
    assert "must_launch" not in low
    assert "playability" not in low
