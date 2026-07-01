#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Entry point for the get-artifact benchmark — a thin shim over the shared harness."""

import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCHMARK_DIR.parent))

from harness import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(benchmark_dir=BENCHMARK_DIR, prog="get-artifact"))
