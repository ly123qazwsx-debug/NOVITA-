"""深色综合看板：概览 + 分项环比表 + 主成本/低金额日趋势（每日标金额）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

from .metrics import CATEGORY_LABELS, ReportMetrics

BG = "#0C0C0C"
CARD = "#161410"
CARD_LINE = "#3D3820"
TEXT = "#F7F4E8"
MUTED = "#B8B08A"
GRID = "#332F1C"
# 主色对齐 Digen Playground：rgb(255, 212, 0)
ACCENT = "#FFD400"
AUG = "#FFD400"
JUL = "#8A7E4A"
BAR_FIXED = "#FFD400"
UP = "#FF7B7B"
DOWN = "#5FD68A"
HEADER_GOLD = "#3A3100"
UNIT = "美元"
UNIT_TAG = "单位：美元"

LINE_COLORS = {
    "llm": "#5CE1E6",
    "sd": "#FF6B2C",
    "gpu_ondemand": "#C4A0FF",
    "gpu_storage": "#7DD3FC",
}

KPI_LABELS = {
    "daily_with_fixed": "日消耗-含固定GPU",
    "daily_ondemand": "日消耗-按需(LLM/SD/GPU按需/存储）",
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


def _fmt_amt(value: float, decimals: int = 2) -> str:
    if value != value:
        return ""
    return f"{value:,.{decimals}f}"


def _fmt_signed_amt(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):,.2f}"


def _fmt_day_amt(value: float) -> str:
    return _fmt_amt(value)


def _money_axis(ax) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))


def _titled(title: str) -> str:
    return f"{title}  ｜  {UNIT_TAG}"


def _style_ax(ax, *, both_grids: bool = False) -> None:
    ax.set_facecolor(CARD)
    ax.grid(axis="y", color=GRID, linestyle=":", linewidth=1.0, zorder=0)
    if both_grids:
        ax.grid(True, color=GRID, linestyle=":", linewidth=0.9, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(CARD_LINE)
    ax.spines["bottom"].set_color(CARD_LINE)
    ax.tick_params(labelsize=14, colors=MUTED, width=1.1, length=5)
    ax.title.set_color(TEXT)


def _legend(ax, **kwargs) -> None:
    kwargs.setdefault("fontsize", 16)
    kwargs.setdefault("handlelength", 1.6)
    kwargs.setdefault("borderpad", 0.6)
    leg = ax.legend(frameon=True, **kwargs)
    if leg is None:
        return
    frame = leg.get_frame()
    frame.set_facecolor("#14120A")
    frame.set_edgecolor(CARD_LINE)
    frame.set_linewidth(0.6)
    for text in leg.get_texts():
        text.set_color(TEXT)


def _value_label(ax, x, y, text: str, color: str, offset=(0, 9), fontsize: float = 9.2) -> None:
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
            "boxstyle": "round,pad=0.22",
            "facecolor": "#14120A",
            "edgecolor": color,
            "linewidth": 0.7,
            "alpha": 0.94,
        },
    )


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
    split_at = label.find("(")
    if split_at > 0:
        ax.text(0.07, 0.84, label[:split_at], fontsize=17, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
        ax.text(0.07, 0.70, label[split_at:], fontsize=13.5, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
        unit_y = 0.56
        value_y = 0.36
        rate_y = 0.15
    else:
        ax.text(0.07, 0.80, label, fontsize=18, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
        unit_y = 0.64
        value_y = 0.40
        rate_y = 0.16
    ax.text(0.07, unit_y, UNIT_TAG, fontsize=13, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(
        0.07,
        value_y,
        _fmt_amt(item["current"]),
        fontsize=30,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=ax.transAxes,
    )
    rate = item["rate"]
    change = item["change"]
    ax.text(
        0.07,
        rate_y,
        f"{_rate_arrow(rate)} {_fmt_pct_signed(rate)}    {_fmt_signed_amt(change)}",
        fontsize=14.5,
        color=_rate_color(rate),
        va="center",
        transform=ax.transAxes,
    )


def _plot_total_compare(ax, metrics: ReportMetrics) -> None:
    _style_ax(ax)
    _money_axis(ax)
    month_item = next(r for r in metrics.overview if r["key"] == "month_total")
    forecast_item = next(r for r in metrics.overview if r["key"] == "forecast")
    cur = month_item["current"]
    prev = month_item["previous"]
    forecast = forecast_item["current"]
    prev_full = forecast_item["previous"]
    cur_m = metrics.current_period.end.month
    prev_m = metrics.previous_period.end.month

    xs = np.array([0, 1])
    width = 0.38
    bars_aug = ax.bar(xs - width / 2, [cur, forecast], width, color=AUG, label=f"{cur_m}月", zorder=3)
    bars_jul = ax.bar(xs + width / 2, [prev, prev_full], width, color=JUL, label=f"{prev_m}月", zorder=3)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"当月总消耗", f"预计{cur_m}月总消耗"], fontsize=16)
    ax.set_ylabel(f"金额（{UNIT}）", fontsize=16, color=MUTED)
    ax.set_title(_titled("累计与预计总消耗对比"), fontsize=22, color=ACCENT, loc="left", pad=14, fontweight="bold")
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
                fontsize=13,
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
            f"环比 {_fmt_signed_amt(item['change'])} ({_fmt_pct_signed(item['rate'])})",
            ha="center",
            va="bottom",
            fontsize=14,
            color=_rate_color(item["rate"]),
            fontweight="bold",
        )


def _plot_daily_compare(ax, metrics: ReportMetrics) -> None:
    _style_ax(ax)
    _money_axis(ax)
    cur_m = metrics.current_period.end.month
    prev_m = metrics.previous_period.end.month
    labels = ["含固定GPU", "按需(LLM/SD/GPU按需/存储)"]
    fixed_item = next(r for r in metrics.overview if r["key"] == "daily_with_fixed")
    ondemand_item = next(r for r in metrics.overview if r["key"] == "daily_ondemand")
    current = [fixed_item["current"], ondemand_item["current"]]
    previous = [fixed_item["previous"], ondemand_item["previous"]]
    x = np.arange(len(labels))
    width = 0.38
    b1 = ax.bar(x - width / 2, current, width, color=AUG, label=f"{cur_m}月", zorder=3)
    b2 = ax.bar(x + width / 2, previous, width, color=JUL, label=f"{prev_m}月", zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=16)
    ax.set_ylabel(f"金额（{UNIT}）", fontsize=16, color=MUTED)
    ax.set_title(_titled("日消耗对比"), fontsize=22, color=ACCENT, loc="left", pad=14, fontweight="bold")
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
                fontsize=13,
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
            fontsize=16,
            color=_rate_color(item["rate"]),
            fontweight="bold",
        )


def _plot_main_trend(ax, metrics: ReportMetrics) -> None:
    """GPU 固定（左轴柱）+ LLM / sd（右轴折线），每个点都标金额。"""
    df = metrics.trend_df.sort_values("date").copy()
    _style_ax(ax, both_grids=True)
    if df.empty:
        ax.set_title("暂无趋势数据", loc="left", color=ACCENT)
        return

    x = np.arange(len(df))
    labels = [f"{int(d.day)}日" if hasattr(d, "day") else str(d) for d in df["date"]]
    month = metrics.current_period.end.month

    mask = df["gpu_fixed"].notna()
    ax.bar(
        x[mask.to_numpy()],
        df.loc[mask, "gpu_fixed"],
        width=0.68,
        color=BAR_FIXED,
        alpha=0.92,
        label="GPU固定（左轴）",
        zorder=2,
    )
    ax.set_ylabel(f"GPU固定（{UNIT}）", fontsize=16, color=BAR_FIXED)
    ax.tick_params(axis="y", colors=BAR_FIXED, labelsize=14)
    _money_axis(ax)

    ax2 = ax.twinx()
    ax2.set_facecolor("none")
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color("#5CE1E6")
    ax2.grid(False)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax2.tick_params(axis="y", labelsize=14, colors="#5CE1E6")

    line_specs = [
        ("llm", "LLM", "o", (0, 14), LINE_COLORS["llm"]),
        ("sd", "sd", "s", (0, -15), LINE_COLORS["sd"]),
    ]
    for key, label, marker, offset, color in line_specs:
        ax2.plot(
            x,
            df[key],
            color=color,
            linewidth=3.0,
            marker=marker,
            markersize=8.2,
            label=label,
            zorder=3,
        )
        for i, (xi, value) in enumerate(zip(x, df[key])):
            if value != value:
                continue
            day_offset = (0, offset[1] + (5 if i % 2 == 0 else -5))
            _value_label(ax2, xi, float(value), _fmt_day_amt(float(value)), color, offset=day_offset, fontsize=11)

    ax2.set_ylabel(f"LLM / sd（{UNIT}）", fontsize=16, color=MUTED)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=13)
    ax.set_xlim(-0.65, len(x) - 0.35)
    vals = df["gpu_fixed"].dropna()
    ax.set_ylim(0, max(float(vals.max()) * 1.28 if not vals.empty else 0.0, 1))
    ondemand_max = 0.0
    for key, _, _, _, _ in line_specs:
        series = df[key].dropna()
        if not series.empty:
            ondemand_max = max(ondemand_max, float(series.max()))
    ax2.set_ylim(0, max(ondemand_max * 1.42, 1))

    for xi, value in zip(x[mask.to_numpy()], df.loc[mask, "gpu_fixed"]):
        _value_label(
            ax,
            xi,
            float(value),
            _fmt_day_amt(float(value)),
            BAR_FIXED,
            offset=(0, 13),
            fontsize=11,
        )

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.set_title(
        _titled(f"NOVITA {month}月日度趋势详情 ｜ 主要成本"),
        fontsize=22,
        color=ACCENT,
        loc="left",
        pad=34,
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
        1.08,
        f"GPU固定用左轴；LLM、sd 用右轴 ｜ 每日金额已标注（{UNIT}）",
        fontsize=14,
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
        ax.set_title("暂无趋势数据", loc="left", color=ACCENT)
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
            linewidth=3.0,
            marker=marker,
            markersize=8.0,
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
                day_offset = (-16 if key == "gpu_ondemand" else 16, 11)
            else:
                stagger = 4 if i % 2 == 0 else -4
                day_offset = (0, offset[1] + stagger)
            _value_label(
                ax,
                xi,
                amount,
                _fmt_day_amt(amount),
                color,
                offset=day_offset,
                fontsize=11,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=13)
    ax.set_xlim(-0.65, len(x) - 0.35)
    ax.set_ylim(0, max(ymax * 1.45, 10))
    ax.set_ylabel(f"金额（{UNIT}）", fontsize=16, color=MUTED)
    ax.set_title(_titled("低金额成本 ｜ 独立放大显示"), fontsize=22, color=ACCENT, loc="left", pad=32, fontweight="bold")
    _legend(ax, loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=2, borderaxespad=0)
    p = metrics.current_period
    ax.text(
        1.0,
        1.08,
        f"数据区间 {p.start.month}月{p.start.day}日–{p.end.month}月{p.end.day}日 ｜ {UNIT_TAG}",
        fontsize=14,
        color=MUTED,
        ha="right",
        va="bottom",
        transform=ax.transAxes,
    )


def _plot_detail_table(ax, metrics: ReportMetrics) -> None:
    ax.axis("off")
    ax.set_facecolor(BG)
    month_total = metrics.current_period.totals["total_with_fixed"]
    cur_m = metrics.current_period.end.month
    note = "（上月同期用表底合计，已剔除 sd 7.12-7.14 异常）" if getattr(metrics, "mom_source", "daily") == "sheet_footer" else ""
    ax.set_title(_titled(f"分项环比明细{note}"), fontsize=22, color=ACCENT, loc="left", pad=12, fontweight="bold")

    rows = [{"key": k, "label": CATEGORY_LABELS[k], **metrics.mom_changes[k]} for k in MOM_ROW_ORDER]
    rows.append({"key": "total", "label": "总消耗", **metrics.mom_changes["total_with_fixed"]})

    cell_text = []
    cell_colors = []
    for idx, item in enumerate(rows):
        share = item["current"] / month_total * 100 if month_total else 0
        is_total = item["key"] == "total"
        stripe = "#2E2A12" if is_total else ("#1C1A12" if idx % 2 else "#141310")
        rate = item["rate"]
        cell_text.append(
            [
                item["label"],
                _fmt_amt(item["current"]),
                _fmt_amt(item["previous"]),
                _fmt_signed_amt(item["change"]),
                _fmt_pct_signed(rate) if rate == rate else "N/A",
                f"{share:.1f}%",
            ]
        )
        cell_colors.append([stripe] * 6)

    table = ax.table(
        cellText=cell_text,
        colLabels=["计费项", f"{cur_m}月合计（{UNIT}）", f"上月同期（{UNIT}）", f"增减额（{UNIT}）", "环比率", "占本期成本"],
        loc="center",
        cellLoc="center",
        colColours=[HEADER_GOLD] * 6,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(16)
    table.scale(1, 2.15)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#4A4018")
        cell.set_linewidth(0.55)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
            cell.set_facecolor(HEADER_GOLD)
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
    fig = plt.figure(figsize=(24.0, 28.2), facecolor=BG)
    outer = GridSpec(
        6,
        1,
        height_ratios=[0.68, 1.42, 1.92, 1.78, 3.35, 2.35],
        hspace=0.20,
        top=0.972,
        bottom=0.028,
        left=0.058,
        right=0.945,
    )

    title_ax = fig.add_subplot(outer[0])
    title_ax.axis("off")
    title_ax.set_facecolor(BG)
    title_ax.text(
        0.0,
        0.62,
        f"NOVITA {p.end.month}月成本概览",
        fontsize=42,
        fontweight="bold",
        color=ACCENT,
        va="center",
        transform=title_ax.transAxes,
    )
    title_ax.text(
        0.0,
        0.12,
        f"截至 {p.end.month} 月 {p.end.day} 日  ｜  {UNIT_TAG}",
        fontsize=20,
        color=MUTED,
        va="center",
        transform=title_ax.transAxes,
    )
    right_bits = []
    if metrics.sheet_actual:
        right_bits.append(f"实际 {_fmt_amt(metrics.sheet_actual)}")
        right_bits.append("已剔除异常消耗")
    elif getattr(metrics, "mom_source", "daily") == "sheet_footer":
        right_bits.append("已剔除异常消耗")
    if right_bits:
        title_ax.text(
            1.0,
            0.62,
            "  ｜  ".join(right_bits),
            fontsize=18,
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

    path = output_dir / "novita_dashboard.png"
    fig.savefig(path, dpi=165, facecolor=fig.get_facecolor())
    plt.close(fig)
    return _flatten_png_to_rgb(path)


def _flatten_png_to_rgb(path: Path) -> Path:
    """飞书上传不认 RGBA 透明 PNG，压成不透明 RGB。"""
    from PIL import Image

    im = Image.open(path)
    if im.mode == "RGB":
        return path
    bg = Image.new("RGB", im.size, (12, 12, 10))
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
