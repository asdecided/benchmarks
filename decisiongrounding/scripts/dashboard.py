"""Write the benchmark dashboard to a static, self-contained HTML file.

A thin CLI over `runner.dashboard.build_dashboard`. Unlike the live `ui` command
it can compute the offline (zero-spend) cost-vs-N curve and bake it into the
page, so the committed `results/published/index.html` is a standalone snapshot.

    python -m scripts.dashboard \
        --run results/published/<headline>.json \
        --crossover results/crossover_dataset.json --cost-curve \
        --out results/published/index.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.dashboard import build_dashboard  # noqa: E402
from scripts.report import _offline_cost_curve  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the static HTML dashboard.")
    ap.add_argument("--run", required=True)
    ap.add_argument("--crossover")
    ap.add_argument("--cost-curve", action="store_true",
                    help="compute the offline token-cost-vs-N curve (no API spend)")
    ap.add_argument("--pool"); ap.add_argument("--scenarios")
    ap.add_argument("--template", default=None, help="custom dashboard HTML template")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    run = json.loads(Path(args.run).read_text())
    dataset = json.loads(Path(args.crossover).read_text()) if args.crossover else None
    curve = None
    if args.cost_curve and dataset:
        curve = _offline_cost_curve(dataset, args.pool, args.scenarios)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_dashboard(run, dataset, curve, template=args.template), encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
