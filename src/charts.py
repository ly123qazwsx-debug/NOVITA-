"""一张综合看板：概览 KPI + 分项趋势（对比上月）+ 环比明细。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch

from .data_fetcher import COST_COLUMNS
from .metrics import CATEGORY_LABELS, ReportMetrics
from .report import _fmt_money, _fmt_rate

BG = "#F4F6F8"
CARD_BG = "#FFFFFF"
TEXT = "#1F2329"
MUTED = "#646A73"
GRID = "#E5E6EB"
UP = "#D83931"
DOWN = "#2EA121"
PREV = "#9AA0A6"
ACCENT = "#3370FF"

COLORS = {
    "llm": "#3370FF",
    "sd": "#F58518",
    "gpu_ondemand": "#00B42A",
    "gpu_storage": "#14C9C9",
    "gpu_fixed": "#86909C",
    "total_with_fixed": "#1D2129",
    "total_ondemand": "#3370FF",
}

TREND_SERIES = COST_COLUMNS + ["total_with_fixed", "total_ondemand"]
TREND_TITLES = {
    **CATEGORY_LABELS,
    "total_with_fixed": "日消耗-含固定GPU",
    "total_ondemand": "日消耗-按需计费",
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
    if rate != rate:
        return ""
    if rate > 0:
        return "▲"
    if rate < 0:
        return "▼"
    return "–"


KPI_SHORT = {
    "month_total": "当月总消耗",
    "daily_with_fixed": "日消耗 · 含固定GPU",
    "daily_ondemand": "日消耗 · 按需计费",
    "forecast": "预计当月总消耗",
}


def _draw_kpi(ax, item: dict, symbol: str) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    card = FancyBboxPatch(
        (0.02, 0.06),
        0.96,
        0.88,
        boxstyle="round,pad=0.02,rounding_size=0.04",
        facecolor=CARD_BG,
        edgecolor="#DEE0E3",
        linewidth=1,
        transform=ax.transAxes,
        clip_on=False,
    )
    ax.add_patch(card)
    ax.text(
        0.08,
        0.78,
        KPI_SHORT.get(item.get("key"), item["label"]),
        fontsize=8.5,
        color=MUTED,
        va="center",
        transform=ax.transAxes,
    )
    ax.text(
        0.08,
        0.48,
        _fmt_money(item["current"], symbol),
        fontsize=15,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=ax.transAxes,
    )
    rate = item["rate"]
    ax.text(
        0.08,
        0.22,
        f"{_rate_arrow(rate)} {_fmt_rate(rate)}   上月 {_fmt_money(item['previous'], symbol)}",
        fontsize=8,
        color=_rate_color(rate),
        va="center",
        transform=ax.transAxes,
    )


def _align_by_day(df) -> tuple[list[int], dict[str, list[float]]]:
    if df is None or df.empty:
        return [], {}
    work = df.copy()
    work["day"] = work["date"].map(lambda d: d.day)
    work = work.drop_duplicates("day").sort_values("day")
    series = {col: work[col].tolist() for col in TREND_SERIES if col in work.columns}
    return work["day"].tolist(), series


def _plot_small_trend(ax, title: str, color: str, days_cur, vals_cur, days_prev, vals_prev, rate: float) -> None:
    ax.set_facecolor(CARD_BG)
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(labelsize=7, colors=MUTED)

    if days_prev and vals_prev:
        ax.plot(days_prev, vals_prev, color=PREV, linestyle="--", linewidth=1.4, label="上月同期")
    if days_cur and vals_cur:
        ax.plot(days_cur, vals_cur, color=color, linewidth=2.0, marker="o", markersize=3.2, label="当月")
        ax.fill_between(days_cur, vals_cur, color=color, alpha=0.08)

    ax.set_title(f"{title}  {_rate_arrow(rate)}{_fmt_rate(rate)}", fontsize=9, color=_rate_color(rate), pad=6, loc="left")
    ax.set_xlabel("日", fontsize=7, color=MUTED)
    if days_cur:
        ax.set_xlim(min(days_cur) - 0.3, max(days_cur) + 0.3)


def _plot_mom_bars(ax, metrics: ReportMetrics) -> None:
    """用环比率看增长（各分项量级差很大，绝对值柱状图会把按需项压扁）。"""
    ax.set_facecolor(CARD_BG)
    labels = [CATEGORY_LABELS[k] for k in COST_COLUMNS]
    rates = [metrics.mom_changes[k]["rate"] for k in COST_COLUMNS]
    plot_rates = [0.0 if r != r else r for r in rates]
    colors = [_rate_color(r) if r == r else MUTED for r in rates]

    y = np.arange(len(labels))
    ax.barh(y, plot_rates, color=colors, height=0.55, zorder=2)
    ax.axvline(0, color=TEXT, linewidth=0.8, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.7, zorder=0)
    ax.set_xlabel("环比率 (%)", fontsize=8, color=MUTED)
    ax.set_title("分项环比变化（红涨绿跌，便于跨分项对比）", fontsize=10, color=TEXT, loc="left", pad=8)
    ax.tick_params(labelsize=7, colors=MUTED)

    span = max(abs(v) for v in plot_rates) if any(plot_rates) else 1
    ax.set_xlim(-span * 1.35, span * 1.45)
    for i, (rate, key) in enumerate(zip(rates, COST_COLUMNS)):
        item = metrics.mom_changes[key]
        x = 0 if rate != rate else rate
        ax.text(
            x + (span * 0.04 if x >= 0 else -span * 0.04),
            i,
            f"{_fmt_rate(rate)}  ({_fmt_money(item['current'], metrics.currency_symbol)})",
            va="center",
            ha="left" if x >= 0 else "right",
            fontsize=7.5,
            color=_rate_color(rate),
        )


def _plot_detail_table(ax, metrics: ReportMetrics) -> None:
    ax.axis("off")
    ax.set_facecolor(BG)
    sym = metrics.currency_symbol
    rows = list(metrics.overview) + [
        {"label": CATEGORY_LABELS[k], **metrics.mom_changes[k]} for k in COST_COLUMNS
    ]
    cell_text = []
    cell_colors = []
    for i, item in enumerate(rows):
        rate = item["rate"]
        rate_bg = "#FDECEC" if rate == rate and rate > 0 else ("#E8F6E9" if rate == rate and rate < 0 else "#FFFFFF")
        # 概览与分项之间加一点视觉分组：前 4 行浅底
        base = "#F7F8FA" if i < 4 else "#FFFFFF"
        cell_text.append(
            [
                item["label"],
                _fmt_money(item["current"], sym),
                _fmt_money(item["previous"], sym),
                _fmt_money(item["change"], sym),
                _fmt_rate(rate),
            ]
        )
        cell_colors.append([base, base, base, rate_bg, rate_bg])

    table = ax.table(
        cellText=cell_text,
        colLabels=["指标 / 分项", "当月数据", "上月同期", "环比", "环比率"],
        loc="center",
        cellLoc="center",
        colColours=["#E8F3FF"] * 5,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1, 1.55)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#E5E6EB")
        cell.set_linewidth(0.6)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
        elif col == 0:
            cell.set_text_props(ha="left")
            cell.PAD = 0.08
        elif col == 4 and row > 0:
            rate = rows[row - 1]["rate"]
            cell.set_text_props(color=_rate_color(rate), fontweight="bold")
    ax.set_title("环比明细（上 4 行为汇总指标，下 5 行为分项）", fontsize=10, color=TEXT, loc="left", pad=10)


def plot_dashboard(metrics: ReportMetrics, output_dir: Path) -> Path:
    """生成一张包含全部关键信息的综合看板。"""
    _setup_font()
    output_dir.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(18.5, 13.2), facecolor=BG)
    outer = GridSpec(
        4,
        1,
        height_ratios=[1.05, 2.15, 2.25, 2.55],
        hspace=0.28,
        top=0.91,
        bottom=0.03,
        left=0.045,
        right=0.975,
    )

    period = metrics.current_period
    fig.suptitle(
        f"NOVITA 成本日报  {metrics.report_date}    单位 {metrics.currency}",
        fontsize=18,
        fontweight="bold",
        color=TEXT,
        x=0.045,
        ha="left",
        y=0.975,
    )
    fig.text(
        0.045,
        0.935,
        f"统计区间 {period.start.month}.{period.start.day}–{period.end.month}.{period.end.day}"
        f"（已过 {period.days} 天）  ｜  实线=当月  虚线=上月同期  ｜  红涨绿跌",
        fontsize=10,
        color=MUTED,
        ha="left",
    )

    gs_kpi = outer[0].subgridspec(1, 4, wspace=0.06)
    for i, item in enumerate(metrics.overview):
        ax = fig.add_subplot(gs_kpi[0, i])
        _draw_kpi(ax, item, metrics.currency_symbol)

    days_cur, cur_series = _align_by_day(metrics.trend_df)
    days_prev, prev_series = _align_by_day(metrics.prev_trend_df)

    gs_trend = outer[1].subgridspec(1, 5, wspace=0.18)
    for i, col in enumerate(COST_COLUMNS):
        ax = fig.add_subplot(gs_trend[0, i])
        rate = metrics.mom_changes[col]["rate"]
        _plot_small_trend(
            ax,
            CATEGORY_LABELS[col],
            COLORS[col],
            days_cur,
            cur_series.get(col, []),
            days_prev,
            prev_series.get(col, []),
            rate,
        )
        if i == 0:
            ax.legend(frameon=False, fontsize=7, loc="upper left")

    gs_mid = outer[2].subgridspec(1, 2, width_ratios=[1.15, 1], wspace=0.16)
    ax_total = fig.add_subplot(gs_mid[0, 0])
    ax_total.set_facecolor(CARD_BG)
    if days_prev:
        ax_total.plot(
            days_prev,
            prev_series.get("total_with_fixed", []),
            color=PREV,
            linestyle="--",
            linewidth=1.4,
            label="上月总消耗",
        )
        ax_total.plot(
            days_prev,
            prev_series.get("total_ondemand", []),
            color="#C9CDD4",
            linestyle="--",
            linewidth=1.3,
            label="上月按需",
        )
    if days_cur:
        ax_total.plot(
            days_cur,
            cur_series.get("total_with_fixed", []),
            color=COLORS["total_with_fixed"],
            linewidth=2.2,
            marker="o",
            markersize=3.5,
            label="当月总消耗（含固定）",
        )
        ax_total.plot(
            days_cur,
            cur_series.get("total_ondemand", []),
            color=COLORS["total_ondemand"],
            linewidth=2.2,
            marker="s",
            markersize=3.5,
            label="当月按需计费",
        )
    ax_total.set_title("每日总消耗变化（含固定 vs 按需）", fontsize=10, color=TEXT, loc="left", pad=8)
    ax_total.set_xlabel("日", fontsize=8, color=MUTED)
    ax_total.set_ylabel(f"金额 ({metrics.currency})", fontsize=8, color=MUTED)
    ax_total.grid(axis="y", color=GRID, linewidth=0.7)
    ax_total.spines["top"].set_visible(False)
    ax_total.spines["right"].set_visible(False)
    ax_total.legend(frameon=False, fontsize=7.5, ncol=2, loc="upper left")
    ax_total.tick_params(labelsize=7, colors=MUTED)

    ax_bars = fig.add_subplot(gs_mid[0, 1])
    _plot_mom_bars(ax_bars, metrics)

    ax_table = fig.add_subplot(outer[3])
    _plot_detail_table(ax_table, metrics)

    path = output_dir / "novita_dashboard.png"
    fig.savefig(path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def generate_all_charts(metrics: ReportMetrics, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dashboard = plot_dashboard(metrics, output_dir)
    return {"dashboard": dashboard}
