#!/usr/bin/env python3
"""Resolve GCS_CLOUD_REF via git ls-remote. Cursor Cloud may still reject the same ref."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.I)
VERIFY_ERR_RE = re.compile(
    r"Failed to verify existence of (?:branch|commit) '.+' in repository",
    re.I,
)


def is_cursor_ref_verify_error(text: str) -> bool:
    return bool(VERIFY_ERR_RE.search(text or ""))


def git_ls_remote(url: str, ref: str, runner=subprocess.run) -> str | None:
    url = (url or "").strip()
    ref = (ref or "").strip() or "main"
    if not url:
        return None
    specs = [f"refs/heads/{ref}", f"refs/tags/{ref}", ref]
    seen: set[str] = set()
    for spec in specs:
        if spec in seen:
            continue
        seen.add(spec)
        proc = runner(
            ["git", "ls-remote", url, spec],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            continue
        for line in (proc.stdout or "").splitlines():
            sha = (line.split() or [""])[0].strip()
            if SHA_RE.match(sha):
                return sha.lower() if len(sha) == 40 else sha
    if SHA_RE.match(ref):
        proc = runner(
            ["git", "ls-remote", url, ref],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode == 0:
            for line in (proc.stdout or "").splitlines():
                sha = (line.split() or [""])[0].strip()
                if SHA_RE.match(sha):
                    return sha
        return ref.lower()
    return None


def followup_first_line(*, sha: str, ref: str, url: str) -> str:
    return (
        f"FOLLOWUP_FIRST github_sha={sha} cursor_cannot_verify_ref={ref} repo={url} "
        "use scripts/cloud/followup-cloud-agent.sh <existing-bc-id> (do not retry create)"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("ref", nargs="?", default="main")
    args = parser.parse_args(argv)
    sha = git_ls_remote(args.url, args.ref)
    if not sha:
        print("CLOUD_REF_ERR", flush=True)
        print(f"git ls-remote could not resolve {args.ref} on {args.url}", file=sys.stderr)
        return 1
    print(f"CLOUD_REF_OK sha={sha} ref={args.ref} url={args.url}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
