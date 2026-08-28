"""推送 NOVITA / AWS 日报到飞书。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path
from typing import Any

from .aws_insights import format_aws_brief
from .aws_metrics import AwsReportMetrics
from .insights import format_daily_brief
from .feishu_client import FeishuClient
from .metrics import ReportMetrics


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


def _send_brief_and_images(
    client: FeishuClient | None,
    brief: str,
    charts: dict[str, Path],
    *,
    webhook_url: str,
    webhook_secret: str,
    receive_id: str,
    receive_id_type: str,
    title: str,
) -> None:
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
        client.send_app_message(receive_id, "text", {"text": brief}, receive_id_type)
        sent = True
        print(f"已通过应用消息发送 {title} 到 {receive_id_type}:{receive_id}")
        for name in charts:
            img_key = image_keys.get(name)
            if img_key:
                client.send_app_message(receive_id, "image", {"image_key": img_key}, receive_id_type)

    if webhook_url and "xxxx" not in webhook_url:
        sender = client or FeishuClient("webhook-only", "webhook-only")
        sender.send_webhook_message(
            webhook_url,
            _attach_sign({"msg_type": "text", "content": {"text": brief}}, webhook_secret),
        )
        sent = True
        print(f"已通过 Webhook 推送 {title} 正文")

        for name in charts:
            img_key = image_keys.get(name)
            if img_key:
                try:
                    sender.send_webhook_message(
                        webhook_url,
                        _attach_sign({"msg_type": "image", "content": {"image_key": img_key}}, webhook_secret),
                    )
                    print(f"已通过 Webhook 推送 {title} 图片 {name}")
                except Exception as exc:  # noqa: BLE001
                    print(f"图片 Webhook 失败: {exc}")
            elif upload_error and name == next(iter(charts)):
                sender.send_webhook_message(
                    webhook_url,
                    _attach_sign({"msg_type": "text", "content": {"text": f"{title} 看板图未发出：{upload_error}"}}, webhook_secret),
                )

    if not sent:
        raise RuntimeError("未配置 FEISHU_WEBHOOK_URL 或 FEISHU_RECEIVE_ID，无法推送")


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
    _send_brief_and_images(
        client,
        brief,
        charts,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
        title="NOVITA",
    )


def push_aws_report(
    client: FeishuClient | None,
    metrics: AwsReportMetrics,
    charts: dict[str, Path],
    *,
    webhook_url: str = "",
    webhook_secret: str = "",
    receive_id: str = "",
    receive_id_type: str = "chat_id",
    watch_items: list[dict] | None = None,
) -> None:
    brief = format_aws_brief(metrics, watch_items)
    _send_brief_and_images(
        client,
        brief,
        charts,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
        title="AWS",
    )
