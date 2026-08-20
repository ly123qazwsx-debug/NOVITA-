"""推送 NOVITA 日报到飞书。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path
from typing import Any

from .insights import format_daily_brief
from .feishu_client import FeishuClient
from .metrics import ReportMetrics


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


def build_card(
    metrics: ReportMetrics,
    image_keys: dict[str, str] | None = None,
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    """构建飞书交互卡片：先发指定模版文字，再附图。"""
    image_keys = image_keys or {}
    brief = format_daily_brief(metrics, extra_notes)

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": brief},
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
            "title": {"tag": "plain_text", "content": f"NOVITA（截止到{metrics.current_period.end.month}月{metrics.current_period.end.day}号）"},
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
    client: FeishuClient | None,
    metrics: ReportMetrics,
    charts: dict[str, Path],
    *,
    webhook_url: str = "",
    webhook_secret: str = "",
    receive_id: str = "",
    receive_id_type: str = "chat_id",
    extra_notes: list[str] | None = None,
) -> None:
    image_keys: dict[str, str] = {}
    if client is not None:
        try:
            image_keys = _upload_charts(client, charts)
        except Exception as exc:  # noqa: BLE001
            print(f"图表上传跳过: {exc}")

    card = build_card(metrics, image_keys, extra_notes)

    sent = False
    if receive_id and client is not None:
        client.send_app_message(receive_id, "interactive", card, receive_id_type)
        sent = True
        print(f"已通过应用消息发送到 {receive_id_type}:{receive_id}")

    if webhook_url and "xxxx" not in webhook_url:
        sender = client or FeishuClient("webhook-only", "webhook-only")
        payload = _attach_sign({"msg_type": "interactive", "card": card}, webhook_secret)
        try:
            sender.send_webhook_message(webhook_url, payload)
            sent = True
            print("已通过 Webhook 推送到飞书群")
        except Exception as exc:  # noqa: BLE001
            print(f"卡片 Webhook 失败，改为纯文本: {exc}")
            text_payload = _attach_sign(
                {"msg_type": "text", "content": {"text": format_daily_brief(metrics, extra_notes)}},
                webhook_secret,
            )
            sender.send_webhook_message(webhook_url, text_payload)
            sent = True
            print("已通过 Webhook 推送文本摘要")

    if not sent:
        raise RuntimeError("未配置 FEISHU_WEBHOOK_URL 或 FEISHU_RECEIVE_ID，无法推送")
