#!/usr/bin/env python3
"""Read Sentry DSN from process env or cloud-env Secrets. Never a literal.

Cursor Extra High and Grok Build both use SENTRY_DSN / GCS_SENTRY_DSN.
Values live in the LIV-84 cloud-env snapshot / dashboard Secrets / studio.env.
This module does not initialize a vendor SDK and never prints the DSN.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

DSN_ENV_NAMES = ("SENTRY_DSN", "GCS_SENTRY_DSN")


def sentry_dsn_from_env(env: Mapping[str, str] | None = None) -> str | None:
    """Return the first non-empty DSN env value, or None."""
    src: Mapping[str, str] = os.environ if env is None else env
    for name in DSN_ENV_NAMES:
        value = (src.get(name) or "").strip()
        if value:
            return value
    return None
