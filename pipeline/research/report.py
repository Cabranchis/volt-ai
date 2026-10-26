"""Build docs/model-experiments.md from the JSON files in results/. Nothing is typed by hand.

Run: uv run python report.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent.parent / "docs" / "model-experiments.md"

DESCRIPTION = {
    "current": "Production model before this work: LightGBM, own history, hydrology, weather, ONI, calendar",
    "d_current": "Production demand model before this work (reference = last value)",
    "ets": "ETS(A,Ad,A), weekly seasonality, fitted on the last 3 years (baseline)",
    "sf_autoets": "statsforecast AutoETS, weekly",
    "sf_autoarima": "statsforecast AutoARIMA, weekly",
    "sf_autotheta": "statsforecast AutoTheta, weekly",
    "sf_mstl": "statsforecast MSTL (7 and 365 days) + AutoETS trend",
    "chronos2_uni": "Chronos-2 foundation model, zero-shot, price history only",
    "chronos2_dc": "Chronos-2 zero-shot with the dispatch cost as past and known-future covariate",
    "chronos2_cov": "Chronos-2 zero-shot with dispatch cost, reservoirs, inflows and demand",
    "chronos2_ft": "Chronos-2 LoRA fine-tuned on the price history, refitted every 6 origins",
    "nhits_exog": "N-HiTS (neuralforecast) with hydrology, dispatch cost and demand covariates",
}
BLOCK_TEXT = {
    "dispatch": "dispatch cost",
    "offers": "offer prices",
    "contracts": "contract and scarcity prices",
    "hydro_now": "newest hydrology",
    "trade": "exports and imports",
    "nowcast": "bias-corrected nowcast",
}


def describe(name: str, result: dict) -> str:
    if name in DESCRIPTION:
        return DESCRIPTION[name]
    exp = result.get("experiment", {})
    if "ensemble_of" in exp:
        return "Mean of the log-quantiles of " + ", ".join(exp["ensemble_of"])
    parts = [exp.get("family", "lightgbm")]
    blocks = exp.get("blocks") or []
    parts.append("features: " + (" + ".join(BLOCK_TEXT.get(b, b) for b in blocks) if blocks else "base"))
    if exp.get("reference") not in (None, "last"):
        parts.append(f"reference {exp['reference']}")
    if exp.get("options"):
        parts.append(", ".join(f"{k}={v}" for k, v in exp["options"].items()))
    return "; ".join(parts)


def row(name: str, r: dict) -> str:
    m, e = r["model"], r["ets"]
    paired = r.get("paired_vs_ets_mase")
    delta = (
        f"{paired['mean_diff']:+.3f} [{paired['ci_low']:+.3f}, {paired['ci_high']:+.3f}]"
        if paired
        else ""
    )
    return (
        f"| `{name}` | {describe(name, r)} | {m['mase']:.3f} | {m['mape']:.1f} | "
        f"{m['pinball_mean']:.3g} | {m['coverage']:.2f} | {delta} |"
    )


def load(target: str) -> dict[str, dict]:
    folder = HERE / "results" / target
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(folder.glob("*.json"))
        if not p.stem.startswith(("spikes", "monthly"))
    }


def table(results: dict[str, dict], names: list[str]) -> list[str]:
    header = [
        "| Candidate | What it is | MASE | MAPE % | Pinball (mean of P10, P50, P90) | P10-P90 coverage | Paired MASE vs ETS |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    return header + [row(n, results[n]) for n in names]


def spike_section() -> list[str]:
    folder = HERE / "results" / "price_mean_cop_kwh"
    dev = json.loads((folder / "spikes_dev.json").read_text())["events"]
    rep = json.loads((folder / "spikes_reported.json").read_text())["events"]
    quant = json.loads((folder / "spikes_from_quantiles.json").read_text())
    lines = [
        "## Probability of a price spike",
        "",
        "Events: price above 500 COP/kWh, above 800, and above 1.3 times its mean of the last 30 days, 1 to 14 days ahead. Brier score, lower is better. `Classifier` is a LightGBM binary model; `From quantiles` reads P(price > threshold) from the forecast's own calibrated P10, P50 and P90 as a log-normal (no new model); `ETS` does the same with the ETS interval; `Persistence` uses P(event | event today) and P(event | no event today) measured on the rows known at each origin; `Base rate` is the training frequency.",
        "",
        "| Period | Event | Event rate | Classifier | From quantiles | ETS | Persistence | Base rate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for period, events, qkey in (("development", dev, "development"), ("reported (classifier run once; quantiles post hoc)", rep, "reported_post_hoc")):
        for event, e in events.items():
            q = quant[qkey][event]["forecast_quantiles"]["brier"]
            lines.append(
                f"| {period} | {event} | {e['event_rate']:.3f} | {e['model']['brier']:.4f} | {q:.4f} | "
                f"{e['ets']['brier']:.4f} | {e['persistence']['brier']:.4f} | {e['base_rate']['brier']:.4f} |"
            )
    lines += [
        "",
        "The classifier does not beat the simpler readings on the reported origins, so it is not shipped. Reading the probability from the forecast quantiles beats ETS and persistence for the 500 COP/kWh and the relative rise in both periods; above 800 the log-normal tail is too thin on the reported origins and persistence is better, so that threshold is not offered.",
        "",
    ]
    return lines


def monthly_section() -> list[str]:
    folder = HERE / "results" / "price_mean_cop_kwh"
    lines = [
        "## Mean price over the next 30, 31-60 and 61-90 days",
        "",
        "Each origin forecasts the mean daily price of three consecutive 30-day windows as a ratio to the mean of the last 30 days. MAPE of the P50 and mean pinball loss (COP/kWh); `persistence` is \"the next window averages what the last 30 days did\". The `analog` method takes the outcomes that followed the 12 most similar past states (reservoirs, inflows, ONI, trend), one per month.",
        "",
        "| Period | Method | MAPE w1 / w2 / w3 | Pinball w1 / w2 / w3 | Coverage w1 / w2 / w3 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for tag, label in (("dev", "development"), ("reported", "reported (run once)")):
        data = json.loads((folder / f"monthly_{tag}.json").read_text())["methods"]
        for method, windows in sorted(data.items()):
            cell = lambda key, fmt: " / ".join(fmt.format(windows[f"window_{k}"][key]) for k in (1, 2, 3) if f"window_{k}" in windows)  # noqa: E731
            lines.append(f"| {label} | `{method}` | {cell('mape', '{:.1f}')} | {cell('pinball_mean', '{:.1f}')} | {cell('coverage', '{:.2f}')} |")
    lines += [
        "",
        "No candidate beats persistence with a paired interval that excludes zero on the development origins, and on the reported origins the errors grow to 30-85 % with no consistent winner. A monthly price outlook is therefore not published; the model card says why.",
        "",
    ]
    return lines


def main() -> None:
    price, demand = load("price_mean_cop_kwh"), load("demand_kwh")
    runs = json.loads((HERE / "results" / "reported_runs.json").read_text())
    dev_price = sorted((n for n in price if not n.startswith("reported_")), key=lambda n: price[n]["model"]["mase"])
    dev_demand = sorted((n for n in demand if not n.startswith("reported_")), key=lambda n: demand[n]["model"]["mase"])
    any_price = price[dev_price[0]]
    ets_row = f"| `ets` | {DESCRIPTION['ets']} | {any_price['ets']['mase']:.3f} | {any_price['ets']['mape']:.1f} | {any_price['ets']['pinball_mean']:.3g} | {any_price['ets']['coverage']:.2f} | |"

    lines = [
        "# Model experiments",
        "",
        "Generated by `pipeline/research/report.py` from `pipeline/research/results/*.json`. Do not edit by hand.",
        "",
        "## Protocol",
        "",
        "- **Development origins** (selection only): every 30 days from 2020-03-01 to 2023-10-12, 45 origins; the first 8 only seed the online interval calibration, so 37 are scored. Every outcome precedes the first reported origin (2023-11-21).",
        "- **Reported origins**: the 24 origins of `docs/model-card.md` (45 days apart, 2023-11-21 to 2026-09-21), plus the same 8 warm-up origins. Each finalist ran once on them (`results/reported_runs.json`); the harness refuses a second run.",
        "- **Forecast date**: XM settles the price about three days late, so a forecast whose origin is the last settled day T is made on T + 3. Series XM publishes sooner (the programmed dispatch cost, hydrology) are read up to the day each is published by then, never beyond. A test scrambles every later value and requires identical features (`research/test_features_ext.py`, `tests/test_features.py`).",
        "- **Metrics**: MASE and MAPE of the P50, mean pinball loss over P10, P50 and P90, coverage of the 80 % interval, and the paired per-origin MASE difference with a bootstrap 95 % interval (negative favours the candidate). Intervals of every candidate go through the same online conformal calibration.",
        f"- **Candidates tried**: {len(dev_price)} on the price and {len(dev_demand)} on the demand, counting baselines and failures.",
        "",
        "## Price, development origins (lower MASE first)",
        "",
        *table(price, dev_price),
        ets_row,
        "",
        "## Demand, development origins (lower MASE first)",
        "",
        *table(demand, dev_demand),
        "",
        "## Reported origins (each run once)",
        "",
        "Price, 1 to 14 days:",
        "",
        *table(price, sorted((n for n in price if n.startswith("reported_")), key=lambda n: price[n]["model"]["mase"])),
        "",
        "Demand, 1 to 30 days:",
        "",
        *table(demand, sorted((n for n in demand if n.startswith("reported_")), key=lambda n: demand[n]["model"]["mase"])),
        "",
        f"Reported runs recorded: {len(runs)}.",
        "",
        *spike_section(),
        *monthly_section(),
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
