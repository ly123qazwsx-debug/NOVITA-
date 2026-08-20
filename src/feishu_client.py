"""飞书 Open API 客户端。"""

from __future__ import annotations

import time
from typing import Any

import requests


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
