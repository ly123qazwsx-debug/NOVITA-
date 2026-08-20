"""三板块看板：成本概览、分项环比明细、五项日度趋势。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch

from .data_fetcher import COST_COLUMNS
from .metrics import CATEGORY_LABELS, ReportMetrics
from .report import _fmt_money

BG = "#F3F6F5"
CARD = "#FFFFFF"
TEXT = "#1B2B28"
MUTED = "#5E6F6B"
GRID = "#E3EBE8"
LINE = "#C9D6D2"
UP = "#C45656"
DOWN = "#2B8A3E"
TEAL = "#0B6E62"
MINT = "#A8D4C8"
AUG = "#0B6E62"
JUL = "#A8D4C8"
BAR_FIXED = "#0D6E62"

LINE_COLORS = {
    "llm": "#1A7F8E",
    "sd": "#D4A017",
    "gpu_ondemand": "#E07A3D",
    "gpu_storage": "#4C9BD6",
}


def _setup_font() -> None:
    from matplotlib import font_manager

    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Noto Sans SC",
        "Source Han Sans SC",
        "WenQuanYi Zen Hei",
        "SimHei",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in candidates if name in available), "DejaVu Sans")
    plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _rate_color(rate: float) -> str:
    if rate != rate or rate == 0:
        return MUTED
    return UP if rate > 0 else DOWN


def _rate_arrow(rate: float) -> str:
    if rate != rate or rate == 0:
        return "–"
    return "▲" if rate > 0 else "▼"


def _fmt_pct(rate: float) -> str:
    if rate != rate:
        return "N/A"
    return f"{int(round(rate))}%"


def _style_ax(ax) -> None:
    ax.set_facecolor(CARD)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)
    ax.tick_params(labelsize=9, colors=MUTED)


def _section_banner(ax, index: str, title: str) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(
        FancyBboxPatch(
            (0.0, 0.18),
            0.014,
            0.64,
            boxstyle="round,pad=0.002,rounding_size=0.004",
            facecolor=TEAL,
            edgecolor="none",
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    ax.text(0.028, 0.5, f"{index}  {title}", fontsize=14, fontweight="bold", color=TEAL, va="center", transform=ax.transAxes)


def _draw_kpi(ax, item: dict, symbol: str, compare_hint: str) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(
        FancyBboxPatch(
            (0.02, 0.06),
            0.96,
            0.88,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            facecolor=CARD,
            edgecolor="#D7E3DF",
            linewidth=1.1,
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    ax.text(0.08, 0.80, item["label"], fontsize=9.4, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(
        0.08,
        0.50,
        _fmt_money(item["current"], symbol),
        fontsize=18,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=ax.transAxes,
    )
    rate = item["rate"]
    change = item["change"]
    ax.text(
        0.08,
        0.22,
        f"{_rate_arrow(rate)} {_fmt_pct(rate)}   环比 {_fmt_money(change, symbol)}",
        fontsize=8.6,
        color=_rate_color(rate),
        va="center",
        transform=ax.transAxes,
    )
    ax.text(
        0.08,
        0.08,
        f"{compare_hint} {_fmt_money(item['previous'], symbol)}",
        fontsize=7.8,
        color=MUTED,
        va="center",
        transform=ax.transAxes,
    )


def _plot_total_compare(ax, metrics: ReportMetrics) -> None:
    _style_ax(ax)
    cur = metrics.current_period.totals["total_with_fixed"]
    prev = metrics.previous_period.totals["total_with_fixed"]
    forecast = metrics.forecast_month_total
    prev_full = metrics.prev_month_full_total
    cur_m = metrics.current_period.end.month
    prev_m = metrics.previous_period.end.month

    xs = np.array([0, 1])
    width = 0.34
    bars_aug = ax.bar(xs - width / 2, [cur, forecast], width, color=AUG, label=f"{cur_m}月", zorder=2)
    bars_jul = ax.bar(xs + width / 2, [prev, prev_full], width, color=JUL, label=f"{prev_m}月", zorder=2)
    ax.set_xticks(xs)
    ax.set_xticklabels(["累计消耗（1日～昨天）", "预计全月 vs 上月全月"], fontsize=9.5)
    ax.set_ylabel(f"金额 ({metrics.currency})", fontsize=9, color=MUTED)
    ax.set_title("累计 / 预计对比", fontsize=12, color=TEXT, loc="left", pad=8, fontweight="bold")
    ax.legend(frameon=False, fontsize=9, loc="upper left")

    def _label(bars):
        for bar in bars:
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h,
                f"${h:,.0f}",
                ha="center",
                va="bottom",
                fontsize=8,
                color=TEXT,
            )

    _label(bars_aug)
    _label(bars_jul)
    ymax = max(cur, prev, forecast, prev_full, 1) * 1.18
    ax.set_ylim(0, ymax)


def _plot_daily_compare(ax, metrics: ReportMetrics) -> None:
    _style_ax(ax)
    cur_m = metrics.current_period.end.month
    prev_m = metrics.previous_period.end.month
    labels = ["含固定 GPU", "按需计费"]
    current = [
        metrics.current_period.daily_avg["total_with_fixed"],
        metrics.current_period.daily_avg["total_ondemand"],
    ]
    previous = [
        metrics.previous_period.daily_avg["total_with_fixed"],
        metrics.previous_period.daily_avg["total_ondemand"],
    ]
    x = np.arange(len(labels))
    width = 0.34
    b1 = ax.bar(x - width / 2, current, width, color=AUG, label=f"{cur_m}月日均", zorder=2)
    b2 = ax.bar(x + width / 2, previous, width, color=JUL, label=f"{prev_m}月日均", zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.set_ylabel(f"金额 ({metrics.currency})", fontsize=9, color=MUTED)
    ax.set_title("日均消耗对比", fontsize=12, color=TEXT, loc="left", pad=8, fontweight="bold")
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h,
                f"${h:,.0f}",
                ha="center",
                va="bottom",
                fontsize=8,
                color=TEXT,
            )
    ax.set_ylim(0, max(current + previous + [1]) * 1.22)


def _fmt_day_amt(value: float) -> str:
    if value != value:
        return ""
    return f"{value:,.0f}"


def _plot_dual_axis_trend(ax, metrics: ReportMetrics) -> None:
    df = metrics.trend_df.sort_values("date").copy()
    _style_ax(ax)
    if df.empty:
        ax.set_title("暂无趋势数据", loc="left")
        return

    x = np.arange(len(df))
    labels = [f"{pd_day(d)}" for d in df["date"]]

    mask = df["gpu_fixed"].notna()
    ax.bar(
        x[mask.to_numpy()],
        df.loc[mask, "gpu_fixed"],
        width=0.68,
        color=BAR_FIXED,
        alpha=0.78,
        label="GPU 固定（左轴）",
        zorder=2,
    )
    ax.set_ylabel("GPU 固定 (USD)", fontsize=9.5, color=BAR_FIXED)
    ax.tick_params(axis="y", colors=BAR_FIXED)

    ax2 = ax.twinx()
    ax2.set_facecolor("none")
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color(LINE)
    ax2.grid(False)

    line_specs = [
        ("llm", "LLM", "o", (0, 9)),
        ("sd", "sd", "s", (0, -11)),
        ("gpu_ondemand", "GPU 按需", "^", (5, 4)),
        ("gpu_storage", "GPU 按需存储", "D", (-5, -8)),
    ]
    for key, label, marker, offset in line_specs:
        ax2.plot(
            x,
            df[key],
            color=LINE_COLORS[key],
            linewidth=2.2,
            marker=marker,
            markersize=5.4,
            label=label,
            zorder=3,
        )
        for xi, value in zip(x, df[key]):
            if value != value:
                continue
            ax2.annotate(
                _fmt_day_amt(float(value)),
                (xi, value),
                textcoords="offset points",
                xytext=offset,
                ha="center",
                va="center",
                fontsize=7.0,
                color=LINE_COLORS[key],
                zorder=4,
            )
    ax2.set_ylabel("按需分项 (USD)", fontsize=9.5, color=MUTED)
    ax2.tick_params(axis="y", labelsize=9, colors=MUTED)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.6)
    ax.set_xlim(-0.6, len(x) - 0.4)
    vals = df["gpu_fixed"].dropna()
    ax.set_ylim(0, max(float(vals.max()) * 1.28 if not vals.empty else 0.0, 1))
    ondemand_max = 0.0
    for k, _, _, _ in line_specs:
        series = df[k].dropna()
        if not series.empty:
            ondemand_max = max(ondemand_max, float(series.max()))
    ax2.set_ylim(0, max(ondemand_max * 1.42, 1))

    for xi, value in zip(x[mask.to_numpy()], df.loc[mask, "gpu_fixed"]):
        ax.text(
            xi,
            float(value),
            _fmt_day_amt(float(value)),
            ha="center",
            va="bottom",
            fontsize=7.0,
            color=BAR_FIXED,
            rotation=90,
            zorder=4,
        )

    if "total_with_fixed" in df.columns:
        y_top = ax.get_ylim()[1]
        for xi, value in zip(x, df["total_with_fixed"]):
            if value != value:
                continue
            ax.text(
                xi,
                y_top * 0.99,
                _fmt_day_amt(float(value)),
                ha="center",
                va="top",
                fontsize=7.2,
                color=TEXT,
                fontweight="bold",
                zorder=5,
            )

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(
        h1 + h2,
        l1 + l2,
        frameon=False,
        fontsize=8.4,
        ncol=5,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.02),
        borderaxespad=0,
    )
    ax.text(
        1.0,
        1.02,
        "柱顶为 GPU 固定，折线旁为分项，最上为当日合计",
        fontsize=7.5,
        color=MUTED,
        ha="right",
        va="bottom",
        transform=ax.transAxes,
    )


def _plot_daily_amount_table(ax, metrics: ReportMetrics) -> None:
    """把每天五项 + 当日合计写成表，保证金额可读。"""
    ax.axis("off")
    ax.set_facecolor(BG)
    df = metrics.trend_df.sort_values("date")
    if df.empty:
        ax.text(0.5, 0.5, "暂无日明细", ha="center", va="center")
        return

    headers = ["日期", "LLM", "sd", "GPU按需", "存储", "GPU固定", "当日合计"]
    keys = ["llm", "sd", "gpu_ondemand", "gpu_storage", "gpu_fixed", "total_with_fixed"]
    cell_text = []
    cell_colors = []
    for row in df.itertuples():
        day = getattr(row, "date")
        values = [float(getattr(row, key)) if getattr(row, key) == getattr(row, key) else float("nan") for key in keys]
        cell_text.append(
            [pd_day(day)] + [_fmt_day_amt(v) if v == v else "–" for v in values]
        )
        cell_colors.append(["#FFFFFF"] * 6 + ["#E7F3EE"])

    table = ax.table(
        cellText=cell_text,
        colLabels=headers,
        loc="center",
        cellLoc="center",
        colColours=["#D8EDE6"] * 7,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.4)
    n = max(len(cell_text), 1)
    table.scale(1, min(1.35, 18 / n))
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D5E4DF")
        cell.set_linewidth(0.5)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
        elif col == 0 or col == 6:
            cell.set_text_props(fontweight="bold")
    ax.set_title("每日金额明细（单位 USD）", fontsize=11, color=TEXT, loc="left", pad=6, fontweight="bold")


def pd_day(d) -> str:
    if hasattr(d, "month") and hasattr(d, "day"):
        return f"{int(d.month)}/{int(d.day)}"
    return str(d)


def _plot_mom_compare(ax, metrics: ReportMetrics) -> None:
    """用表底当期 / 上月同期画分项对比，柱顶标环比率（sd 异常已在表底剔除）。"""
    _style_ax(ax)
    cur_m = metrics.current_period.end.month
    prev_m = metrics.previous_period.end.month
    keys = list(COST_COLUMNS)
    labels = [CATEGORY_LABELS[k] for k in keys]
    current = [metrics.mom_changes[k]["current"] for k in keys]
    previous = [metrics.mom_changes[k]["previous"] for k in keys]
    rates = [metrics.mom_changes[k]["rate"] for k in keys]

    x = np.arange(len(keys))
    width = 0.36
    b1 = ax.bar(x - width / 2, current, width, color=AUG, label=f"{cur_m}月当期", zorder=2)
    b2 = ax.bar(x + width / 2, previous, width, color=JUL, label=f"{prev_m}月同期", zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel(f"金额 ({metrics.currency})", fontsize=9, color=MUTED)
    ax.set_title("表底合计对比（当期 vs 上月同期）", fontsize=12, color=TEXT, loc="left", pad=8, fontweight="bold")
    ax.legend(frameon=False, fontsize=9, loc="upper left")

    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h,
                f"${h:,.0f}",
                ha="center",
                va="bottom",
                fontsize=7.4,
                color=TEXT,
            )
    ymax = max(current + previous + [1]) * 1.28
    ax.set_ylim(0, ymax)
    for xi, rate in zip(x, rates):
        ax.text(
            xi,
            ymax * 0.96,
            f"{_rate_arrow(rate)}{_fmt_pct(rate)}",
            ha="center",
            va="top",
            fontsize=9,
            fontweight="bold",
            color=_rate_color(rate),
        )


def _plot_detail_table(ax, metrics: ReportMetrics) -> None:
    ax.axis("off")
    ax.set_facecolor(BG)
    sym = metrics.currency_symbol
    month_total = metrics.current_period.totals["total_with_fixed"]
    rows = [{"key": k, "label": CATEGORY_LABELS[k], **metrics.mom_changes[k]} for k in COST_COLUMNS]
    rows.append({"key": "total", "label": "总消耗", **metrics.mom_changes["total_with_fixed"]})

    cell_text = []
    cell_colors = []
    for item in rows:
        share = item["current"] / month_total * 100 if month_total else 0
        is_total = item["key"] == "total"
        base = "#E7F3EE" if is_total else "#FFFFFF"
        rate = item["rate"]
        rate_bg = "#F8E8E8" if rate == rate and rate > 0 else ("#E7F4EA" if rate == rate and rate < 0 else base)
        cell_text.append(
            [
                item["label"],
                _fmt_money(item["current"], sym),
                _fmt_money(item["previous"], sym),
                _fmt_money(item["change"], sym),
                _fmt_pct(rate) if rate == rate else "N/A",
                f"{share:.0f}%",
            ]
        )
        cell_colors.append([base, base, base, rate_bg, rate_bg, base])

    table = ax.table(
        cellText=cell_text,
        colLabels=["计费项", "当月累计", "上月同期", "环比", "环比率", "占比"],
        loc="center",
        cellLoc="center",
        colColours=["#D8EDE6"] * 6,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.72)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D5E4DF")
        cell.set_linewidth(0.7)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
        elif col == 0:
            cell.set_text_props(ha="left", fontweight="bold" if row == len(rows) else "normal")
            cell.PAD = 0.1
        elif col == 4 and row > 0:
            rate = rows[row - 1]["rate"]
            cell.set_text_props(color=_rate_color(rate), fontweight="bold")
        if row == len(rows):
            cell.set_text_props(fontweight="bold")


def plot_dashboard(
    metrics: ReportMetrics,
    output_dir: Path,
    extra_notes: list[str] | None = None,
) -> Path:
    _setup_font()
    output_dir.mkdir(parents=True, exist_ok=True)

    p = metrics.current_period
    fig = plt.figure(figsize=(18.8, 19.4), facecolor=BG)
    outer = GridSpec(
        9,
        1,
        height_ratios=[0.52, 0.26, 1.02, 1.48, 0.26, 1.72, 0.26, 2.35, 2.05],
        hspace=0.10,
        top=0.96,
        bottom=0.03,
        left=0.045,
        right=0.96,
    )

    title_ax = fig.add_subplot(outer[0])
    title_ax.axis("off")
    title_ax.set_facecolor(BG)
    title_ax.text(
        0.0,
        0.62,
        f"NOVITA {p.end.month}月成本数据概览",
        fontsize=24,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=title_ax.transAxes,
    )
    extra = ""
    if metrics.sheet_actual:
        extra = f"  ｜  表内实际 {_fmt_money(metrics.sheet_actual, metrics.currency_symbol)}"
    title_ax.text(
        0.0,
        0.12,
        f"今天 {metrics.generated_on.month}月{metrics.generated_on.day}日  ｜  "
        f"统计区间 {p.start.month}月{p.start.day}日 – {p.end.month}月{p.end.day}日"
        f"（不含当天，共 {p.days} 天）  ｜  单位 {metrics.currency}  ｜  红涨绿跌"
        f"{extra}",
        fontsize=11,
        color=MUTED,
        va="center",
        transform=title_ax.transAxes,
    )

    _section_banner(fig.add_subplot(outer[1]), "01", "成本概览数据")

    hints = {
        "month_total": "上月同期",
        "daily_with_fixed": "上月同期",
        "daily_ondemand": "上月同期",
        "forecast": "上月全月",
    }
    gs_kpi = outer[2].subgridspec(1, 4, wspace=0.07)
    for i, item in enumerate(metrics.overview):
        ax = fig.add_subplot(gs_kpi[0, i])
        _draw_kpi(ax, item, metrics.currency_symbol, hints.get(item["key"], "上月同期"))

    gs_mid = outer[3].subgridspec(1, 2, wspace=0.16)
    _plot_total_compare(fig.add_subplot(gs_mid[0, 0]), metrics)
    _plot_daily_compare(fig.add_subplot(gs_mid[0, 1]), metrics)

    mom_title = "分项环比明细（上月同期用表底合计，已剔除 sd 7.12-7.14 异常）"
    if getattr(metrics, "mom_source", "daily") != "sheet_footer":
        mom_title = "分项环比明细"
    _section_banner(fig.add_subplot(outer[4]), "02", mom_title)
    gs_mom = outer[5].subgridspec(1, 2, wspace=0.14, width_ratios=[1.12, 1.0])
    _plot_mom_compare(fig.add_subplot(gs_mom[0, 0]), metrics)
    _plot_detail_table(fig.add_subplot(gs_mom[0, 1]), metrics)

    _section_banner(fig.add_subplot(outer[6]), "03", "五项成本日度趋势（每天标注金额）")
    _plot_dual_axis_trend(fig.add_subplot(outer[7]), metrics)
    _plot_daily_amount_table(fig.add_subplot(outer[8]), metrics)

    path = output_dir / "novita_dashboard.png"
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return _flatten_png_to_rgb(path)


def _flatten_png_to_rgb(path: Path) -> Path:
    """飞书上传不认 RGBA 透明 PNG，压成不透明 RGB。"""
    from PIL import Image

    im = Image.open(path)
    if im.mode == "RGB":
        return path
    bg = Image.new("RGB", im.size, (243, 246, 245))
    rgba = im.convert("RGBA")
    bg.paste(rgba, mask=rgba.split()[-1])
    bg.save(path, "PNG", optimize=True)
    return path


def generate_all_charts(
    metrics: ReportMetrics,
    output_dir: Path,
    extra_notes: list[str] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {"dashboard": plot_dashboard(metrics, output_dir, extra_notes)}
