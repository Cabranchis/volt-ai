"""Run finalists once on the reported origins (the 24 + 8 warm-up origins that docs/model-card.md used until 2026-10-26).

Usage: python run_reported.py [--demand] <experiment> ...   or   --ensemble <name> <member> <member> ...

The reported origins must not drive model selection, so each name may run only once; the run is
recorded in results/reported_runs.json and a second run needs --force. The origins are those of the
earlier model card (data up to 2026-10-21, step 45 days, 32 origins). The card now uses a fixed
calendar (step 21 days from 2023-11-21), so these runs are not on its origins.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import pandas as pd

import ensemble
import harness
import run_price
from voltia.features import TARGETS
from voltia.models.backtest import select_origins

END = pd.Timestamp("2026-10-21")
LOG = harness.RESULTS / "reported_runs.json"
TARGET = run_price.TARGET
TAG = "reported"


def origins() -> list[pd.Timestamp]:
    return select_origins(END, max(t.horizon for t in TARGETS.values()), 32, 45)


def register(name: str, force: bool) -> None:
    log = json.loads(LOG.read_text()) if LOG.exists() else {}
    key = f"{TARGET.name}/{name}"
    if key in log and not force:
        raise SystemExit(f"{key} already ran on the reported origins ({log[key]}); use --force to repeat")
    log[key] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(log, indent=2, sort_keys=True))


def finish(name: str, rows: pd.DataFrame, extra: dict) -> dict:
    result = harness.score(rows)
    result.update(extra)
    result["target"] = TARGET.name
    for other in ("ets", "sn"):
        result[f"paired_vs_{other}_mase"] = harness.paired(rows, "m", other, "mase")
        result[f"paired_vs_{other}_pinball"] = harness.paired(rows, "m", other, "pinball")
    result["seconds"] = 0.0
    result["origins"] = [str(o.date()) for o in sorted(rows["origin"].unique())]
    harness.save_result(f"reported_{name}", TARGET.name, result)
    rows.to_csv(harness.DATA / f"rows_reported_{name}.csv", index=False)
    return result


def main(args: list[str]) -> None:
    force = "--force" in args
    names = [a for a in args if not a.startswith("--")]
    data = harness.load_data()
    planned = origins()
    base = harness.cached_baselines(data, TARGET, planned, TAG)
    if "--ensemble" in args:
        name, *members = names
        register(name, force)
        pred = ensemble.combine([f"reported_{m}" for m in members])
        rows = harness.finish_rows(pred, data, TARGET, base)
        result = finish(name, rows, {"experiment": {"name": name, "ensemble_of": members}})
        print(run_price.summary_line(name, result))
        return
    for name in names:
        register(name, force)
        exp = run_price.EXPERIMENTS[name]
        prepared = run_price.extended(data, exp)
        frames = [run_price.forecast_origin(prepared, o, exp) for o in planned]
        rows = harness.finish_rows(pd.concat(frames, ignore_index=True), data, TARGET, base)
        result = finish(name, rows, {"experiment": {"name": name, "family": exp.family, "blocks": list(exp.blocks)}})
        print(run_price.summary_line(name, result), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
