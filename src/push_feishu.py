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
    upload_error: str = "",
) -> dict[str, Any]:
    """构建飞书交互卡片：先发指定模版文字，再附图。"""
    image_keys = image_keys or {}
    brief = format_daily_brief(metrics, extra_notes)

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {"tag": "plain_text", "content": brief},
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
                "mode": "fit_horizontal",
                "compact_width": False,
            }
        )

    if not image_keys:
        reason = upload_error or "未拿到 image_key"
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**看板图未发到群里。** 图已在 GitHub Actions 产物里生成，但飞书上传失败：{reason}\n"
                        "请在开放平台给应用开启「机器人」能力，并开通权限 `im:resource`，创建版本发布后再跑一次。"
                    ),
                },
            }
        )

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"NOVITA（截止到{metrics.current_period.end.month}月{metrics.current_period.end.day}号）"},
            "template": "blue",
        },
        "elements": elements,
    }


def _upload_charts(client: FeishuClient, charts: dict[str, Path]) -> tuple[dict[str, str], str]:
    keys: dict[str, str] = {}
    errors: list[str] = []
    for name, path in charts.items():
        try:
            keys[name] = client.upload_image(str(path))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
            print(f"上传图表 {name} 失败: {exc}")
    return keys, "；".join(errors)


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
    brief = format_daily_brief(metrics, extra_notes)
    image_keys: dict[str, str] = {}
    upload_error = ""
    if client is not None:
        try:
            image_keys, upload_error = _upload_charts(client, charts)
        except Exception as exc:  # noqa: BLE001
            upload_error = str(exc)
            print(f"图表上传跳过: {exc}")

    sent = False
    if receive_id and client is not None:
        client.send_app_message(
            receive_id,
            "text",
            {"text": brief},
            receive_id_type,
        )
        sent = True
        print(f"已通过应用消息发送日报到 {receive_id_type}:{receive_id}")
        img_key = image_keys.get("dashboard")
        if img_key:
            client.send_app_message(
                receive_id,
                "image",
                {"image_key": img_key},
                receive_id_type,
            )

    if webhook_url and "xxxx" not in webhook_url:
        sender = client or FeishuClient("webhook-only", "webhook-only")
        try:
            sender.send_webhook_message(
                webhook_url,
                _attach_sign({"msg_type": "text", "content": {"text": brief}}, webhook_secret),
            )
            sent = True
            print("已通过 Webhook 推送日报正文")
        except Exception as exc:  # noqa: BLE001
            print(f"日报文本推送失败: {exc}")
            raise

        img_key = image_keys.get("dashboard")
        if img_key:
            try:
                sender.send_webhook_message(
                    webhook_url,
                    _attach_sign({"msg_type": "image", "content": {"image_key": img_key}}, webhook_secret),
                )
                print("已通过 Webhook 推送看板图片")
            except Exception as exc:  # noqa: BLE001
                print(f"图片 Webhook 失败: {exc}")
        elif upload_error:
            sender.send_webhook_message(
                webhook_url,
                _attach_sign(
                    {"msg_type": "text", "content": {"text": f"看板图未发出：{upload_error}"}},
                    webhook_secret,
                ),
            )

    if not sent:
        raise RuntimeError("未配置 FEISHU_WEBHOOK_URL 或 FEISHU_RECEIVE_ID，无法推送")
