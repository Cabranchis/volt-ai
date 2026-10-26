"""Build the sample business report (PDF, Spanish) from the web fixtures.

Run from the repository root:

    uv run --no-project --with reportlab --with matplotlib python tools/build_sample_report.py

Reads web/src/lib/data/fixtures/ (export them first with tools/export_fixtures.py) and writes
web/public/informe-ejemplo-voltia.pdf. Every figure comes from the fixtures; the text only frames
them. The probability of a price spike reads the forecast's own P10, P50 and P90 as a log-normal,
the same rule as web/src/lib/spikes.ts.
"""

from __future__ import annotations

import io
import json
import math
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "web" / "src" / "lib" / "data" / "fixtures"
OUT = ROOT / "web" / "public" / "informe-ejemplo-voltia.pdf"
SITE = "https://voltia-xi-five.vercel.app/es"
CONTACT = "miguelangel.14130@gmail.com"

INK = colors.HexColor("#1b1b1a")
MUTED = colors.HexColor("#5b5a56")
LINE = colors.HexColor("#dedcd5")
SOFT = colors.HexColor("#f4f3ef")
ACCENT = colors.HexColor("#b97400")
DEMAND = "#6250d6"
PRICE = "#eb6834"
WATER = "#2a78d6"

MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]
Z80 = 1.2815515655446004  # the 90th percentile of a standard normal


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def num(value: float, decimals: int = 0) -> str:
    """Spanish format: thousands with a dot, decimals with a comma."""
    text = f"{abs(value):,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"-{text}" if value < 0 else text


def pct(value: float, decimals: int = 0) -> str:
    return f"{num(value * 100, decimals)} %"


def day_label(iso: str, year: bool = True) -> str:
    d = date.fromisoformat(iso)
    base = f"{d.day} {MONTHS[d.month - 1]}"
    return f"{base} {d.year}" if year else base


def normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def prob_above(p10: float, p50: float, p90: float, threshold: float) -> float:
    """P(price > threshold), reading P10, P50 and P90 as a log-normal."""
    sigma = (math.log(p90) - math.log(p10)) / (2 * Z80)
    if sigma <= 0:
        return 1.0 if p50 > threshold else 0.0
    return 1 - normal_cdf((math.log(threshold) - math.log(p50)) / sigma)


def last_valid(values: list[float | None]) -> int:
    return max(i for i, v in enumerate(values) if v is not None)


