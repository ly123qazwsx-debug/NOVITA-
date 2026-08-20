"""飞书 Open API 客户端。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests


IMAGE_UPLOAD_HINTS = {
    234001: "请求参数无效（已按飞书文档带上文件名和 MIME 重试）。",
    234007: "应用未启用机器人能力。打开 https://open.feishu.cn/app → 应用能力 → 添加「机器人」→ 创建版本并发布。",
    234011: "飞书无法识别图片格式。",
    234006: "图片超过 10MB。",
    99991663: "应用缺少 im:resource 权限，请开通「获取与上传图片或文件资源」后发布。",
    99991672: "应用缺少 im:resource 权限，请开通「获取与上传图片或文件资源」后发布。",
}


def _explain_image_upload_error(http_status: int, data: dict[str, Any]) -> str:
    code = data.get("code")
    msg = data.get("msg") or data.get("message") or ""
    hint = IMAGE_UPLOAD_HINTS.get(code, "")
    parts = [f"HTTP {http_status}", f"code={code}", f"msg={msg}"]
    if hint:
        parts.append(hint)
    return "；".join(parts)


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: str | None = None
        self._token_expires_at = 0.0
        self.base_url = "https://open.feishu.cn/open-apis"

    def _get_tenant_access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        resp = requests.post(
            f"{self.base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

        self._token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200)
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_tenant_access_token()}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.request(method, url, headers=self._headers(), timeout=60, **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 API 错误 [{path}]: {data}")
        return data

    def get_wiki_node(self, wiki_token: str) -> dict[str, Any]:
        """通过 Wiki token 获取内嵌文档信息（含电子表格 token）。"""
        data = self._request(
            "GET",
            "/wiki/v2/spaces/get_node",
            params={"token": wiki_token},
        )
        return data["data"]["node"]

    def get_spreadsheet_meta(self, spreadsheet_token: str) -> dict[str, Any]:
        data = self._request(
            "GET",
            f"/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query",
        )
        return data["data"]

    def read_sheet_values(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        cell_range: str,
    ) -> list[list[Any]]:
        """读取指定工作表区域数据。"""
        range_notation = f"{sheet_id}!{cell_range}"
        data = self._request(
            "GET",
            f"/sheets/v2/spreadsheets/{spreadsheet_token}/values/{range_notation}",
            params={"valueRenderOption": "ToString", "dateTimeRenderOption": "FormattedString"},
        )
        return data["data"]["valueRange"].get("values") or []

    def find_sheet_id_by_title(self, spreadsheet_token: str, title: str) -> str:
        meta = self.get_spreadsheet_meta(spreadsheet_token)
        for sheet in meta.get("sheets", []):
            if sheet.get("title") == title:
                return sheet["sheet_id"]
        available = [s.get("title") for s in meta.get("sheets", [])]
        raise ValueError(f"未找到工作表 '{title}'，可用工作表: {available}")

    def send_webhook_message(self, webhook_url: str, payload: dict[str, Any]) -> None:
        resp = requests.post(webhook_url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None) and data.get("StatusCode") not in (0, None):
            raise RuntimeError(f"Webhook 推送失败: {data}")

    def upload_image(self, image_path: str) -> str:
        """上传图片，返回 image_key。失败时带上飞书原始错误，便于排查。"""
        from PIL import Image

        src = Path(image_path)
        if not src.exists() or src.stat().st_size == 0:
            raise RuntimeError(f"图表文件不存在或为空: {image_path}")

        jpeg_path = src.with_name(src.stem + "_feishu.jpg")
        Image.open(src).convert("RGB").save(jpeg_path, "JPEG", quality=85, optimize=True)
        candidates = [jpeg_path, src]
        last_error = ""

        for path in candidates:
            mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            with path.open("rb") as f:
                resp = requests.post(
                    f"{self.base_url}/im/v1/images",
                    headers=self._headers(),
                    files={"image": (path.name, f, mime)},
                    data={"image_type": "message"},
                    timeout=60,
                )
            try:
                data = resp.json()
            except ValueError:
                data = {"code": -1, "msg": resp.text[:400]}
            if resp.ok and data.get("code") == 0:
                print(f"已上传图表 {path.name} -> {data['data']['image_key']}")
                return data["data"]["image_key"]
            last_error = _explain_image_upload_error(resp.status_code, data)
            print(f"上传 {path.name} 失败: {last_error}")

        raise RuntimeError(last_error)

    def send_app_message(
        self,
        receive_id: str,
        msg_type: str,
        content: dict[str, Any],
        receive_id_type: str = "chat_id",
    ) -> None:
        import json

        self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            json={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
        )
