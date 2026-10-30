"""Dependency-free SVG price chart.

Rendered on the server so the trend view still works when JavaScript is
blocked, on a slow phone, or in an SMS/WhatsApp-style embed. The chart is
deliberately honest: the projection is dashed, the uncertainty band is drawn,
and a low-confidence forecast says so inside the image.
"""

from __future__ import annotations

from markupsafe import Markup


def _scale(values: list[float], lo: float, hi: float, top: float, bottom: float) -> list[float]:
    span = (hi - lo) or 1.0
    return [bottom - (v - lo) / span * (bottom - top) for v in values]


def _fmt(v: float) -> str:
    return f"{v:.1f}"


def price_chart_svg(
    chart: dict,
    *,
    width: int = 720,
    height: int = 260,
    unit: str = "UGX per bunch",
    title: str = "",
) -> Markup:
    history = chart.get("history") or []
    proj = chart.get("projection") or []
    if not history:
        return Markup(
            f'<svg viewBox="0 0 {width} {height}" role="img"><text x="12" y="30" class="c-note">No price history yet for this market.</text></svg>'
        )

    pad_l, pad_r, pad_t, pad_b = 54, 12, 26, 34
    plot_top, plot_bottom = pad_t, height - pad_b
    all_vals = [h["price"] for h in history] + [p["high"] for p in proj] + [p["low"] for p in proj]
    lo, hi = min(all_vals) * 0.96, max(all_vals) * 1.04

    n = len(history) + len(proj)
    xs = [pad_l + (i / max(n - 1, 1)) * (width - pad_l - pad_r) for i in range(n)]
    hist_ys = _scale([h["price"] for h in history], lo, hi, plot_top, plot_bottom)
    proj_ys = _scale([p["predicted"] for p in proj], lo, hi, plot_top, plot_bottom)
    hi_ys = _scale([p["high"] for p in proj], lo, hi, plot_top, plot_bottom)
    lo_ys = _scale([p["low"] for p in proj], lo, hi, plot_top, plot_bottom)
    ma_ys = _scale([m["price"] for m in (chart.get("moving_average") or [])], lo, hi, plot_top, plot_bottom)

    hist_pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in zip(xs[: len(history)], hist_ys, strict=True))
    offset = len(history) - 1
    proj_pts = " ".join(f"{_fmt(xs[offset + i])},{_fmt(y)}" for i, y in enumerate(proj_ys)) if proj else ""
    band_pts = ""
    anchor_pt = f"{_fmt(xs[offset])},{_fmt(hist_ys[-1])}"
    if proj:
        upper = [f"{_fmt(xs[offset + i])},{_fmt(y)}" for i, y in enumerate(hi_ys)]
        lower = [f"{_fmt(xs[offset + i])},{_fmt(y)}" for i, y in reversed(list(enumerate(lo_ys)))]
        band_pts = " ".join([anchor_pt, *upper, *lower, anchor_pt])
    ma_pts = " ".join(f"{_fmt(xs[i])},{_fmt(y)}" for i, y in enumerate(ma_ys))

    # y-axis ticks
    ticks = []
    for frac in (0.0, 0.5, 1.0):
        val = lo + frac * (hi - lo)
        y = plot_bottom - frac * (plot_bottom - plot_top)
        ticks.append(
            f'<line x1="{pad_l}" y1="{_fmt(y)}" x2="{width - pad_r}" y2="{_fmt(y)}" class="c-grid"/>'
            f'<text x="4" y="{_fmt(y + 4)}" class="c-tick">{int(val):,}</text>'
        )
    # x labels: first, middle, last
    labels = []
    picks = {0, len(history) // 2, len(history) - 1, n - 1}
    idxs = [i for i in picks if 0 <= i < n]
    for i in sorted(idxs):
        day = (history + [{"date": p["date"]} for p in proj])[i]["date"]
        labels.append(
            f'<text x="{_fmt(xs[i])}" y="{height - 10}" class="c-tick" text-anchor="middle">{day}</text>'
        )

    conf = chart.get("confidence", "low")
    band = f'<polygon points="{band_pts}" class="c-band-{conf}"/>' if band_pts else ""
    proj_line = f'<polyline points="{proj_pts}" class="c-proj"/>' if proj_pts else ""
    conf_note = {
        "high": "projection confidence: high",
        "medium": "projection confidence: medium",
        "low": "projection confidence: LOW - treat as a signal, not a plan",
    }.get(conf, "")
    synth = "sample data" if chart.get("data_is_synthetic") else "field data"

    return Markup(
        f"""<svg viewBox="0 0 {width} {height}" class="c-chart" role="img"
  aria-label="Matooke price history and indicative projection, {unit}, {synth}, {conf_note}">
  <title>{title or "Price history and indicative projection"} ({unit}, {synth})</title>
  {"".join(ticks)}
  {band}
  <polyline points="{ma_pts}" class="c-ma"/>
  <polyline points="{hist_pts}" class="c-hist"/>
  {proj_line}
  <line x1="{_fmt(xs[offset])}" y1="{plot_top}" x2="{_fmt(xs[offset])}" y2="{plot_bottom}" class="c-now"/>
  {"".join(labels)}
  <text x="{pad_l}" y="16" class="c-note">{unit} - {synth}</text>
  <text x="{width - pad_r}" y="16" class="c-note c-note-{"low" if conf == "low" else "ok"}" text-anchor="end">{conf_note}</text>
</svg>"""
    )
