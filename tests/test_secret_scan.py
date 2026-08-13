"""Repo-wide secret/lore scan must stay clean."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "scripts" / "secret_scan.py"


def test_secret_scan_clean() -> None:
    proc = subprocess.run(
        ["python3", str(SCAN), "--root", str(ROOT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "secret_scan=clean" in proc.stdout


def test_no_private_repo_default_in_launchers() -> None:
    banned = "atebites-hub/" + "palemon"
    roots = [ROOT / "scripts", ROOT / "docs", ROOT / "prompts"]
    hits: list[str] = []
    for folder in roots:
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if banned in text:
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []
