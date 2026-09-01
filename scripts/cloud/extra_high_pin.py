#!/usr/bin/env python3
"""Fail-closed Extra High env pin (LIV-67 / LIV-69). Opus/Auto must never launch."""

from __future__ import annotations

import os
import sys

PIN_MODEL = "grok-4.6"
PIN_EFFORT = "xhigh"


def assert_extra_high_env() -> None:
    leaked = (os.environ.get("CURSOR_CLOUD_MODEL") or "").strip()
    if leaked and leaked != PIN_MODEL:
        raise SystemExit(
            f"CLOUD_BLOCKED: CURSOR_CLOUD_MODEL={leaked} rejected; Extra High is {PIN_MODEL} xhigh fast=false only"
        )
    effort = (os.environ.get("CURSOR_CLOUD_EFFORT") or "").strip()
    if effort and effort != PIN_EFFORT:
        raise SystemExit(
            f"CLOUD_BLOCKED: CURSOR_CLOUD_EFFORT={effort} rejected; Extra High effort is {PIN_EFFORT} only"
        )


def main() -> int:
    assert_extra_high_env()
    print(f"CLOUD_PIN_OK model={PIN_MODEL} effort={PIN_EFFORT} fast=false", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
