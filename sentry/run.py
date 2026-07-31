#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run SentryBench through the published AsDecided CLI."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentry_benchmark import main


if __name__ == "__main__":
    raise SystemExit(main())
