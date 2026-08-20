"""深色综合看板：概览 + 分项环比表 + 主成本/低金额日趋势（每日标金额）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

from .metrics import CATEGORY_LABELS, ReportMetrics
from .report import _fmt_money

BG = "#101412"
CARD = "#171C1A"
CARD_LINE = "#2A3A34"
TEXT = "#F4F7F5"
MUTED = "#9AA8A3"
GRID = "#2C3833"
AUG = "#39E58C"
JUL = "#8FB8A6"
BAR_FIXED = "#39E58C"
ACCENT = "#39E58C"
UP = "#FF7B7B"
DOWN = "#39E58C"
HEADER_GREEN = "#14352C"

LINE_COLORS = {
    "llm": "#5CE1E6",
    "sd": "#F5A623",
    "gpu_ondemand": "#C4A0FF",
    "gpu_storage": "#7DD3FC",
}

KPI_LABELS = {
    "daily_ondemand": "日消耗-按需计费",
}

MOM_ROW_ORDER = ["gpu_fixed", "llm", "sd", "gpu_ondemand", "gpu_storage"]


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
    plt.rcParams["figure.facecolor"] = BG
    plt.rcParams["savefig.facecolor"] = BG
    plt.rcParams["text.color"] = TEXT
    plt.rcParams["axes.labelcolor"] = MUTED
    plt.rcParams["xtick.color"] = MUTED
    plt.rcParams["ytick.color"] = MUTED


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


def _fmt_pct_signed(rate: float) -> str:
    if rate != rate:
        return "N/A"
    number = int(round(rate))
    if number > 0:
        return f"+{number}%"
    return f"{number}%"


def _fmt_signed_money(value: float, symbol: str) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{symbol}{abs(value):,.2f}"


def _fmt_day_amt(value: float) -> str:
    if value != value:
        return ""
    return f"${value:,.2f}"


def _money_axis(ax) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))


def _style_ax(ax, *, both_grids: bool = False) -> None:
    ax.set_facecolor(CARD)
    ax.grid(axis="y", color=GRID, linestyle=":", linewidth=0.8, zorder=0)
    if both_grids:
        ax.grid(True, color=GRID, linestyle=":", linewidth=0.75, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(CARD_LINE)
    ax.spines["bottom"].set_color(CARD_LINE)
    ax.tick_params(labelsize=9, colors=MUTED)
    ax.title.set_color(TEXT)


def _legend(ax, **kwargs) -> None:
    leg = ax.legend(frameon=True, fontsize=9, **kwargs)
    if leg is None:
        return
    frame = leg.get_frame()
    frame.set_facecolor("#121816")
    frame.set_edgecolor(CARD_LINE)
    frame.set_linewidth(0.6)
    for text in leg.get_texts():
        text.set_color(TEXT)


def _value_label(ax, x, y, text: str, color: str, offset=(0, 7), fontsize: float = 6.5) -> None:
    if not text:
        return
    ax.annotate(
        text,
        (x, y),
        textcoords="offset points",
        xytext=offset,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=color,
        zorder=6,
        annotation_clip=False,
        bbox={
            "boxstyle": "round,pad=0.18",
            "facecolor": "#101612",
            "edgecolor": color,
            "linewidth": 0.55,
            "alpha": 0.94,
        },
    )


def pd_day(d) -> str:
    if hasattr(d, "month") and hasattr(d, "day"):
        return f"{int(d.month)}/{int(d.day)}"
    return str(d)


def _draw_kpi(ax, item: dict, symbol: str) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(
        FancyBboxPatch(
            (0.02, 0.06),
            0.96,
            0.88,
            boxstyle="round,pad=0.018,rounding_size=0.04",
            facecolor=CARD,
            edgecolor=CARD_LINE,
            linewidth=1.1,
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (0.02, 0.90),
            0.96,
            0.045,
            boxstyle="round,pad=0.002,rounding_size=0.01",
            facecolor=ACCENT,
            edgecolor="none",
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    label = KPI_LABELS.get(item["key"], item["label"])
    ax.text(0.08, 0.78, label, fontsize=9.2, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(
        0.08,
        0.48,
        _fmt_money(item["current"], symbol),
        fontsize=18.5,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=ax.transAxes,
    )
    rate = item["rate"]
    change = item["change"]
    ax.text(
        0.08,
        0.18,
        f"{_rate_arrow(rate)} {_fmt_pct_signed(rate)}    {_fmt_signed_money(change, symbol)}",
        fontsize=9.2,
        color=_rate_color(rate),
        va="center",
        transform=ax.transAxes,
    )


def _plot_total_compare(ax, metrics: ReportMetrics) -> None:
    _style_ax(ax)
    _money_axis(ax)
    cur = metrics.current_period.totals["total_with_fixed"]
    prev = metrics.previous_period.totals["total_with_fixed"]
    forecast = metrics.forecast_month_total
    prev_full = metrics.prev_month_full_total
    cur_m = metrics.current_period.end.month
    prev_m = metrics.previous_period.end.month
    month_item = next(r for r in metrics.overview if r["key"] == "month_total")
    forecast_item = next(r for r in metrics.overview if r["key"] == "forecast")

    xs = np.array([0, 1])
    width = 0.34
    bars_aug = ax.bar(xs - width / 2, [cur, forecast], width, color=AUG, label=f"{cur_m}月", zorder=3)
    bars_jul = ax.bar(xs + width / 2, [prev, prev_full], width, color=JUL, label=f"{prev_m}月", zorder=3)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"当月总消耗", f"预计{cur_m}月总消耗"], fontsize=10)
    ax.set_ylabel("金额 (USD)", fontsize=9, color=MUTED)
    ax.set_title("累计与预计总消耗对比", fontsize=13, color=TEXT, loc="left", pad=10, fontweight="bold")
    _legend(ax, loc="upper left")

    for bars in (bars_aug, bars_jul):
        for bar in bars:
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h,
                _fmt_day_amt(h),
                ha="center",
                va="bottom",
                fontsize=7.4,
                color=TEXT,
                zorder=4,
            )

    ymax = max(cur, prev, forecast, prev_full, 1) * 1.28
    ax.set_ylim(0, ymax)
    callouts = [
        (0, max(cur, prev), month_item),
        (1, max(forecast, prev_full), forecast_item),
    ]
    for x, peak, item in callouts:
        ax.text(
            x,
            peak + ymax * 0.04,
            f"环比 {_fmt_signed_money(item['change'], metrics.currency_symbol)} ({_fmt_pct_signed(item['rate'])})",
            ha="center",
            va="bottom",
            fontsize=8.4,
            color=_rate_color(item["rate"]),
            fontweight="bold",
        )


def _plot_daily_compare(ax, metrics: ReportMetrics) -> None:
    _style_ax(ax)
    _money_axis(ax)
    cur_m = metrics.current_period.end.month
    prev_m = metrics.previous_period.end.month
    labels = ["含固定GPU", "按需计费"]
    current = [
        metrics.current_period.daily_avg["total_with_fixed"],
        metrics.current_period.daily_avg["total_ondemand"],
    ]
    previous = [
        metrics.previous_period.daily_avg["total_with_fixed"],
        metrics.previous_period.daily_avg["total_ondemand"],
    ]
    fixed_item = next(r for r in metrics.overview if r["key"] == "daily_with_fixed")
    ondemand_item = next(r for r in metrics.overview if r["key"] == "daily_ondemand")
    x = np.arange(len(labels))
    width = 0.34
    b1 = ax.bar(x - width / 2, current, width, color=AUG, label=f"{cur_m}月", zorder=3)
    b2 = ax.bar(x + width / 2, previous, width, color=JUL, label=f"{prev_m}月", zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("金额 (USD)", fontsize=9, color=MUTED)
    ax.set_title("日消耗对比", fontsize=13, color=TEXT, loc="left", pad=10, fontweight="bold")
    _legend(ax, loc="upper right")
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h,
                _fmt_day_amt(h),
                ha="center",
                va="bottom",
                fontsize=7.6,
                color=TEXT,
                zorder=4,
            )
    ymax = max(current + previous + [1]) * 1.32
    ax.set_ylim(0, ymax)
    for xi, item, peak in (
        (0, fixed_item, max(current[0], previous[0])),
        (1, ondemand_item, max(current[1], previous[1])),
    ):
        ax.text(
            xi,
            peak + ymax * 0.04,
            _fmt_pct_signed(item["rate"]),
            ha="center",
            va="bottom",
            fontsize=11,
            color=_rate_color(item["rate"]),
            fontweight="bold",
        )


def _plot_main_trend(ax, metrics: ReportMetrics) -> None:
    """GPU 固定（左轴柱）+ LLM / sd（右轴折线），每个点都标金额。"""
    df = metrics.trend_df.sort_values("date").copy()
    _style_ax(ax, both_grids=True)
    if df.empty:
        ax.set_title("暂无趋势数据", loc="left", color=TEXT)
        return

    x = np.arange(len(df))
    labels = [f"{int(d.day)}日" if hasattr(d, "day") else str(d) for d in df["date"]]
    month = metrics.current_period.end.month

    mask = df["gpu_fixed"].notna()
    ax.bar(
        x[mask.to_numpy()],
        df.loc[mask, "gpu_fixed"],
        width=0.62,
        color=BAR_FIXED,
        alpha=0.92,
        label="GPU固定（左轴）",
        zorder=2,
    )
    ax.set_ylabel("GPU固定 (USD)", fontsize=9.5, color=BAR_FIXED)
    ax.tick_params(axis="y", colors=BAR_FIXED)
    _money_axis(ax)

    ax2 = ax.twinx()
    ax2.set_facecolor("none")
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color("#5CE1E6")
    ax2.grid(False)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax2.tick_params(axis="y", labelsize=9, colors="#5CE1E6")

    line_specs = [
        ("llm", "LLM", "o", (0, 11), LINE_COLORS["llm"]),
        ("sd", "sd", "s", (0, -12), LINE_COLORS["sd"]),
    ]
    for key, label, marker, offset, color in line_specs:
        ax2.plot(
            x,
            df[key],
            color=color,
            linewidth=2.35,
            marker=marker,
            markersize=5.8,
            label=label,
            zorder=3,
        )
        for i, (xi, value) in enumerate(zip(x, df[key])):
            if value != value:
                continue
            day_offset = (0, offset[1] + (4 if i % 2 == 0 else -4))
            _value_label(ax2, xi, float(value), _fmt_day_amt(float(value)), color, offset=day_offset, fontsize=6.2)

    ax2.set_ylabel("LLM / sd (USD)", fontsize=9.5, color=MUTED)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.2)
    ax.set_xlim(-0.65, len(x) - 0.35)
    vals = df["gpu_fixed"].dropna()
    ax.set_ylim(0, max(float(vals.max()) * 1.22 if not vals.empty else 0.0, 1))
    ondemand_max = 0.0
    for key, _, _, _, _ in line_specs:
        series = df[key].dropna()
        if not series.empty:
            ondemand_max = max(ondemand_max, float(series.max()))
    ax2.set_ylim(0, max(ondemand_max * 1.38, 1))

    for xi, value in zip(x[mask.to_numpy()], df.loc[mask, "gpu_fixed"]):
        _value_label(
            ax,
            xi,
            float(value),
            _fmt_day_amt(float(value)),
            BAR_FIXED,
            offset=(0, 10),
            fontsize=6.1,
        )

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.set_title(
        f"NOVITA {month}月日度趋势详情 ｜ 主要成本",
        fontsize=13,
        color=TEXT,
        loc="left",
        pad=30,
        fontweight="bold",
    )
    _legend(
        ax,
        handles=h1 + h2,
        labels=l1 + l2,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.01),
        ncol=3,
        borderaxespad=0,
    )
    ax.text(
        1.0,
        1.07,
        "GPU固定用左轴；LLM、sd 用右轴 ｜ 每日金额已标注",
        fontsize=8.2,
        color=MUTED,
        ha="right",
        va="bottom",
        transform=ax.transAxes,
    )


def _plot_low_cost_trend(ax, metrics: ReportMetrics) -> None:
    """低金额项单独放大，避免被 GPU 固定量级压住。"""
    df = metrics.trend_df.sort_values("date").copy()
    _style_ax(ax, both_grids=True)
    _money_axis(ax)
    if df.empty:
        ax.set_title("暂无趋势数据", loc="left", color=TEXT)
        return

    x = np.arange(len(df))
    labels = [f"{int(d.day)}日" if hasattr(d, "day") else str(d) for d in df["date"]]
    specs = [
        ("gpu_ondemand", "GPU (按需)", "o", (0, 10), LINE_COLORS["gpu_ondemand"]),
        ("gpu_storage", "GPU (按需存储)", "D", (0, -11), LINE_COLORS["gpu_storage"]),
    ]
    ymax = 1.0
    for key, label, marker, offset, color in specs:
        ax.plot(
            x,
            df[key],
            color=color,
            linewidth=2.3,
            marker=marker,
            markersize=5.6,
            label=label,
            zorder=3,
        )
        series = df[key].dropna()
        if not series.empty:
            ymax = max(ymax, float(series.max()))
        for i, (xi, value) in enumerate(zip(x, df[key])):
            if value != value:
                continue
            amount = float(value)
            if amount < 1:
                day_offset = (-14 if key == "gpu_ondemand" else 14, 9)
            else:
                stagger = 3 if i % 2 == 0 else -3
                day_offset = (0, offset[1] + stagger)
            _value_label(
                ax,
                xi,
                amount,
                _fmt_day_amt(amount),
                color,
                offset=day_offset,
                fontsize=6.2,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.2)
    ax.set_xlim(-0.65, len(x) - 0.35)
    ax.set_ylim(0, max(ymax * 1.42, 10))
    ax.set_ylabel("金额 (USD)", fontsize=9.5, color=MUTED)
    ax.set_title("低金额成本 ｜ 独立放大显示", fontsize=13, color=TEXT, loc="left", pad=28, fontweight="bold")
    _legend(ax, loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=2, borderaxespad=0)
    p = metrics.current_period
    ax.text(
        1.0,
        1.07,
        f"数据区间 {p.start.month}月{p.start.day}日–{p.end.month}月{p.end.day}日 ｜ 单位 USD",
        fontsize=8.2,
        color=MUTED,
        ha="right",
        va="bottom",
        transform=ax.transAxes,
    )


def _plot_daily_amount_table(ax, metrics: ReportMetrics) -> None:
    """每天五项 + 当日合计，保证金额可读。"""
    ax.axis("off")
    ax.set_facecolor(BG)
    df = metrics.trend_df.sort_values("date")
    ax.set_title("每日消耗金额明细（单位 USD，与上图逐日对应）", fontsize=13, color=TEXT, loc="left", pad=8, fontweight="bold")
    if df.empty:
        ax.text(0.5, 0.5, "暂无日明细", ha="center", va="center", color=MUTED)
        return

    headers = ["日期", "LLM", "sd", "GPU按需", "GPU按需存储", "GPU固定", "当日合计"]
    keys = ["llm", "sd", "gpu_ondemand", "gpu_storage", "gpu_fixed", "total_with_fixed"]
    cell_text = []
    cell_colors = []
    for idx, row in enumerate(df.itertuples()):
        values = [float(getattr(row, key)) if getattr(row, key) == getattr(row, key) else float("nan") for key in keys]
        cell_text.append([pd_day(getattr(row, "date"))] + [_fmt_day_amt(v) if v == v else "–" for v in values])
        stripe = "#1A2220" if idx % 2 else "#141A18"
        cell_colors.append([stripe] * 6 + ["#1B3329"])

    table = ax.table(
        cellText=cell_text,
        colLabels=headers,
        loc="center",
        cellLoc="center",
        colColours=[HEADER_GREEN] * 7,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.6)
    n = max(len(cell_text), 1)
    table.scale(1, min(1.38, 20 / n))
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#24332E")
        cell.set_linewidth(0.45)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
            cell.set_facecolor(HEADER_GREEN)
        else:
            cell.set_text_props(color=TEXT)
            if col == 0 or col == 6:
                cell.set_text_props(fontweight="bold", color=ACCENT if col == 6 else TEXT)


def _plot_detail_table(ax, metrics: ReportMetrics) -> None:
    ax.axis("off")
    ax.set_facecolor(BG)
    sym = metrics.currency_symbol
    month_total = metrics.current_period.totals["total_with_fixed"]
    cur_m = metrics.current_period.end.month
    note = "（上月同期用表底合计，已剔除 sd 7.12-7.14 异常）" if getattr(metrics, "mom_source", "daily") == "sheet_footer" else ""
    ax.set_title(f"分项环比明细{note}", fontsize=13, color=TEXT, loc="left", pad=8, fontweight="bold")

    rows = [{"key": k, "label": CATEGORY_LABELS[k], **metrics.mom_changes[k]} for k in MOM_ROW_ORDER]
    rows.append({"key": "total", "label": "总消耗", **metrics.mom_changes["total_with_fixed"]})

    cell_text = []
    cell_colors = []
    for idx, item in enumerate(rows):
        share = item["current"] / month_total * 100 if month_total else 0
        is_total = item["key"] == "total"
        stripe = "#1B3329" if is_total else ("#1A2220" if idx % 2 else "#141A18")
        rate = item["rate"]
        cell_text.append(
            [
                item["label"],
                _fmt_money(item["current"], sym),
                _fmt_money(item["previous"], sym),
                _fmt_signed_money(item["change"], sym),
                _fmt_pct_signed(rate) if rate == rate else "N/A",
                f"{share:.1f}%",
            ]
        )
        cell_colors.append([stripe] * 6)

    table = ax.table(
        cellText=cell_text,
        colLabels=["计费项", f"{cur_m}月合计", "上月同期", "增减额", "环比率", "占本期成本"],
        loc="center",
        cellLoc="center",
        colColours=[HEADER_GREEN] * 6,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.78)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#24332E")
        cell.set_linewidth(0.55)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
            cell.set_facecolor(HEADER_GREEN)
        else:
            cell.set_text_props(color=TEXT)
            if col == 0:
                cell.set_text_props(ha="left", fontweight="bold")
                cell.PAD = 0.12
            if col == 4:
                rate = rows[row - 1]["rate"]
                cell.set_text_props(color=_rate_color(rate), fontweight="bold")
            if row == len(rows):
                cell.set_text_props(fontweight="bold")
                if col in (1, 2, 3, 5):
                    cell.set_text_props(color=ACCENT)
                elif col == 4:
                    cell.set_text_props(color=_rate_color(rows[row - 1]["rate"]))


def plot_dashboard(
    metrics: ReportMetrics,
    output_dir: Path,
    extra_notes: list[str] | None = None,
) -> Path:
    _setup_font()
    output_dir.mkdir(parents=True, exist_ok=True)

    p = metrics.current_period
    fig = plt.figure(figsize=(19.6, 27.4), facecolor=BG)
    outer = GridSpec(
        7,
        1,
        height_ratios=[0.50, 1.08, 1.58, 1.42, 2.72, 1.92, 2.05],
        hspace=0.18,
        top=0.975,
        bottom=0.025,
        left=0.05,
        right=0.955,
    )

    title_ax = fig.add_subplot(outer[0])
    title_ax.axis("off")
    title_ax.set_facecolor(BG)
    title_ax.text(
        0.0,
        0.62,
        f"NOVITA {p.end.month}月成本概览",
        fontsize=26,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=title_ax.transAxes,
    )
    title_ax.text(
        0.0,
        0.14,
        f"截至 {p.end.month} 月 {p.end.day} 日  ｜  金额单位：{metrics.currency}",
        fontsize=12,
        color=MUTED,
        va="center",
        transform=title_ax.transAxes,
    )
    right_bits = []
    if metrics.sheet_actual:
        right_bits.append(f"实际 {_fmt_money(metrics.sheet_actual, metrics.currency_symbol)}")
    if getattr(metrics, "mom_source", "daily") == "sheet_footer":
        right_bits.append("已剔除异常消耗")
    if right_bits:
        title_ax.text(
            1.0,
            0.62,
            "  ｜  ".join(right_bits),
            fontsize=12,
            color=ACCENT,
            ha="right",
            va="center",
            transform=title_ax.transAxes,
        )

    gs_kpi = outer[1].subgridspec(1, 4, wspace=0.06)
    for i, item in enumerate(metrics.overview):
        _draw_kpi(fig.add_subplot(gs_kpi[0, i]), item, metrics.currency_symbol)

    gs_mid = outer[2].subgridspec(1, 2, wspace=0.14)
    _plot_total_compare(fig.add_subplot(gs_mid[0, 0]), metrics)
    _plot_daily_compare(fig.add_subplot(gs_mid[0, 1]), metrics)

    _plot_detail_table(fig.add_subplot(outer[3]), metrics)
    _plot_main_trend(fig.add_subplot(outer[4]), metrics)
    _plot_low_cost_trend(fig.add_subplot(outer[5]), metrics)
    _plot_daily_amount_table(fig.add_subplot(outer[6]), metrics)

    path = output_dir / "novita_dashboard.png"
    fig.savefig(path, dpi=155, facecolor=fig.get_facecolor())
    plt.close(fig)
    return _flatten_png_to_rgb(path)


def _flatten_png_to_rgb(path: Path) -> Path:
    """飞书上传不认 RGBA 透明 PNG，压成不透明 RGB。"""
    from PIL import Image

    im = Image.open(path)
    if im.mode == "RGB":
        return path
    bg = Image.new("RGB", im.size, (16, 20, 18))
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
