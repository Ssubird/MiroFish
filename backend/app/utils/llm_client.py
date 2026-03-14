"""LLM client for OpenAI-compatible chat completion APIs."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from ..config import Config
from .logger import get_logger


DEFAULT_TIMEOUT_SECONDS = 120
ERROR_PREVIEW_CHARS = 800
DEFAULT_LLM_RETRY_COUNT = 2
DEFAULT_LLM_RETRY_BACKOFF_MS = 1500
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.SSLError,
    requests.exceptions.Timeout,
)

logger = get_logger("mirofish.llm_client")


class LLMClient:
    """Thin HTTP client for OpenAI-compatible providers."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        retry_count: int = DEFAULT_LLM_RETRY_COUNT,
        retry_backoff_ms: int = DEFAULT_LLM_RETRY_BACKOFF_MS,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = (base_url or Config.LLM_BASE_URL).rstrip("/")
        self.model = model or Config.LLM_MODEL_NAME
        self.retry_count = max(0, retry_count)
        self.retry_backoff_ms = max(0, retry_backoff_ms)
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

    def list_models(self) -> list[dict[str, Any]]:
        body = self._request_json("GET", "/models", json_mode=False)
        models = body.get("data", [])
        if not isinstance(models, list):
            raise ValueError(f"模型列表格式错误: {body}")
        filtered = [item for item in models if self._supports_openai(item)]
        return sorted(filtered, key=lambda item: str(item.get("id", "")))

    def probe_model(self, model: str) -> dict[str, Any]:
        probe_client = LLMClient(
            api_key=self.api_key,
            base_url=self.base_url,
            model=model,
            retry_count=self.retry_count,
            retry_backoff_ms=self.retry_backoff_ms,
        )
        payload = probe_client.chat_json(
            messages=[
                {"role": "system", "content": "只返回 JSON。"},
                {"role": "user", "content": f'返回 {{"ok": true, "model": "{model}"}}'},
            ],
            temperature=0.1,
            max_tokens=64,
        )
        return {"ok": bool(payload.get("ok")), "model": model, "response": payload}

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        payload = self._build_payload(messages, temperature, max_tokens, response_format)
        body = self._request_json("POST", "/chat/completions", payload=payload, json_mode=True)
        content = self._extract_content(body)
        return re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        cleaned_response = self._strip_code_fence(response)
        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM 返回的 JSON 无效: {cleaned_response}") from exc

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        json_mode: bool = True,
    ) -> dict[str, Any]:
        for attempt in range(self.retry_count + 1):
            try:
                response = self._send_request(method, path, payload, json_mode)
            except RETRYABLE_EXCEPTIONS as exc:
                if not self._can_retry(attempt):
                    raise
                self._log_retry(method, path, attempt, str(exc))
                self._sleep_before_retry(attempt)
                continue
            if self._should_retry_response(response, method, path, attempt):
                self._sleep_before_retry(attempt)
                continue
            return self._parse_body(response)
        raise RuntimeError(f"LLM 请求失败: 未能完成 {method} {path}")

    def _send_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        json_mode: bool,
    ) -> requests.Response:
        return requests.request(
            method=method,
            url=f"{self.base_url}{path}",
            headers=self._build_headers(json_mode=json_mode),
            json=payload,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

    def _build_headers(self, json_mode: bool) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "MiroFish-Backend/1.0",
            "Connection": "close",
        }
        if json_mode:
            headers["Content-Type"] = "application/json"
        return headers

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        return payload

    def _should_retry_response(
        self,
        response: requests.Response,
        method: str,
        path: str,
        attempt: int,
    ) -> bool:
        status_code = response.status_code
        if status_code < 500 or not self._can_retry(attempt):
            return False
        detail = f"HTTP {status_code} {self._preview_error(response.text)}"
        self._log_retry(method, path, attempt, detail)
        return True

    def _parse_body(self, response: requests.Response) -> dict[str, Any]:
        if response.ok:
            return response.json()
        preview = self._preview_error(response.text)
        status_code = response.status_code
        if status_code == 429:
            raise RuntimeError(f"LLM 请求失败: HTTP 429 {preview}")
        if status_code == 520:
            raise RuntimeError(f"LLM 请求失败: HTTP 520 上游 Cloudflare/源站错误 {preview}")
        if status_code >= 500:
            raise RuntimeError(f"LLM 请求失败: HTTP {status_code} 上游服务异常 {preview}")
        raise RuntimeError(f"LLM 请求失败: HTTP {status_code} {preview}")

    def _extract_content(self, body: dict[str, Any]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError(f"LLM 响应缺少 choices: {body}")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"LLM 响应缺少 message.content: {body}")
        return content

    def _strip_code_fence(self, response: str) -> str:
        cleaned_response = response.strip()
        cleaned_response = re.sub(r"^```(?:json)?\s*\n?", "", cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r"\n?```\s*$", "", cleaned_response)
        return cleaned_response.strip()

    def _preview_error(self, text: str) -> str:
        plain = re.sub(r"<[^>]+>", " ", text)
        compact = " ".join(plain.split())
        if len(compact) > ERROR_PREVIEW_CHARS:
            return compact[:ERROR_PREVIEW_CHARS].rstrip() + "..."
        return compact

    def _supports_openai(self, item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        endpoint_types = item.get("supported_endpoint_types")
        if not isinstance(endpoint_types, list):
            return True
        return "openai" in endpoint_types

    def _can_retry(self, attempt: int) -> bool:
        return attempt < self.retry_count

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_ms <= 0:
            return
        time.sleep(self.retry_backoff_ms * (attempt + 1) / 1000)

    def _log_retry(self, method: str, path: str, attempt: int, detail: str) -> None:
        logger.warning(
            "LLM 瞬时异常，准备重试 %s %s，第 %s/%s 次补偿：%s",
            method,
            path,
            attempt + 1,
            self.retry_count,
            detail,
        )
