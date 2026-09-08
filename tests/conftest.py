"""Required pytest plugin loader for live Palemon bus isolation.

pytest.ini also registers ``-p gcs_pytest_isolate`` so a file-level
invocation cannot skip this conftest. See docs/studio/PYTEST.md.
"""

from __future__ import annotations

pytest_plugins = ("gcs_pytest_isolate",)
