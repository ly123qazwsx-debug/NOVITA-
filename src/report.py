"""生成 HTML / Markdown 报告。"""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from .data_fetcher import COST_COLUMNS
from .metrics import CATEGORY_LABELS, ReportMetrics


def _fmt_money(value: float, symbol: str) -> str:
    return f"{symbol}{value:,.2f}"


def _fmt_rate(rate: float) -> str:
    if rate != rate:
        return "N/A"
    return f"{rate:+.1f}%"


def _img_to_base64(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


HTML_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>NOVITA 成本日报 - {{ report_date }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2329; }
    h1 { font-size: 24px; margin-bottom: 8px; }
    .subtitle { color: #646a73; margin-bottom: 24px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .kpi-card { background: #f5f6f7; border-radius: 8px; padding: 16px; }
    .kpi-label { font-size: 13px; color: #646a73; }
    .kpi-value { font-size: 22px; font-weight: 700; margin-top: 6px; }
    .kpi-sub { font-size: 12px; color: #8f959e; margin-top: 4px; }
    table { border-collapse: collapse; width: 100%; margin: 16px 0 32px; font-size: 14px; }
    th, td { border: 1px solid #dee0e3; padding: 10px 12px; text-align: right; }
    th { background: #f5f6f7; text-align: center; }
    td:first-child, th:first-child { text-align: left; }
    .up { color: #d83931; }
    .down { color: #2ea121; }
    .chart { margin: 24px 0; }
    .chart img { max-width: 100%; border: 1px solid #dee0e3; border-radius: 8px; }
    h2 { font-size: 18px; margin-top: 32px; }
  </style>
</head>
<body>
  <h1>NOVITA 成本日报</h1>
  <div class="subtitle">报告日期：{{ report_date }} ｜ 统计区间：{{ period_start }} ~ {{ period_end }} ｜ 币种：{{ currency }}</div>

  <h2>当月数据概览</h2>
  <table>
    <thead>
      <tr>
        <th>指标</th>
        <th>当月数据</th>
        <th>上月同期</th>
        <th>环比</th>
        <th>环比率</th>
      </tr>
    </thead>
    <tbody>
      {% for row in overview_rows %}
      <tr>
        <td>{{ row.label }}</td>
        <td>{{ row.current }}</td>
        <td>{{ row.previous }}</td>
        <td class="{{ row.change_class }}">{{ row.change }}</td>
        <td class="{{ row.change_class }}">{{ row.rate }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <h2>分项环比明细</h2>
  <table>
    <thead>
      <tr>
        <th>分项</th>
        <th>当月同期</th>
        <th>上月同期</th>
        <th>环比</th>
        <th>环比率</th>
      </tr>
    </thead>
    <tbody>
      {% for row in mom_rows %}
      <tr>
        <td>{{ row.label }}</td>
        <td>{{ row.current }}</td>
        <td>{{ row.previous }}</td>
        <td class="{{ row.change_class }}">{{ row.change }}</td>
        <td class="{{ row.change_class }}">{{ row.rate }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <h2>综合看板</h2>
  {% for title, img in charts %}
  <div class="chart"><img src="{{ img }}" alt="{{ title }}" /></div>
  {% endfor %}
</body>
</html>"""
)


def build_report_context(metrics: ReportMetrics, charts: dict[str, Path]) -> dict:
    sym = metrics.currency_symbol

    def _row(label: str, item: dict) -> dict:
        c = item["change"]
        return {
            "label": label,
            "current": _fmt_money(item["current"], sym),
            "previous": _fmt_money(item["previous"], sym),
            "change": _fmt_money(c, sym),
            "rate": _fmt_rate(item["rate"]),
            "change_class": "up" if c > 0 else ("down" if c < 0 else ""),
        }

    overview_rows = [_row(item["label"], item) for item in metrics.overview]

    mom_rows = []
    for key in COST_COLUMNS:
        item = metrics.mom_changes[key]
        c = item["change"]
        mom_rows.append(
            {
                "label": CATEGORY_LABELS[key],
                "current": _fmt_money(item["current"], sym),
                "previous": _fmt_money(item["previous"], sym),
                "change": _fmt_money(c, sym),
                "rate": _fmt_rate(item["rate"]),
                "change_class": "up" if c > 0 else ("down" if c < 0 else ""),
            }
        )

    chart_titles = {
        "dashboard": "NOVITA 成本综合看板",
    }

    return {
        "report_date": metrics.report_date.isoformat(),
        "period_start": metrics.current_period.start.isoformat(),
        "period_end": metrics.current_period.end.isoformat(),
        "currency": metrics.currency,
        "days": metrics.current_period.days,
        "overview_rows": overview_rows,
        "mom_rows": mom_rows,
        "charts": [(chart_titles[k], _img_to_base64(v)) for k, v in charts.items()],
    }


def generate_html_report(metrics: ReportMetrics, charts: dict[str, Path], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    context = build_report_context(metrics, charts)
    html = HTML_TEMPLATE.render(**context)
    path = output_dir / f"novita_report_{metrics.report_date.isoformat()}.html"
    path.write_text(html, encoding="utf-8")
    return path


def generate_markdown_summary(metrics: ReportMetrics) -> str:
    sym = metrics.currency_symbol
    lines = [
        f"📊 NOVITA 成本日报 | {metrics.report_date}",
        f"统计区间：{metrics.current_period.start} ~ {metrics.current_period.end}（{metrics.current_period.days} 天）｜单位：{metrics.currency}",
        "",
        "【当月数据概览】",
        "指标 | 当月数据 | 上月同期 | 环比 | 环比率",
    ]
    for item in metrics.overview:
        lines.append(
            f"{item['label']} | {_fmt_money(item['current'], sym)} | "
            f"{_fmt_money(item['previous'], sym)} | {_fmt_money(item['change'], sym)} | {_fmt_rate(item['rate'])}"
        )
    lines.extend(
        [
            "",
            "【分项环比明细】",
            "分项 | 当月同期 | 上月同期 | 环比 | 环比率",
        ]
    )
    for key in COST_COLUMNS:
        item = metrics.mom_changes[key]
        lines.append(
            f"{CATEGORY_LABELS[key]} | {_fmt_money(item['current'], sym)} | "
            f"{_fmt_money(item['previous'], sym)} | {_fmt_money(item['change'], sym)} | {_fmt_rate(item['rate'])}"
        )
    lines.append("")
    lines.append(f"_生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")
    return "\n".join(lines)
