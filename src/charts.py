"""一张清晰的当月成本看板：KPI + 对比柱 + 双轴日趋势 + 分项表。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch

from .data_fetcher import COST_COLUMNS
from .insights import build_highlights
from .metrics import CATEGORY_LABELS, ReportMetrics
from .report import _fmt_money, _fmt_rate

BG = "#F7F8FA"
CARD = "#FFFFFF"
TEXT = "#1F2329"
MUTED = "#646A73"
GRID = "#E8EAED"
LINE = "#D0D3D8"
UP = "#C45656"
DOWN = "#2B8A3E"
AUG = "#1F7A4D"
JUL = "#B7D4C4"
BAR_FIXED = "#2F6F4E"

# 按需项用高对比颜色，避免和固定 GPU 柱挤在一起看不清
LINE_COLORS = {
    "llm": "#1A7F8E",
    "sd": "#D4A017",
    "gpu_ondemand": "#C0392B",
    "gpu_storage": "#3D8B5F",
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


def _style_ax(ax) -> None:
    ax.set_facecolor(CARD)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)
    ax.tick_params(labelsize=9, colors=MUTED)


def _draw_kpi(ax, item: dict, symbol: str, compare_hint: str) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(
        FancyBboxPatch(
            (0.03, 0.08),
            0.94,
            0.84,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            facecolor=CARD,
            edgecolor="#E2E4E8",
            linewidth=1,
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    ax.text(0.08, 0.78, item["label"], fontsize=9.5, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(
        0.08,
        0.48,
        _fmt_money(item["current"], symbol),
        fontsize=17,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=ax.transAxes,
    )
    rate = item["rate"]
    ax.text(
        0.08,
        0.2,
        f"{_rate_arrow(rate)} {_fmt_rate(rate)}  {compare_hint} {_fmt_money(item['previous'], symbol)}",
        fontsize=8.5,
        color=_rate_color(rate),
        va="center",
        transform=ax.transAxes,
    )


def _plot_total_compare(ax, metrics: ReportMetrics) -> None:
    """累计 vs 上月同期；预计全月 vs 上月全月。"""
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
    ax.set_xticklabels(["累计消耗（截至昨日）", "预计全月 vs 上月全月"], fontsize=9.5)
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


def _plot_dual_axis_trend(ax, metrics: ReportMetrics) -> None:
    """左轴：GPU 固定柱；右轴：LLM / sd / GPU按需 / 存储折线。"""
    df = metrics.trend_df.sort_values("date").copy()
    _style_ax(ax)
    if df.empty:
        ax.set_title("暂无趋势数据", loc="left")
        return

    x = np.arange(len(df))
    labels = [f"{d.month}/{d.day}" for d in df["date"]]

    bars = ax.bar(
        x,
        df["gpu_fixed"],
        width=0.72,
        color=BAR_FIXED,
        alpha=0.88,
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
        ("llm", "LLM", "o"),
        ("sd", "sd", "s"),
        ("gpu_ondemand", "GPU 按需", "^"),
        ("gpu_storage", "GPU 按需存储", "D"),
    ]
    for key, label, marker in line_specs:
        ax2.plot(
            x,
            df[key],
            color=LINE_COLORS[key],
            linewidth=2.3,
            marker=marker,
            markersize=5.2,
            label=label,
            zorder=3,
        )
    ax2.set_ylabel("按需分项 (USD)", fontsize=9.5, color=MUTED)
    ax2.tick_params(axis="y", labelsize=9, colors=MUTED)

    ax.set_xticks(x)
    step = 2 if len(x) > 12 else 1
    ax.set_xticklabels([lab if i % step == 0 else "" for i, lab in enumerate(labels)], fontsize=8.5)
    ax.set_xlim(-0.6, len(x) - 0.4)
    ax.set_ylim(0, max(df["gpu_fixed"].max() * 1.18, 1))
    ondemand_max = max(df[k].max() for k, _, _ in line_specs)
    ax2.set_ylim(0, max(ondemand_max * 1.25, 1))

    ax.set_title(
        f"NOVITA {metrics.report_date.month}月五项成本日度趋势（柱=固定 GPU，线=按需项）",
        fontsize=12,
        color=TEXT,
        loc="left",
        pad=28,
        fontweight="bold",
    )

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(
        h1 + h2,
        l1 + l2,
        frameon=False,
        fontsize=8.5,
        ncol=5,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.02),
        borderaxespad=0,
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
    for i, item in enumerate(rows):
        share = item["current"] / month_total * 100 if month_total else 0
        is_total = item["key"] == "total"
        base = "#EEF6F1" if is_total else "#FFFFFF"
        rate = item["rate"]
        rate_bg = "#F8E8E8" if rate == rate and rate > 0 else ("#E7F4EA" if rate == rate and rate < 0 else base)
        cell_text.append(
            [
                item["label"],
                _fmt_money(item["current"], sym),
                _fmt_money(item["previous"], sym),
                _fmt_money(item["change"], sym),
                _fmt_rate(rate),
                f"{share:.0f}%",
            ]
        )
        cell_colors.append([base, base, base, rate_bg, rate_bg, base])

    table = ax.table(
        cellText=cell_text,
        colLabels=["计费项", "当月累计", "上月同期", "环比", "环比率", "占比"],
        loc="center",
        cellLoc="center",
        colColours=["#E7F2EB"] * 6,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.65)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#E2E5EA")
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
    ax.set_title("分项环比明细", fontsize=12, color=TEXT, loc="left", pad=8, fontweight="bold")


def _draw_insights(ax, lines: list[str]) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(
        FancyBboxPatch(
            (0.02, 0.08),
            0.96,
            0.84,
            boxstyle="round,pad=0.02,rounding_size=0.03",
            facecolor="#F3F8F5",
            edgecolor="#CDE0D4",
            linewidth=1,
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    ax.text(0.04, 0.78, "其中", fontsize=12, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
    body = "\n".join(f"{i}、{line}" for i, line in enumerate(lines, start=1)) or "暂无"
    ax.text(0.04, 0.62, body, fontsize=10, color=TEXT, va="top", ha="left", transform=ax.transAxes)


def plot_dashboard(
    metrics: ReportMetrics,
    output_dir: Path,
    extra_notes: list[str] | None = None,
) -> Path:
    _setup_font()
    output_dir.mkdir(parents=True, exist_ok=True)

    p = metrics.current_period
    fig = plt.figure(figsize=(18.2, 15.0), facecolor=BG)
    outer = GridSpec(
        5,
        1,
        height_ratios=[1.05, 2.05, 3.2, 1.95, 1.15],
        hspace=0.30,
        top=0.91,
        bottom=0.03,
        left=0.05,
        right=0.96,
    )

    fig.suptitle(
        f"NOVITA {p.end.month}月成本数据概览",
        fontsize=22,
        fontweight="bold",
        color=TEXT,
        x=0.05,
        ha="left",
        y=0.975,
    )
    fig.text(
        0.05,
        0.938,
        f"统计区间 {p.start.month}月{p.start.day}日 – {p.end.month}月{p.end.day}日"
        f"（截至昨日，共 {p.days} 天）  ｜  单位 {metrics.currency}  ｜  红涨绿跌",
        fontsize=11,
        color=MUTED,
        ha="left",
    )

    hints = {
        "month_total": "上月同期",
        "daily_with_fixed": "上月同期",
        "daily_ondemand": "上月同期",
        "forecast": "上月全月",
    }
    gs_kpi = outer[0].subgridspec(1, 4, wspace=0.07)
    for i, item in enumerate(metrics.overview):
        ax = fig.add_subplot(gs_kpi[0, i])
        _draw_kpi(ax, item, metrics.currency_symbol, hints.get(item["key"], "上月同期"))

    gs_mid = outer[1].subgridspec(1, 2, wspace=0.16)
    _plot_total_compare(fig.add_subplot(gs_mid[0, 0]), metrics)
    _plot_daily_compare(fig.add_subplot(gs_mid[0, 1]), metrics)

    _plot_dual_axis_trend(fig.add_subplot(outer[2]), metrics)
    _plot_detail_table(fig.add_subplot(outer[3]), metrics)
    _draw_insights(fig.add_subplot(outer[4]), build_highlights(metrics, extra_notes))

    path = output_dir / "novita_dashboard.png"
    fig.savefig(path, dpi=170, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def generate_all_charts(
    metrics: ReportMetrics,
    output_dir: Path,
    extra_notes: list[str] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {"dashboard": plot_dashboard(metrics, output_dir, extra_notes)}
