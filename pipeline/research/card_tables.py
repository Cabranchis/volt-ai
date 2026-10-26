"""Write the "Results" section of docs/model-card.md from a training run's metrics JSON.

Every figure and every win/loss statement is computed from the file; none is typed by hand.
Run: uv run python card_tables.py results/production_backtest_2026-10-21.json > results_section.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

METHOD_ROWS = [
    ("model", "LightGBM + CQR"),
    ("model_raw", "LightGBM, raw intervals"),
    ("seasonal_naive", "Seasonal naive"),
    ("ets", "ETS"),
]
BUCKET_HEADER = "| Horizon | MASE model | MASE seasonal naive | MASE ETS | MAPE model | MAPE seasonal naive | MAPE ETS | Coverage raw | Coverage CQR | Coverage seasonal naive | Coverage ETS |"


def sci(value: float) -> str:
    return f"{value:.3g}" if value < 1000 else f"{value:.2e}".replace("e+0", "e")


def methods_table(target: dict[str, Any], price: bool) -> list[str]:
    best = min(target["overall"][m]["mase"] for m, _ in METHOD_ROWS if m != "model_raw")
    lines = [
        "| Method | MAPE % | sMAPE % | MASE | Pinball P10 | Pinball P50 | Pinball P90 | P10-P90 coverage | Below P10 | Above P90 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key, label in METHOD_ROWS:
        m = target["overall"][key]
        bold = key != "model_raw" and m["mase"] == best
        name = f"**{label}**" if bold else label
        fmt = (lambda v: f"{v:.1f}") if price else sci
        lines.append(
            f"| {name} | {m['mape']:.2f} | {m['smape']:.2f} | {m['mase']:.3f} | {fmt(m['pinball_p10'])} | "
            f"{fmt(m['pinball_p50'])} | {fmt(m['pinball_p90'])} | {m['coverage_p10_p90']:.2f} | "
            f"{m['below_p10']:.2f} | {m['above_p90']:.2f} |"
        )
    return lines


def bucket_table(target: dict[str, Any]) -> list[str]:
    lines = [BUCKET_HEADER, "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for label, b in target["by_bucket"].items():
        lines.append(
            f"| {label} | {b['model']['mase']:.3f} | {b['seasonal_naive']['mase']:.3f} | {b['ets']['mase']:.3f} | "
            f"{b['model']['mape']:.2f} | {b['seasonal_naive']['mape']:.2f} | {b['ets']['mape']:.2f} | "
            f"{b['model_raw']['coverage_p10_p90']:.2f} | {b['model']['coverage_p10_p90']:.2f} | "
            f"{b['seasonal_naive']['coverage_p10_p90']:.2f} | {b['ets']['coverage_p10_p90']:.2f} |"
        )
    return lines


def verdicts(name: str, t: dict[str, Any]) -> list[str]:
    sn, ets = t["paired"]["seasonal_naive"], t["paired"]["ets"]
    out = []

    def vs(base: dict[str, Any], label: str) -> str:
        gain = base["mase_reduction_pct"]
        p = base["wilcoxon_p"]
        p_text = "p < 0.001" if p < 0.001 else f"p = {p:.3f}"
        sig = "significant" if p < 0.05 else "not significant"
        lead = (
            f"beats {label} on MASE by {gain:.1f} %"
            if gain > 0
            else f"does not beat {label}: its MASE is {abs(gain):.1f} % higher"
        )
        return f"{lead} (it wins {base['origins_won']} of {base['origins']} origins, Wilcoxon {p_text}, {sig})"

    out.append(f"- **The model {vs(sn, 'seasonal naive')} and {vs(ets, 'ETS')}.**")
    wins_all = all(
        b["model"]["mase"] < min(b["seasonal_naive"]["mase"], b["ets"]["mase"]) for b in t["by_bucket"].values()
    )
    lost = [k for k, b in t["by_bucket"].items() if b["model"]["mase"] >= min(b["seasonal_naive"]["mase"], b["ets"]["mase"])]
    if wins_all:
        out.append("  - It has the lowest MASE in every horizon bucket.")
    else:
        buckets = ", ".join(lost)
        out.append(f"  - It does not have the lowest MASE in the horizon buckets {buckets} days.")
    horizons = t["by_horizon"]
    best_at = sum(
        1
        for h in horizons.values()
        if h["model"]["mase"] < min(h["seasonal_naive"]["mase"], h["ets"]["mase"])
    )
    out.append(f"  - Per individual horizon it has the lowest MASE at {best_at} of {len(horizons)} horizons.")
    cov = t["coverage"]
    m = t["overall"]["model"]
    out.append(
        f"- **Calibration lifts P10-P90 coverage from {cov['raw']:.2f} (raw) to {cov['calibrated']:.2f}** "
        f"(nominal 0.80); the tails are {m['below_p10']:.0%} below P10 and {m['above_p90']:.0%} above P90. "
        f"The P90 pinball loss goes from {t['overall']['model_raw']['pinball_p90']:.3g} (raw) to {m['pinball_p90']:.3g}."
    )
    by_origin = sorted(t["by_origin"], key=lambda r: -r["model_mase"])
    worst = ", ".join(f"{r['origin']} (MASE {r['model_mase']:.2f}, coverage {r['model_coverage']:.2f})" for r in by_origin[:3])
    out.append(f"- The weakest origins are {worst}.")
    covs = [r["model_coverage"] for r in t["by_origin"]]
    out.append(f"  - Coverage per origin ranges from {min(covs):.2f} to {max(covs):.2f}.")
    return out


# Published in the previous model card (run 20261024T214240Z-280431a), before the market features.
PREVIOUS = {
    "demand_kwh": {"mape": 1.76, "mase": 0.718, "coverage": 0.83, "buckets": ("0.680", "0.643", "0.768")},
    "price_mean_cop_kwh": {"mape": 34.75, "mase": 2.021, "coverage": 0.87, "buckets": ("1.270", "1.917", "2.403")},
}


def change_table(d: dict[str, Any], p: dict[str, Any]) -> list[str]:
    lines = [
        "| Target | | MAPE % | MASE | P10-P90 coverage | MASE by horizon bucket |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for key, label, t in (("demand_kwh", "Demand", d), ("price_mean_cop_kwh", "Spot price", p)):
        old, new = PREVIOUS[key], t["overall"]["model"]
        buckets = " / ".join(f"{b['model']['mase']:.3f}" for b in t["by_bucket"].values())
        lines.append(
            f"| {label} | previous run | {old['mape']:.2f} | {old['mase']:.3f} | {old['coverage']:.2f} | "
            f"{' / '.join(old['buckets'])} |"
        )
        lines.append(
            f"| {label} | this run | {new['mape']:.2f} | {new['mase']:.3f} | {new['coverage_p10_p90']:.2f} | {buckets} |"
        )
    return lines


def section(metrics: dict[str, Any]) -> str:
    d, p = metrics["targets"]["demand_kwh"], metrics["targets"]["price_mean_cop_kwh"]
    lines = [
        "## Results (reported origins only)",
        "",
        f"### Demand, horizons 1 to {d['horizon']} days ({d['n_rows']} forecasts)",
        "",
        *methods_table(d, price=False),
        "",
        *bucket_table(d),
        "",
        "Pinball loss is in kWh.",
        "",
        "Verdicts:",
        "",
        *verdicts("demand", d),
        "",
        f"### Spot price (daily mean), horizons 1 to {p['horizon']} days ({p['n_rows']} forecasts)",
        "",
        *methods_table(p, price=True),
        "",
        *bucket_table(p),
        "",
        "Pinball loss is in COP/kWh.",
        "",
        "Verdicts:",
        "",
        *verdicts("price", p),
        "",
        "### Change against the previous run",
        "",
        "The previous run's figures are those published in the earlier version of this card. Buckets are 1-7, 8-14 and 15-30 days for demand and 1-3, 4-7 and 8-14 days for price.",
        "",
        *change_table(d, p),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(section(data))
