#!/usr/bin/env python3
"""AWS 8 月成本综合看板：对齐用户上传图的信息密度与样式，截止 8/26。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import MultipleLocator

# ── 对齐原图的深海军配色 ──────────────────────────────────────────────────
BG = "#06121B"
CARD = "#0D202D"
CARD_LINE = "#1E3D4D"
TEXT = "#F4F7FA"
MUTED = "#8AA0B0"
GRID = "#1A3340"
ACCENT = "#7EC8E3"
UP = "#FF6B9D"
DOWN = "#3DDC97"
HEADER = "#9FD4E8"
UNIT = "USD"
SYMBOL = "$"
AUG_DAYS = 31
AS_OF = 26
BASE_DAYS = 25

LINE_COLORS = {
    "RDS-数据库": "#50A0E0",
    "S3": "#F0D040",
    "ELB-负载均衡": "#3FD0D0",
    "ECS": "#60D0B0",
    "EC2 实例": "#A090E0",
    "Amplify": "#FF6B9D",
    "CloudFront": "#E8EEF2",
    "ElastiCache": "#F0A040",
    "VPC": "#F0D040",
    "EC2-其他": "#6EC8F0",
}

# 8/1–8/25 分项合计（来自上传原表）
BASE_ROWS = [
    {"name": "RDS-数据库", "current": 2885.74, "previous": 1824.86},
    {"name": "S3", "current": 2708.06, "previous": 2771.28},
    {"name": "ELB-负载均衡", "current": 1408.28, "previous": 1205.69},
    {"name": "ECS", "current": 1168.06, "previous": 1224.55},
    {"name": "EC2 实例", "current": 650.88, "previous": 691.83},
    {"name": "Amplify", "current": 525.82, "previous": 253.08},
    {"name": "CloudFront", "current": 457.13, "previous": 642.71},
    {"name": "ElastiCache", "current": 420.31, "previous": 407.84},
    {"name": "VPC", "current": 411.38, "previous": 421.24},
    {"name": "EC2-其他", "current": 179.04, "previous": 226.57},
]

BASE_MTD = 14116.08
BASE_DAILY = 564.64
BASE_FORECAST = 17148.69
BASE_MTD_CHANGE = 697.96
BASE_DAILY_CHANGE = 27.92
BASE_FORECAST_CHANGE = 686.58

# 8/1–8/25 日度金额：从上传原图逐点读取，不再缩放（缩放会把 88.0 改成错数）
DAILY_25 = {
    "RDS-数据库": [
        137.4, 122.8, 148.9, 137.5, 134.2, 131.5, 130.2, 129.1, 126.8, 139.1,
        139.2, 129.8, 105.3, 90.4, 82.6, 86.3, 107.4, 109.1, 111.5, 106.3,
        85.0, 79.0, 79.7, 84.5, 88.0,
    ],
    "S3": [
        98.0, 96.1, 99.4, 104.0, 97.8, 99.2, 100.3, 94.7, 102.9, 99.1,
        103.5, 98.6, 101.3, 97.8, 100.5, 101.0, 114.6, 119.0, 121.7, 122.7,
        124.1, 123.9, 131.2, 129.2, 126.8,
    ],
    "ELB-负载均衡": [
        44.2, 44.8, 45.0, 45.1, 45.3, 48.9, 49.8, 51.1, 52.5, 58.0,
        59.2, 56.8, 56.5, 59.1, 61.2, 63.0, 64.0, 61.1, 61.0, 61.8,
        62.3, 59.7, 60.9, 61.9, 64.2,
    ],
    "ECS": [
        46.1, 48.5, 49.3, 49.9, 48.9, 45.3, 45.3, 45.1, 45.4, 46.9,
        47.4, 46.8, 47.1, 46.7, 46.5, 46.9, 47.0, 46.6, 46.5, 47.3,
        48.6, 49.0, 49.8, 50.2, 50.4,
    ],
    "EC2 实例": [
        22.1, 26.7, 26.5, 26.4, 26.6, 26.6, 27.1, 26.3, 26.7, 26.5,
        27.0, 26.2, 26.1, 25.6, 25.9, 25.9, 26.3, 26.0, 26.0, 25.7,
        26.0, 25.4, 25.6, 26.2, 25.6,
    ],
    "Amplify": [
        7.4, 7.8, 11.2, 11.2, 12.5, 11.1, 12.3, 9.0, 7.8, 11.2,
        12.7, 10.8, 13.8, 23.9, 29.1, 29.6, 29.4, 33.1, 31.3, 34.1,
        38.1, 32.1, 32.9, 34.9, 38.2,
    ],
    "CloudFront": [
        14.2, 15.3, 23.6, 23.0, 22.4, 21.6, 19.2, 24.4, 23.4, 22.2,
        21.7, 24.8, 24.1, 18.8, 15.2, 14.6, 16.0, 17.6, 15.4, 13.2,
        13.9, 12.5, 12.2, 12.6, 14.0,
    ],
    "ElastiCache": [
        16.8, 16.8, 16.9, 16.8, 16.8, 16.8, 16.8, 16.7, 16.9, 16.8,
        16.8, 16.8, 16.8, 16.9, 16.8, 16.9, 17.0, 17.1, 17.0, 16.9,
        16.8, 16.8, 16.9, 16.8, 16.8,
    ],
    "VPC": [
        16.4, 16.4, 16.4, 16.4, 16.4, 16.4, 16.4, 16.3, 16.5, 16.4,
        16.4, 16.4, 16.4, 16.4, 16.4, 16.4, 16.4, 16.4, 16.4, 16.4,
        16.8, 16.9, 17.1, 17.2, 17.3,
    ],
    "EC2-其他": [
        7.1, 7.1, 7.1, 7.2, 7.2, 7.2, 7.2, 7.1, 7.1, 7.2,
        7.2, 7.2, 7.2, 7.2, 7.1, 7.2, 7.1, 7.2, 7.1, 7.2,
        7.3, 7.1, 7.1, 7.2, 7.2,
    ],
}


def _fonts() -> tuple[font_manager.FontProperties, font_manager.FontProperties]:
    font_dir = Path(__file__).resolve().parent / "fonts"
    regular_path = font_dir / "NotoSansCJKsc-Regular.otf"
    bold_path = font_dir / "NotoSansCJKsc-Bold.otf"
    if regular_path.exists():
        font_manager.fontManager.addfont(str(regular_path))
        regular = font_manager.FontProperties(fname=str(regular_path))
    else:
        regular = font_manager.FontProperties(family="DejaVu Sans")
    if bold_path.exists():
        font_manager.fontManager.addfont(str(bold_path))
        bold = font_manager.FontProperties(fname=str(bold_path))
    else:
        bold = regular
    plt.rcParams["font.family"] = regular.get_name()
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = BG
    plt.rcParams["savefig.facecolor"] = BG
    return regular, bold


def _fmt_amt(value: float) -> str:
    return f"{SYMBOL}{value:,.2f}"


def _fmt_signed_amt(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{SYMBOL}{abs(value):,.2f}"


def _fmt_signed_plain(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):,.2f}"


def _fmt_pct(rate: float) -> str:
    n = int(round(rate))
    return f"+{n}%" if n > 0 else f"{n}%"


def _tone(value: float) -> str:
    if abs(value) < 1e-9:
        return MUTED
    return UP if value > 0 else DOWN


def _next_day(series: list[float]) -> float:
    """8/26：按原图 8/24→8/25 的变动外推一天。"""
    nxt = series[-1] + (series[-1] - series[-2])
    return float(np.round(nxt, 1))


def build_dataset() -> dict:
    assert all(len(v) == BASE_DAYS for v in DAILY_25.values())
    daily: dict[str, np.ndarray] = {}
    rows = []
    top10_25 = sum(r["current"] for r in BASE_ROWS)
    other_daily = (BASE_MTD - top10_25) / BASE_DAYS

    for row in BASE_ROWS:
        name = row["name"]
        s25 = list(DAILY_25[name])
        day26 = _next_day(s25)
        series = np.array(s25 + [day26], dtype=float)
        daily[name] = series
        current = float(np.round(row["current"] + day26, 2))
        prev_daily = row["previous"] / BASE_DAYS
        previous = float(np.round(row["previous"] + prev_daily, 2))
        change = float(np.round(current - previous, 2))
        rate = change / previous * 100 if previous else 0.0
        rows.append(
            {
                "name": name,
                "current": current,
                "previous": previous,
                "change": change,
                "rate": rate,
            }
        )

    day26_total = sum(float(daily[r["name"]][-1]) for r in BASE_ROWS) + other_daily
    mtd = float(np.round(BASE_MTD + day26_total, 2))
    daily_avg = float(np.round(mtd / AS_OF, 2))

    prev_mtd_25 = BASE_MTD - BASE_MTD_CHANGE
    prev_daily = BASE_DAILY - BASE_DAILY_CHANGE
    prev_mtd = float(np.round(prev_mtd_25 + prev_daily, 2))
    prev_forecast = BASE_FORECAST - BASE_FORECAST_CHANGE
    remain_rate = (BASE_FORECAST - BASE_MTD) / (AUG_DAYS - BASE_DAYS)
    forecast = float(np.round(mtd + remain_rate * (AUG_DAYS - AS_OF), 2))

    for row in rows:
        row["share"] = row["current"] / mtd * 100

    overview = [
        {
            "label": "当月总消耗",
            "hint": "总额",
            "current": mtd,
            "change": float(np.round(mtd - prev_mtd, 2)),
            "rate": (mtd - prev_mtd) / prev_mtd * 100,
            "note": "",
        },
        {
            "label": "日消耗",
            "hint": "本期日均",
            "current": daily_avg,
            "change": float(np.round(daily_avg - prev_daily, 2)),
            "rate": (daily_avg - prev_daily) / prev_daily * 100,
            "note": "",
        },
        {
            "label": "预计8月总消耗",
            "hint": "按工作簿预估",
            "current": forecast,
            "change": float(np.round(forecast - prev_forecast, 2)),
            "rate": (forecast - prev_forecast) / prev_forecast * 100,
            "note": "含8/26",
        },
    ]
    return {"daily": daily, "rows": rows, "overview": overview}


def _style_chart(ax) -> None:
    ax.set_facecolor(BG)
    ax.grid(axis="y", color=GRID, linestyle="-", linewidth=0.5, zorder=0)
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#2A4A58")
    ax.spines["bottom"].set_color("#2A4A58")
    ax.spines["left"].set_linewidth(0.6)
    ax.spines["bottom"].set_linewidth(0.6)
    ax.tick_params(colors=MUTED, width=0.6, length=3, labelsize=7.5, pad=3)


def _draw_kpi(ax, item: dict, regular, bold) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(
        FancyBboxPatch(
            (0.01, 0.06),
            0.98,
            0.88,
            boxstyle="round,pad=0.012,rounding_size=0.035",
            facecolor=CARD,
            edgecolor=CARD_LINE,
            linewidth=0.8,
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    ax.text(0.06, 0.78, item["label"], fontproperties=regular, fontsize=11, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(
        0.06,
        0.46,
        _fmt_amt(item["current"]),
        fontproperties=bold,
        fontsize=22,
        color=TEXT,
        va="center",
        transform=ax.transAxes,
    )
    ax.text(0.06, 0.18, item["hint"], fontproperties=regular, fontsize=9, color=MUTED, va="center", transform=ax.transAxes)
    tone = _tone(item["rate"])
    ax.text(
        0.94,
        0.78,
        _fmt_pct(item["rate"]),
        fontproperties=bold,
        fontsize=12,
        color=tone,
        ha="right",
        va="center",
        transform=ax.transAxes,
    )
    ax.text(
        0.94,
        0.48,
        f"▲ {_fmt_signed_amt(item['change'])}" if item["change"] >= 0 else f"▼ {_fmt_signed_amt(item['change'])}",
        fontproperties=regular,
        fontsize=10.5,
        color=tone,
        ha="right",
        va="center",
        transform=ax.transAxes,
    )
    if item.get("note"):
        ax.text(0.94, 0.18, item["note"], fontproperties=regular, fontsize=7.5, color=MUTED, ha="right", va="center", transform=ax.transAxes)


def _draw_table(ax, rows: list[dict], regular, bold) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)

    headers = ["计费项", "8月合计 (截至8/26)", "上月同期", "增减金额", "环比率", "占本期成本"]
    widths = [0.18, 0.20, 0.16, 0.16, 0.13, 0.17]
    xs = [0.0]
    for w in widths[:-1]:
        xs.append(xs[-1] + w)
    aligns = ["left", "right", "right", "right", "right", "right"]

    n = len(rows)
    header_y = 0.96
    row_h = 0.078
    first_y = 0.88

    ax.plot([0, 1], [header_y + 0.04, header_y + 0.04], color="#2A4A58", lw=0.6, transform=ax.transAxes, clip_on=False)
    for x, head, align, w in zip(xs, headers, aligns, widths):
        tx = x + (0.01 if align == "left" else w - 0.01)
        ax.text(
            tx,
            header_y,
            head,
            fontproperties=bold,
            fontsize=9.5,
            color=HEADER,
            ha=align,
            va="center",
            transform=ax.transAxes,
        )
    ax.plot([0, 1], [header_y - 0.04, header_y - 0.04], color="#2A4A58", lw=0.7, transform=ax.transAxes, clip_on=False)

    for i, row in enumerate(rows):
        y = first_y - i * row_h
        if i % 2 == 0:
            ax.add_patch(
                FancyBboxPatch(
                    (0.0, y - 0.035),
                    1.0,
                    0.07,
                    boxstyle="square,pad=0",
                    facecolor="#0A1A24",
                    edgecolor="none",
                    transform=ax.transAxes,
                    clip_on=False,
                )
            )
        values = [
            row["name"],
            _fmt_amt(row["current"]),
            _fmt_amt(row["previous"]),
            _fmt_signed_plain(row["change"]),
            _fmt_pct(row["rate"]),
            f"{row['share']:.1f}%",
        ]
        colors = [TEXT, TEXT, TEXT, _tone(row["change"]), _tone(row["rate"]), TEXT]
        weights = [bold, regular, regular, bold, bold, regular]
        for x, val, align, w, color, fp in zip(xs, values, aligns, widths, colors, weights):
            tx = x + (0.01 if align == "left" else w - 0.01)
            ax.text(tx, y, val, fontproperties=fp, fontsize=10.5, color=color, ha=align, va="center", transform=ax.transAxes)
        ax.plot([0, 1], [y - 0.038, y - 0.038], color="#16303C", lw=0.4, transform=ax.transAxes, clip_on=False)


def _label_offset(name: str, idx: int, names: list[str]) -> tuple[int, int]:
    lane = names.index(name)
    # 上下交错，避免多序列标签叠在一起
    base = 8 if (idx + lane) % 2 == 0 else -9
    extra = {0: 2, 1: 0, 2: 1, 3: -2, 4: -1}.get(lane, 0)
    return (0, base + extra * 3)


def _plot_trend(ax, names, daily, title, y_max, y_step, regular, bold) -> None:
    _style_chart(ax)
    x = np.arange(1, AS_OF + 1)
    for name in names:
        series = daily[name]
        color = LINE_COLORS[name]
        ls = (0, (4, 2.2)) if name == "VPC" else "-"
        try:
            from scipy.interpolate import PchipInterpolator

            xs = np.linspace(float(x[0]), float(x[-1]), 420)
            ys = PchipInterpolator(x, series)(xs)
            ax.plot(xs, ys, color=color, linewidth=1.7, linestyle=ls, zorder=3, solid_capstyle="round")
            ax.plot(
                x,
                series,
                color=color,
                linestyle="none",
                marker="o",
                markersize=3.6,
                markerfacecolor=color,
                markeredgecolor=BG,
                markeredgewidth=0.4,
                label=name,
                zorder=4,
            )
        except Exception:
            ax.plot(
                x,
                series,
                color=color,
                linewidth=1.7,
                linestyle=ls,
                marker="o",
                markersize=3.6,
                markerfacecolor=color,
                markeredgecolor=BG,
                markeredgewidth=0.4,
                label=name,
                zorder=3,
                solid_capstyle="round",
            )
        for i, (xi, val) in enumerate(zip(x, series)):
            dx, dy = _label_offset(name, i, names)
            ax.annotate(
                f"{float(val):.1f}",
                (xi, float(val)),
                textcoords="offset points",
                xytext=(dx, dy),
                ha="center",
                va="center",
                fontsize=6.3,
                color=color,
                fontproperties=regular,
                zorder=4,
                annotation_clip=False,
            )

    ax.set_xlim(0.6, AS_OF + 0.4)
    ax.set_ylim(0, y_max)
    ax.yaxis.set_major_locator(MultipleLocator(y_step))
    ax.set_xticks(x)
    ax.set_xticklabels([f"8月{d}日" for d in x], fontproperties=regular, fontsize=7.2)
    ax.tick_params(axis="y", labelsize=7.5)
    for lab in ax.get_yticklabels():
        lab.set_fontproperties(regular)
        lab.set_color(MUTED)
    ax.set_title(title, fontproperties=bold, fontsize=12.5, color=TEXT, loc="left", pad=18)
    handles, labels = ax.get_legend_handles_labels()
    leg = ax.legend(
        handles,
        labels,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.02),
        ncol=5,
        frameon=False,
        fontsize=8.5,
        handlelength=1.6,
        columnspacing=1.3,
        borderaxespad=0,
        prop=regular,
    )
    for text, name in zip(leg.get_texts(), labels):
        text.set_color(LINE_COLORS[name])
        text.set_fontproperties(regular)


def generate_dashboard(output_path: Path) -> Path:
    regular, bold = _fonts()
    data = build_dataset()
    daily, rows, overview = data["daily"], data["rows"], data["overview"]

    fig = plt.figure(figsize=(15.7, 20.0), facecolor=BG)
    outer = GridSpec(
        5,
        1,
        height_ratios=[0.42, 0.72, 1.72, 2.55, 2.15],
        hspace=0.16,
        top=0.965,
        bottom=0.032,
        left=0.055,
        right=0.965,
    )

    title_ax = fig.add_subplot(outer[0])
    title_ax.axis("off")
    title_ax.set_facecolor(BG)
    title_ax.text(
        0.0,
        0.62,
        "AWS 8月成本概览 (截至8/26)",
        fontproperties=bold,
        fontsize=22,
        color=TEXT,
        va="center",
        transform=title_ax.transAxes,
    )
    title_ax.text(
        0.0,
        0.18,
        "明细区间：8/1–8/26  ｜  单位：USD",
        fontproperties=regular,
        fontsize=10,
        color=MUTED,
        va="center",
        transform=title_ax.transAxes,
    )
    title_ax.text(
        1.0,
        0.62,
        "成本前十项  ·  日度趋势详情",
        fontproperties=regular,
        fontsize=10,
        color=ACCENT,
        ha="right",
        va="center",
        transform=title_ax.transAxes,
    )

    gs_kpi = outer[1].subgridspec(1, 3, wspace=0.035)
    for i, item in enumerate(overview):
        _draw_kpi(fig.add_subplot(gs_kpi[0, i]), item, regular, bold)

    table_ax = fig.add_subplot(outer[2])
    table_ax.text(
        0.0,
        1.045,
        "累计消耗前10项  ｜  分项环比明细  ｜  单位：USD",
        fontproperties=bold,
        fontsize=12.5,
        color=TEXT,
        va="bottom",
        transform=table_ax.transAxes,
        clip_on=False,
    )
    table_ax.text(
        1.0,
        1.045,
        "对比区间：本期明细与上月同期",
        fontproperties=regular,
        fontsize=9,
        color=MUTED,
        ha="right",
        va="bottom",
        transform=table_ax.transAxes,
        clip_on=False,
    )
    _draw_table(table_ax, rows, regular, bold)

    top5 = [r["name"] for r in rows[:5]]
    bottom5 = [r["name"] for r in rows[5:]]
    _plot_trend(
        fig.add_subplot(outer[3]),
        top5,
        daily,
        "排名 1-5  ｜  主要成本趋势",
        y_max=175,
        y_step=25,
        regular=regular,
        bold=bold,
    )
    _plot_trend(
        fig.add_subplot(outer[4]),
        bottom5,
        daily,
        "排名 6-10  ｜  其余成本趋势",
        y_max=48,
        y_step=10,
        regular=regular,
        bold=bold,
    )

    fig.text(
        0.055,
        0.012,
        "口径说明：明细区间为8/1-8/26。8/1-8/25 逐点取自原图；8/26 按 8/24→8/25 变动补一天。汇总表 = 原表合计 + 8/26。",
        fontproperties=regular,
        fontsize=8,
        color=MUTED,
        ha="left",
    )
    fig.text(0.965, 0.012, "金额单位：USD", fontproperties=regular, fontsize=8, color=MUTED, ha="right")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, facecolor=fig.get_facecolor())
    plt.close(fig)

    from PIL import Image

    im = Image.open(output_path)
    if im.mode != "RGB":
        bg = Image.new("RGB", im.size, (6, 18, 27))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        bg.save(output_path, "PNG", optimize=True)
    return output_path


if __name__ == "__main__":
    out = generate_dashboard(Path("output/charts/aws_dashboard.png"))
    print(f"已生成: {out.resolve()}")
