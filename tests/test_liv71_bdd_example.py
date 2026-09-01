"""LIV-71 BDD example: apply BDD in Action to a real IaC change and log it.

Executable specification of hive law. Living Sky only. Never Bot CloudAgent.
Never Palemon game code. Book titles only — never copyrighted book text.
"""
from __future__ import annotations

from pathlib import Path

from test_apply_log import (
    APPLY_LOG,
    HEALTH,
    HIVE,
    WATCHDOG,
    _base_env,
    _live_health_env,
    _py,
    _run,
)

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "liv71_bdd_in_action.feature"
PRIVATE_GAME = "atebites-hub/" + "palemon"
BDD_MODEL = "BDD in Action"
REAL_IAC = "health_check.sh"


def _feature_text() -> str:
    return FEATURE.read_text(encoding="utf-8")


def test_bdd_feature_file_is_the_living_spec() -> None:
    assert FEATURE.is_file(), "missing tests/features/liv71_bdd_in_action.feature"
    text = _feature_text()
    fold = " ".join(text.lower().split())
    assert "Feature:" in text
    assert BDD_MODEL in text
    assert "LIV-71" in text
    assert REAL_IAC in text
    assert "studio-archive/log" in text
    assert "HEALTH_OK" in text
    assert "Living Sky" in text
    assert "Bot CloudAgent" in text or "bot cloudagent" in fold
    assert "copyright" in fold
    assert PRIVATE_GAME not in text
    assert "Scenario:" in text
    assert "Given " in text and "When " in text and "Then " in text
    for line in text.splitlines():
        if line.strip().startswith(">"):
            assert len(line) < 80


