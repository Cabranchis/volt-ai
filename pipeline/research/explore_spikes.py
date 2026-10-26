"""How often does the daily price pass a threshold, and how persistent is it? Base rates per period."""

import numpy as np
import pandas as pd

import harness

data = harness.load_data()
price = data["price_mean_cop_kwh"].dropna()
mean30 = price.rolling(30, min_periods=20).mean()
periods = {
    "2018-2020": ("2018-01-01", "2020-12-31"),
    "2021-2023-10 (development)": ("2021-01-01", "2023-11-20"),
    "2023-11-21 on (reported)": ("2023-11-21", "2026-10-22"),
}
for label, (a, b) in periods.items():
    p = price.loc[a:b]
    rel = (price / mean30.shift(1)).loc[a:b]
    print(
        f"{label:<30} n={len(p):>4}  >400: {np.mean(p > 400):.3f}  >500: {np.mean(p > 500):.3f}  "
        f">800: {np.mean(p > 800):.3f}  >1000: {np.mean(p > 1000):.3f}  >1.3x30d: {np.mean(rel > 1.3):.3f}  "
        f">1.5x30d: {np.mean(rel > 1.5):.3f}"
    )
# persistence: P(price_t+7 > thr | price_t > thr)
for thr in (400, 500, 800):
    above = price > thr
    nxt = above.shift(-7)
    both = (above & nxt.fillna(False).astype(bool)).sum()
    print(f"persistence 7d at {thr}: P(above in 7d | above now) = {both / max(above.sum(), 1):.2f}, P(above in 7d | below now) = {((~above) & nxt.fillna(False).astype(bool)).sum() / max((~above).sum(), 1):.3f}")
