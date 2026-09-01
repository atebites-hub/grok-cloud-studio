"""LIV-74: directors paste demonstrated N, not leftover-green --override-ini.

Gherkin: tests/features/liv74_demonstrated_n.feature
pytest.ini must not duplicate ship-gate -q (pytest 8+ extra-quiet hides N).
Targeted evidence files, not the leftover 200-test suite.
"""
from __future__ import annotations

from liv_list_bdd import (
    DEMONSTRATE,
    FEATURE_67,
    FEATURE_73,
    FEATURE_74,
    PRIVATE_GAME,
    PYTEST_INI,
    REPO,
)

EVIDENCE_PY = (
    REPO / "tests" / "test_liv67_list_prints_runstatus.py",
    REPO / "tests" / "test_liv73_failing_then_passing.py",
    REPO / "tests" / "test_liv74_demonstrated_n.py",
)


def _ini_addopts(text: str) -> str:
    values: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == "addopts":
            values.append(value.strip())
    return " ".join(values)


def test_liv74_feature_file_is_the_living_spec() -> None:
    text = FEATURE_74.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE_74.is_file()
    assert "LIV-74" in text
    assert "demonstrated n" in fold
    assert "override-ini" in fold
    assert "leftover-green" in fold
    assert "pytest.ini" in fold or "pytest.ini" in text
    assert "living sky" in fold or "liv-74" in text
    assert "bot cloudagent" in fold
    assert PRIVATE_GAME not in text
    assert "Scenario:" in text


def test_liv74_pytest_ini_does_not_force_override_ini_for_demonstrated_n() -> None:
    """Ship-gate `.venv/bin/pytest -q` must print N passed without --override-ini."""
    text = PYTEST_INI.read_text(encoding="utf-8")
    assert PYTEST_INI.is_file()
    assert "--override-ini" not in text
    addopts = _ini_addopts(text)
    assert "-q" not in addopts.split()
    assert "--quiet" not in addopts.split()
    assert "testpaths" in text
    assert "pythonpath" in text


def test_liv74_demonstrate_bdd_is_targeted_not_leftover_green_suite() -> None:
    text = DEMONSTRATE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert DEMONSTRATE.is_file()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "--override-ini" not in stripped
    assert "test_liv67_list_prints_runstatus.py" in text
    assert "test_liv73_failing_then_passing.py" in text
    assert "test_liv74_demonstrated_n.py" in text
    assert "test_list_rows.py" in text
    assert "tests/test_cloud_launch.py" not in text
    assert "leftover-green" in fold or "not leftover" in fold
    assert "pytest" in fold
    mode = DEMONSTRATE.stat().st_mode
    assert mode & 0o111, "demonstrate_bdd.sh must be executable"
    for path in EVIDENCE_PY:
        assert path.is_file(), path
    assert FEATURE_67.is_file()
    assert FEATURE_73.is_file()
    assert FEATURE_74.is_file()
    assert PRIVATE_GAME not in text
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert ".venv/bin/pytest -q" in agents
    assert "--override-ini" not in agents