def test_vague_apply_without_real_iac_path_is_rejected(tmp_path: Path) -> None:
    """BDD in Action: a beat that does not name a real IaC artifact is not an apply."""
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    proc = _py(
        [
            "append",
            "--model",
            BDD_MODEL,
            "--change",
            "IaC: vibes only; Palemon: no game code",
        ],
        env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "APPLY_OK" not in blob
    assert "IaC" in blob or "path" in blob.lower()


def test_bdd_in_action_apply_to_health_check_is_logged(tmp_path: Path) -> None:
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    change = (
        "IaC: health_check.sh gates HEALTH_OK on this beat APPLY; "
        "Palemon: no game code"
    )
    proc = _py(
        ["append", "--model", BDD_MODEL, "--change", change],
        env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "APPLY_OK" in blob
    assert BDD_MODEL in blob
    assert REAL_IAC in blob
    logs = list((Path(env["GCS_STUDIO_ARCHIVE"]) / "log").glob("????-??-??.md"))
    assert len(logs) == 1, logs
    text = logs[0].read_text(encoding="utf-8")
    assert BDD_MODEL in text
    assert REAL_IAC in text
    assert "beat=" in text
    assert PRIVATE_GAME not in text
    for line in text.splitlines():
        if "APPLY" in line:
            assert len(line) < 400


def test_watchdog_beat_cites_real_iac_path() -> None:
    text = WATCHDOG.read_text(encoding="utf-8")
    assert "apply_log.py" in text
    assert "health_check.sh" in text or "apply_log.py" in text.split("change=")[-1]
    # The APPLY change= string must name a kit IaC file, not only bus=ok.
    apply_lines = [
        line
        for line in text.splitlines()
        if "change=" in line and "IaC:" in line
    ]
    assert apply_lines, text
    blob = "\n".join(apply_lines)
    assert "health_check.sh" in blob or "apply_log.py" in blob
    assert "acp_inject.py" not in text
    assert "launch-cloud-extra-high" not in text


def test_hive_law_requires_real_iac_path_and_living_sky() -> None:
    hive = HIVE.read_text(encoding="utf-8")
    fold = " ".join(hive.lower().split())
    assert "real" in fold and ("iac" in fold)
    assert "health_check.sh" in hive or "existing" in fold or "path" in fold
    assert "Living Sky" in hive or "living sky" in fold
    assert "Bot CloudAgent" in hive or "bot cloudagent" in fold
    assert BDD_MODEL in hive
    assert PRIVATE_GAME not in hive
    assert "tests/features/liv71_bdd_in_action.feature" in hive


def test_liv71_gherkin_scenarios(tmp_path: Path) -> None:
    """Run the living Gherkin spec. One scenario = one observable hive behavior."""
    scenarios = _parse_feature(FEATURE)
    assert len(scenarios) >= 3, scenarios
    names = [s["name"] for s in scenarios]
    assert any("HEALTH_OK" in n and "without" in n.lower() for n in names)
    assert any(BDD_MODEL in n or "health_check.sh" in n for n in names)
    assert any("real IaC" in n or "does not cite" in n for n in names)
    for scenario in scenarios:
        _run_scenario(scenario, tmp_path)


def _parse_feature(path: Path) -> list[dict[str, object]]:
    scenarios: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("Scenario:"):
            if current is not None:
                scenarios.append(current)
            current = {"name": stripped.split(":", 1)[1].strip(), "steps": []}
            continue
        if current is None:
            continue
        for kw in ("Given ", "When ", "Then ", "And "):
            if stripped.startswith(kw):
                steps = current["steps"]
                assert isinstance(steps, list)
                steps.append(stripped)
                break
    if current is not None:
        scenarios.append(current)
    return scenarios


def _run_scenario(scenario: dict[str, object], tmp_path: Path) -> None:
    name = str(scenario["name"])
    ctx: dict[str, object] = {
        "servers": [],
        "env": None,
        "proc": None,
        "append": None,
    }
    try:
        steps = scenario["steps"]
        assert isinstance(steps, list)
        for step in steps:
            assert isinstance(step, str)
            _run_step(step, ctx, tmp_path / name.replace(" ", "_")[:40])
    finally:
        servers = ctx["servers"]
        assert isinstance(servers, list)
        for server in servers:
            server.shutdown()


def _run_step(step: str, ctx: dict[str, object], tmp_path: Path) -> None:
    if step == "Given live studio probes are up":
        env, servers = _live_health_env(tmp_path)
        ctx["env"] = env
        ctx["servers"] = servers
        return
    if step == "And the current beat has no APPLY line":
        env = ctx["env"]
        assert isinstance(env, dict)
        check = _py(["check"], env)
        assert check.returncode != 0
        return
    if step.startswith("And studio-ops applies ") or step.startswith(
        "Given studio-ops applies "
    ):
        model, change = _parse_applies_step(step)
        env = ctx["env"]
        if not isinstance(env, dict):
            env = _base_env(tmp_path, tmp_path / "a2a-state")
            ctx["env"] = env
        ctx["append"] = _py(
            ["append", "--model", model, "--change", change],
            env,
        )
        return
    if step == "When health_check.sh runs":
        env = ctx["env"]
        assert isinstance(env, dict)
        ctx["proc"] = _run(HEALTH, [], env)
        return
    if step == "Then output does not contain HEALTH_OK":
        proc = ctx["proc"]
        assert proc is not None
        blob = proc.stdout + proc.stderr
        assert "HEALTH_OK" not in blob, blob
        return
    if step == "Then output contains HEALTH_OK":
        proc = ctx["proc"]
        assert proc is not None
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "HEALTH_OK" in blob, blob
        return
    if step == "And the process exits non-zero":
        proc = ctx["proc"]
        assert proc is not None
        blob = proc.stdout + proc.stderr
        assert proc.returncode != 0, blob
        return
    if step == "And output contains APPLY_LOG":
        proc = ctx["proc"]
        assert proc is not None
        blob = proc.stdout + proc.stderr
        assert "APPLY_LOG" in blob, blob
        return
    if step.startswith("And the apply-log cites model "):
        model = step.split("cites model ", 1)[1].strip().strip('"')
        env = ctx["env"]
        assert isinstance(env, dict)
        text = _archive_text(env)
        assert model in text, text
        return
    if step.startswith("And the apply-log cites IaC path "):
        iac = step.split("IaC path ", 1)[1].strip()
        env = ctx["env"]
        assert isinstance(env, dict)
        text = _archive_text(env)
        assert iac in text, text
        return
    if step == "Then the apply command fails":
        append = ctx["append"]
        assert append is not None
        blob = append.stdout + append.stderr
        assert append.returncode != 0, blob
        assert "APPLY_OK" not in blob
        return
    raise AssertionError(f"unmapped Gherkin step: {step}")


def _parse_applies_step(step: str) -> tuple[str, str]:
    rest = step.split("applies ", 1)[1]
    model_part, change_part = rest.split(" to ", 1)
    model = model_part.strip().strip('"')
    change = change_part.strip().strip('"')
    return model, change


def _archive_text(env: dict[str, str]) -> str:
    logs = list((Path(env["GCS_STUDIO_ARCHIVE"]) / "log").glob("*.md"))
    assert logs, env["GCS_STUDIO_ARCHIVE"]
    return logs[0].read_text(encoding="utf-8")


def test_bdd_example_never_launches_bot_cloudagent() -> None:
    feature = _feature_text()
    hive = HIVE.read_text(encoding="utf-8")
    src = APPLY_LOG.read_text(encoding="utf-8")
    watchdog = WATCHDOG.read_text(encoding="utf-8")
    blob = feature + hive + src + watchdog
    assert "launch-cloud-extra-high" not in watchdog
    assert PRIVATE_GAME not in blob
    assert "Never Bot CloudAgent" in feature or "never Bot CloudAgent" in hive