def forecast_chart(dates, values, points, color, ylabel, scale, hline=None) -> io.BytesIO:
    history_days = 75
    last = last_valid(values)
    hist_x = list(range(history_days))
    hist_y = [values[last - history_days + 1 + i] / scale for i in hist_x]
    hist_dates = dates[last - history_days + 1 : last + 1]
    fc_days = [p["day"] for p in points]
    # place forecast days on the same axis as the history by calendar distance
    start = date.fromisoformat(hist_dates[0])
    fx = [(date.fromisoformat(d) - start).days for d in fc_days]
    fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=200)
    ax.plot(hist_x, hist_y, color=color, linewidth=1.4, label="Liquidado")
    ax.fill_between(fx, [p["p10"] / scale for p in points], [p["p90"] / scale for p in points], color=color, alpha=0.18, linewidth=0, label="Rango P10 a P90")
    ax.plot(fx, [p["p50"] / scale for p in points], color=color, linewidth=1.6, linestyle=(0, (4, 2)), label="Pronóstico (P50)")
    if hline is not None:
        ax.axhline(hline, color="#5b5a56", linewidth=0.8, linestyle=":")
        ax.text(0, hline, f" {num(hline)}", va="bottom", fontsize=7, color="#5b5a56")
    ticks = [i for i in range(0, max(fx) + 1, 14)]
    labels = [day_label((start.fromordinal(start.toordinal() + i)).isoformat(), year=False) for i in ticks]
    ax.set_xticks(ticks, labels, fontsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_ylabel(ylabel, fontsize=7)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#dedcd5")
    ax.grid(axis="y", color="#e8e6e0", linewidth=0.6)
    ax.legend(fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def region_table(regional) -> list[list[str]]:
    by_region: dict[str, list[float | None]] = {}
    for r in regional["reservoirs"]:
        if r["capacityKwh"] <= 0:
            continue
        agg = by_region.setdefault(r["region"], [0.0, 0.0, 0.0])
        agg[0] += r["volumeKwh"]
        agg[1] += r["capacityKwh"]
        # one reservoir without last week's value leaves the whole change unknown
        agg[2] = None if agg[2] is None or r.get("weekAgoKwh") is None else agg[2] + r["weekAgoKwh"]
    names = {"CARIBE": "Caribe", "ANTIOQUIA": "Antioquia", "CALDAS": "Caldas", "CENTRO": "Centro", "ORIENTE": "Oriente", "VALLE": "Valle"}
    rows = [["Región", "Nivel", "Cambio en 7 días", "Capacidad (GWh)"]]
    total: list[float | None] = [0.0, 0.0, 0.0]
    change = lambda volume, capacity, week: "–" if week is None else f"{num((volume - week) / capacity * 100, 1)} pt"  # noqa: E731
    for region, (volume, capacity, week) in sorted(by_region.items(), key=lambda kv: -(kv[1][1] or 0)):
        total = [total[0] + volume, total[1] + capacity, None if total[2] is None or week is None else total[2] + week]
        rows.append([names.get(region, region), pct(volume / capacity, 1), change(volume, capacity, week), num(capacity / 1e6)])
    rows.append(["Todo el país", pct(total[0] / total[1], 1), change(total[0], total[1], total[2]), num(total[1] / 1e6)])
    return rows


def main() -> None:
    series = load("series.json")
    dates = series["dates"]
    data = series["series"]
    forecasts = load("forecasts.json")
    regional = load("regional.json")
    run = load("model-run.json")

    demand_fc = forecasts["demand_kwh"]["points"]
    price_fc = forecasts["price_mean_cop_kwh"]["points"]
    d_last = last_valid(data["demand_kwh"])
    p_last = last_valid(data["price_mean_cop_kwh"])
    d_day, p_day = dates[d_last], dates[p_last]
    issued = datetime.fromisoformat(forecasts["demand_kwh"]["trainedAt"]).date().isoformat()
    recent = [v for v in data["price_mean_cop_kwh"][: p_last + 1] if v is not None][-30:]
    mean30 = sum(recent) / len(recent) if len(recent) >= 20 else None

    # The forecast starts on the last day with a complete price, so its first days are already over
    # when it is issued. The summary looks at the 7 days from the issue date on.
    week_d = [p for p in demand_fc if p["day"] >= issued][:7]
    week_p = [p for p in price_fc if p["day"] >= issued][:7]
    range_d = f"{day_label(week_d[0]['day'], False)} a {day_label(week_d[-1]['day'], False)}"
    week_range = f"{day_label(week_p[0]['day'], False)} a {day_label(week_p[-1]['day'], False)}"
    d_mean = sum(p["p50"] for p in week_d) / len(week_d) / 1e6
    p_mean = sum(p["p50"] for p in week_p) / len(week_p)
    p_lo = min(p["p10"] for p in week_p)
    p_hi = max(p["p90"] for p in week_p)
    prob500 = [prob_above(p["p10"], p["p50"], p["p90"], 500) for p in week_p]
    prob13 = (
        [prob_above(p["p10"], p["p50"], p["p90"], 1.3 * mean30) for p in week_p] if mean30 is not None else []
    )
    price_cov = [o["model_coverage"] for o in run["metrics"]["targets"]["price_mean_cop_kwh"].get("by_origin", [])]
    low_cov = f"{min(price_cov) * 100:.0f} %" if price_cov else None
    over_days = [p["day"] for p in price_fc if p["day"] < issued]
    over_text = " y ".join(day_label(d, False) for d in over_days)
    levels = region_table(regional)
    country = levels[-1]

    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK)
    small = ParagraphStyle("small", parent=base, fontSize=7.5, leading=10, textColor=MUTED)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=19, leading=22, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=14, spaceBefore=10, spaceAfter=4)
    bullet = ParagraphStyle("bullet", parent=base, leftIndent=11, bulletIndent=0, spaceAfter=2)

    def table(rows, widths, right_from=1):
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                    ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                    ("ALIGN", (right_from, 0), (-1, -1), "RIGHT"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ]
            )
        )
        return t

    story: list = [
        Paragraph("VoltIA · Informe de ejemplo", h1),
        Paragraph(
            f"Mercado eléctrico colombiano. Pronóstico emitido el {day_label(issued)}; en los datos públicos de XM, precio completo hasta el {day_label(p_day)} y demanda completa hasta el {day_label(d_day)}. "
            "Ejemplo con datos reales: así se vería un resumen semanal.",
            small,
        ),
        Spacer(1, 6),
        Paragraph("Lo esencial", h2),
        Paragraph(
            f"<b>Demanda.</b> El último día completo, {day_label(d_day, False)}, fue de {num(data['demand_kwh'][d_last] / 1e6, 1)} GWh. "
            f"Para los 7 días desde la emisión ({range_d}) el pronóstico central es de {num(d_mean, 1)} GWh al día.",
            bullet,
            bulletText="•",
        ),
        Paragraph(
            f"<b>Precio de bolsa.</b> El último día con precio completo, {day_label(p_day, False)}, el precio medio fue de {num(data['price_mean_cop_kwh'][p_last])} COP/kWh. "
            f"Para los 7 días desde la emisión ({week_range}) el pronóstico central es de {num(p_mean)} COP/kWh; los rangos P10 a P90 de cada día van de {num(p_lo)} a {num(p_hi)}.",
            bullet,
            bulletText="•",
        ),
        Paragraph(
            f"<b>Picos.</b> La probabilidad de que el precio medio diario supere 500 COP/kWh va de {pct(min(prob500))} a {pct(max(prob500))} en esa semana"
            + (
                f"; la de que suba 1,3 veces su media de 30 días ({num(1.3 * mean30)} COP/kWh) va de {pct(min(prob13))} a {pct(max(prob13))}."
                if prob13
                else "."
            ),
            bullet,
            bulletText="•",
        ),
        Paragraph(
            f"<b>Embalses.</b> El nivel agregado es de {country[1]} de la capacidad, con un cambio de {country[2]} frente a hace 7 días.",
            bullet,
            bulletText="•",
        ),
        Paragraph("Demanda de energía del sistema, pronóstico a 30 días", h2),
        Image(forecast_chart(dates, data["demand_kwh"], demand_fc, DEMAND, "GWh por día", 1e6), width=17 * cm, height=5.9 * cm),
        Paragraph("Precio de bolsa, pronóstico a 14 días", h2),
        Image(forecast_chart(dates, data["price_mean_cop_kwh"], price_fc, PRICE, "COP/kWh", 1, hline=500), width=17 * cm, height=5.9 * cm),
        Paragraph(
            "El rango P10 a P90 está calibrado: en promedio sobre las fechas pasadas, cerca del 80 % de los resultados cayó dentro"
            + (f" (en cambios bruscos de régimen llegó a bajar hasta cerca de {low_cov} en una fecha)" if low_cov else "")
            + ". Un ancho grande significa más incertidumbre, no un error. "
            + (f"Los días {over_text} ya habían pasado al emitir el informe, pero XM aún no publicaba su precio completo: el pronóstico los cubre en el gráfico." if over_text else ""),
            small,
        ),
    ]

    spike_rows = [["Día", "Precio central", "Rango P10 a P90", "Prob. > 500 COP/kWh", *([f"Prob. > 1,3 × media 30 d ({num(1.3 * mean30)})"] if mean30 is not None else [])]]
    for i, p in enumerate(week_p):
        spike_rows.append(
            [
                day_label(p["day"], False),
                num(p["p50"]),
                f"{num(p['p10'])} a {num(p['p90'])}",
                pct(prob500[i]),
                *([pct(prob13[i])] if prob13 else []),
            ]
        )

    bucket_rows = [["Pronóstico", "VoltIA", "Estacional ingenuo", "ETS"]]
    metrics = run["metrics"]["targets"]
    d = metrics["demand_kwh"]["overall"]
    bucket_rows.append(["Demanda, 1 a 30 días", f"{num(d['model']['mape'], 1)} %", f"{num(d['seasonal_naive']['mape'], 1)} %", f"{num(d['ets']['mape'], 1)} %"])
    for label, b in sorted(metrics["price_mean_cop_kwh"]["by_bucket"].items(), key=lambda kv: int(kv[0].split("-")[0])):
        bucket_rows.append([f"Precio de bolsa, {label.replace('-', ' a ')} días", f"{num(b['model']['mape'], 1)} %", f"{num(b['seasonal_naive']['mape'], 1)} %", f"{num(b['ets']['mape'], 1)} %"])
    n = metrics["demand_kwh"]["n_origins"]

    story += [
        KeepTogether(
            [
                Paragraph(f"Probabilidad de picos de precio, {week_range}", h2),
                table(spike_rows, [2.2 * cm, 2.8 * cm, 3.4 * cm, 3.6 * cm, 5.0 * cm]),
                Paragraph(
                    "La probabilidad se lee de las propias bandas del pronóstico (P10, P50 y P90) como una distribución log-normal. Para 800 COP/kWh la lectura no supera a una regla simple, por eso no se ofrece. ",
                    small,
                ),
            ]
        ),
        Paragraph("Hidrología por región", h2),
        table(levels, [4.2 * cm, 3 * cm, 4.4 * cm, 4.4 * cm]),
        Paragraph("Las regiones son las de XM y siguen las cuencas de los ríos, no los límites de los departamentos.", small),
        KeepTogether(
            [
                Paragraph("Qué tan bien ha pronosticado", h2),
                table(bucket_rows, [6 * cm, 3 * cm, 4 * cm, 3 * cm]),
                Paragraph(
                    f"Error porcentual medio en {n} fechas pasadas que el modelo no había visto. Menor es mejor. Los días se cuentan desde el último día con precio completo en los datos públicos de XM, unos tres días antes de emitir el pronóstico. "
                    "El precio supera a las dos referencias en los primeros días y queda a la par con ETS pasada una semana. "
                    "El historial en vivo, con cada pronóstico guardado tal como se emitió, antes de que los datos públicos de XM muestren el resultado, está en la página de Modelos.",
                    small,
                ),
            ]
        ),
        Paragraph("Qué no hace", h2),
        Paragraph("No anticipa racionamientos, decisiones regulatorias ni hechos sin precedente en la historia.", bullet, bulletText="•"),
        Paragraph("Los datos públicos de XM traen el precio diario completo con unos tres días de retraso (según lo observado): el pronóstico más nuevo parte de datos de hace tres días.", bullet, bulletText="•"),
        Paragraph("Pasada una semana el precio no es mejor que un pronóstico estadístico simple: conviene leer su rango más que el valor central.", bullet, bulletText="•"),
        Paragraph("Apoya decisiones. No es una recomendación para comprar, vender ni cubrir energía.", bullet, bulletText="•"),
        Spacer(1, 8),
        Paragraph(
            f"Fuentes: XM (demanda, precio, embalses y aportes), Open-Meteo y NOAA. Sitio y método: {SITE}/models · Contacto: {CONTACT}",
            small,
        ),
    ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2.2)
        canvas.line(1.8 * cm, A4[1] - 1.2 * cm, 4.2 * cm, A4[1] - 1.2 * cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.8 * cm, 1.1 * cm, "VoltIA · informe de ejemplo con datos reales · no es una recomendación de inversión")
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.1 * cm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.7 * cm,
        bottomMargin=1.7 * cm,
        title="VoltIA, informe de ejemplo",
        author="Miguel Angel",
        subject="Pronóstico de demanda y precio de bolsa de la electricidad en Colombia",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
