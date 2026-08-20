"""推送报告到飞书群。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path
from typing import Any

from .feishu_client import FeishuClient
from .metrics import ReportMetrics
from .report import generate_markdown_summary


def _sign_webhook(secret: str) -> tuple[int, str]:
    timestamp = int(time.time())
    string_to_sign = f"{timestamp}\n{secret}"
    sign = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    return timestamp, sign


def push_text_summary(client: FeishuClient, webhook_url: str, metrics: ReportMetrics, secret: str = "") -> None:
    content = generate_markdown_summary(metrics)
    payload: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": content},
    }
    if secret:
        timestamp, sign = _sign_webhook(secret)
        payload["timestamp"] = str(timestamp)
        payload["sign"] = sign

    client.send_webhook_message(webhook_url, payload)


def push_rich_card(
    client: FeishuClient,
    webhook_url: str,
    metrics: ReportMetrics,
    chart_path: Path,
    secret: str = "",
) -> None:
    sym = metrics.currency_symbol
    total = metrics.mom_changes["total_with_fixed"]
    rate_text = "N/A" if total["rate"] != total["rate"] else f"{total['rate']:+.1f}%"

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**当月累计**：{sym}{total['current']:,.2f}\n"
                    f"**预计全月**：{sym}{metrics.forecast_month_total:,.2f}\n"
                    f"**今日消耗**：{sym}{metrics.today['total_with_fixed']:,.2f}\n"
                    f"**环比**：{sym}{total['change']:,.2f}（{rate_text}）"
                ),
            },
        },
    ]

    # 飞书 webhook 图片需先上传或使用 img_key；文本卡片更稳定
    payload: dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"NOVITA 成本日报 {metrics.report_date}"},
                "template": "blue",
            },
            "elements": elements,
        },
    }
    if secret:
        timestamp, sign = _sign_webhook(secret)
        payload["timestamp"] = str(timestamp)
        payload["sign"] = sign

    client.send_webhook_message(webhook_url, payload)
