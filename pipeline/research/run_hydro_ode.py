"""The reservoir water balance as a differential equation, as a price feature.

Hypothesis: the price over the next 14 days depends on where the national reservoir will stand, not
only on where it stands now. The block `hydro_ode` (features_ext.hydro_ode_projection) projects the
stored energy from the balance dV/dt = I(t) - R with the inflow anomaly relaxing to its mean,
dl/dt = -l / tau, and adds two features per horizon: the projected share of the capacity on the
target day and its change from today. The balance itself closes on the stored history (28-day means
of inflows minus the change of the volume and of generation plus spill correlate 0.985 and differ
by 3 %), which is why the net outflow is read from the identity.

Experiment `fb_hydro_ode` (run_price.py): the production features (`dispatch+contracts+hydro`, the
same LightGBM) plus the two features, on the 37 scored development origins. Nothing after the
reported origin is used.

Decision rule, written before the first run. The block is a candidate for production only if, against
`dispatch+contracts+hydro` on the same rows:
  1. the paired per-origin MASE difference (new minus reference) has a 95 % bootstrap interval whose
     upper end is below 0;
  2. the mean pinball loss is not larger;
  3. the coverage of the calibrated P10-P90 range is between 0.75 and 0.85.
If any fails, the result is recorded as one more candidate and production does not change. If all
hold, the finalist runs once on the reported origins (the harness refuses a second run) and is
shipped only if it also improves there, with an ADR.

    uv run python run_hydro_ode.py          # from pipeline/research

Writes results/hydro_ode.json (the comparison). The experiment itself writes
results/price_mean_cop_kwh/fb_hydro_ode.json.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import features_ext
import harness
import run_price

REFERENCE = "dispatch+contracts+hydro"
NAME = "fb_hydro_ode"


def balance_closure(data: pd.DataFrame) -> dict[str, float]:
    """How well I - dV matches generation plus spill, on the days before the first reported origin."""
    frame = pd.DataFrame(
        {
            "net_outflow": data["inflows_kwh"].astype(float) - data["reservoir_kwh"].astype(float).diff(),
            "generation_plus_spill": data["gen_hydro_kwh"].astype(float) + data["spill_kwh"].fillna(0.0).astype(float),
        }
    )
    frame = frame[(frame.index >= "2019-01-01") & (frame.index < harness.REPORTED_FIRST)].dropna()
    monthly = frame.rolling(28).mean().dropna()
    return {
        "days": int(len(frame)),
        "corr_28day_means": float(monthly["net_outflow"].corr(monthly["generation_plus_spill"])),
        "mean_ratio": float(monthly["net_outflow"].mean() / monthly["generation_plus_spill"].mean()),
    }


def projection_error(data: pd.DataFrame, origins: list[pd.Timestamp]) -> dict[str, dict[str, float]]:
    """Mean absolute error, in share of the capacity, of the projected level against the real one.

    The reference is "the level stays where it was last published". Only the development origins.
    """
    target, _ = features_ext.hydro_ode_projection(data)
    k = features_ext._k("reservoir_kwh", features_ext.PUBLICATION_LAG)
    share = data["reservoir_kwh"].astype(float) / data["reservoir_capacity_kwh"].astype(float)
    stays = share.shift(-k)
    out: dict[str, dict[str, float]] = {}
    for h in (3, 7, 14):
        real = share.shift(-h).reindex(origins)
        projected = target[h].reindex(origins)
        persistence = stays.reindex(origins)
        keep = real.notna() & projected.notna() & persistence.notna()
        out[str(h)] = {
            "origins": int(keep.sum()),
            "mae_projection": float((projected[keep] - real[keep]).abs().mean()),
            "mae_level_stays": float((persistence[keep] - real[keep]).abs().mean()),
        }
    return out


def main() -> None:
    data = harness.load_data()
    target = run_price.TARGET
    origins = harness.dev_origins(target)
    harness.assert_development(origins, target)
    base = harness.cached_baselines(data, target, origins, "dev")
    experiment = run_price.GBMExperiment(blocks=(*run_price.FS1, "hydro_ode"))
    result = run_price.run_gbm(NAME, experiment, data, origins, base)
    print(run_price.summary_line(NAME, result), flush=True)

    new = pd.read_csv(harness.DATA / f"rows_{NAME}.csv", parse_dates=["origin", "day"])
    old = pd.read_csv(harness.DATA / f"rows_{REFERENCE}.csv", parse_dates=["origin", "day"])
    merged = new.merge(old[["origin", "h", "m10", "m50", "m90"]], on=["origin", "h"], suffixes=("", "_ref"), validate="one_to_one")
    for q in ("10", "50", "90"):
        merged[f"o{q}"] = merged[f"m{q}_ref"]
    paired_mase = harness.paired(merged, "m", "o", "mase")
    paired_pinball = harness.paired(merged, "m", "o", "pinball")
    reference = json.loads((harness.RESULTS / "price_mean_cop_kwh" / f"{REFERENCE}.json").read_text())
    new_model, old_model = result["model"], reference["model"]
    checks = {
        "mase_interval_below_zero": bool(paired_mase["ci_high"] < 0),
        "pinball_not_larger": bool(new_model["pinball_mean"] <= old_model["pinball_mean"]),
        "coverage_between_075_and_085": bool(0.75 <= new_model["coverage"] <= 0.85),
    }
    out = {
        "experiment": NAME,
        "reference": REFERENCE,
        "origins": int(merged["origin"].nunique()),
        "model": {k: new_model[k] for k in ("mase", "mape", "pinball_mean", "coverage")},
        "reference_model": {k: old_model[k] for k in ("mase", "mape", "pinball_mean", "coverage")},
        "paired_mase_new_minus_reference": paired_mase,
        "paired_pinball_new_minus_reference": paired_pinball,
        "by_bucket": {
            "new": {b: v["mase"] for b, v in new_model["by_bucket"].items()},
            "reference": {b: v["mase"] for b, v in old_model["by_bucket"].items()},
        },
        "water_balance_closure_before_first_reported_origin": balance_closure(data),
        "projection_error_share_of_capacity": projection_error(data, origins),
        "checks": checks,
        "candidate_for_production": all(checks.values()),
    }
    harness.RESULTS.joinpath("hydro_ode.json").write_text(json.dumps(harness.rounded(out), indent=2), encoding="utf-8")
    print(json.dumps(harness.rounded(out), indent=2))
    assert np.isfinite(paired_mase["mean_diff"])


if __name__ == "__main__":
    main()
