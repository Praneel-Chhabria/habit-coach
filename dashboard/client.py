"""Talks to the Habit Coach backend."""

import os
from typing import List, Optional

import requests


class ApiError(Exception):
    pass


class Api:
    def __init__(self) -> None:
        self.base = os.environ.get("API_URL", "http://localhost:8001").rstrip("/")
        self.key = os.environ.get("API_KEY", "")

    def _call(self, method: str, path: str, **kwargs):
        try:
            r = requests.request(method, "%s/api%s" % (self.base, path), headers={"X-API-Key": self.key}, timeout=10, **kwargs)
        except requests.RequestException:
            raise ApiError("Cannot reach the backend at %s. Is it running?" % self.base)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = None
            raise ApiError(detail if isinstance(detail, str) else "The backend said no (%d)" % r.status_code)
        return r.json() if r.content else None

    def today(self) -> dict:
        return self._call("GET", "/today")

    def insights(self, days: int) -> dict:
        return self._call("GET", "/insights", params={"days": days})

    def reply(self, task_id: int, action: str) -> None:
        self._call("POST", "/tasks/%d/reply" % task_id, json={"action": action})

    def blocks(self) -> List[dict]:
        return self._call("GET", "/blocks")

    def save_blocks(self, rows: List[dict]) -> dict:
        return self._call("PUT", "/blocks", json=rows)

    def import_markdown(self, text: str) -> dict:
        return self._call("POST", "/blocks/import", json={"markdown": text})

    def reset_blocks(self) -> dict:
        return self._call("POST", "/blocks/reset")

    def settings(self) -> dict:
        return self._call("GET", "/settings")

    def save_settings(self, values: dict) -> dict:
        return self._call("PUT", "/settings", json=values)

    def test_message(self) -> None:
        self._call("POST", "/test-message")

    def messages(self, limit: int = 15) -> List[dict]:
        return self._call("GET", "/messages", params={"limit": limit})
