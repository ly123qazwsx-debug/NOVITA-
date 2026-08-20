"""推送 NOVITA 日报到飞书。"""

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


CHART_TITLES = {
    "dashboard": "NOVITA 成本综合看板",
}


def _sign_webhook(secret: str) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    sign = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    return timestamp, sign


def _attach_sign(payload: dict[str, Any], secret: str) -> dict[str, Any]:
    if secret:
        timestamp, sign = _sign_webhook(secret)
        payload["timestamp"] = timestamp
        payload["sign"] = sign
    return payload


def build_card(metrics: ReportMetrics, image_keys: dict[str, str] | None = None) -> dict[str, Any]:
    """构建飞书交互卡片。"""
    image_keys = image_keys or {}
    p = metrics.current_period

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"统计区间：**{p.start.month}.{p.start.day} – {p.end.month}.{p.end.day}**"
                    f"（已过 {p.days} 天）｜ 单位：{metrics.currency}\n"
                    "一张图包含：当月概览、分项每日趋势（对比上月）、环比率、明细表"
                ),
            },
        },
    ]

    for key, title in CHART_TITLES.items():
        img_key = image_keys.get(key)
        if not img_key:
            continue
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{title}**"}})
        elements.append(
            {
                "tag": "img",
                "img_key": img_key,
                "alt": {"tag": "plain_text", "content": title},
            }
        )

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"NOVITA 成本日报 {metrics.report_date}"},
            "template": "blue",
        },
        "elements": elements,
    }


def _upload_charts(client: FeishuClient, charts: dict[str, Path]) -> dict[str, str]:
    keys: dict[str, str] = {}
    for name, path in charts.items():
        try:
            keys[name] = client.upload_image(str(path))
        except Exception as exc:  # noqa: BLE001
            print(f"上传图表 {name} 失败: {exc}")
    return keys


def push_daily_report(
    client: FeishuClient,
    metrics: ReportMetrics,
    charts: dict[str, Path],
    *,
    webhook_url: str = "",
    webhook_secret: str = "",
    receive_id: str = "",
    receive_id_type: str = "chat_id",
) -> None:
    image_keys = {}
    if receive_id or webhook_url:
        try:
            image_keys = _upload_charts(client, charts)
        except Exception as exc:  # noqa: BLE001
            print(f"图表上传跳过: {exc}")

    card = build_card(metrics, image_keys)

    sent = False
    if receive_id:
        client.send_app_message(receive_id, "interactive", card, receive_id_type)
        sent = True
        print(f"已通过应用消息发送到 {receive_id_type}:{receive_id}")

    if webhook_url and "xxxx" not in webhook_url:
        payload = _attach_sign({"msg_type": "interactive", "card": card}, webhook_secret)
        try:
            client.send_webhook_message(webhook_url, payload)
            sent = True
            print("已通过 Webhook 推送到飞书群")
        except Exception as exc:  # noqa: BLE001
            print(f"卡片 Webhook 失败，改为纯文本: {exc}")
            text_payload = _attach_sign(
                {"msg_type": "text", "content": {"text": generate_markdown_summary(metrics)}},
                webhook_secret,
            )
            client.send_webhook_message(webhook_url, text_payload)
            sent = True
            print("已通过 Webhook 推送文本摘要")

    if not sent:
        raise RuntimeError("未配置 FEISHU_WEBHOOK_URL 或 FEISHU_RECEIVE_ID，无法推送")
