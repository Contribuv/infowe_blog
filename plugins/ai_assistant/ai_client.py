"""OpenAI 兼容的 chat/completions 客户端。

不引入新依赖，直接用 requests；DeepSeek / OpenAI / 通义 / 智谱等
只要兼容 `/chat/completions` 就能用同一套配置。
"""

from __future__ import annotations

import json

import requests

from . import config


def _endpoint(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def chat(messages: list[dict], temperature: float | None = None, max_tokens: int | None = None,
         timeout: int | None = None) -> tuple[bool, str, dict]:
    """返回 (ok, content, usage)。任何失败都返回 ok=False 和错误文本。"""
    cfg = config.get()
    base_url = str(cfg.get("base_url") or "").strip()
    api_key = str(cfg.get("api_key") or "").strip()
    model = str(cfg.get("model") or "").strip()
    if not base_url or not api_key or not model:
        return False, "AI 助手尚未配置接口地址 / API Key / 模型", {}

    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(cfg.get("temperature") if temperature is None else temperature),
        "max_tokens": int(cfg.get("max_tokens") if max_tokens is None else max_tokens),
    }
    try:
        resp = requests.post(
            _endpoint(base_url),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=int(cfg.get("timeout") or (timeout or 60)),
        )
    except requests.RequestException as exc:
        return False, f"请求失败：{exc}", {}

    if resp.status_code >= 400:
        detail = resp.text[:300]
        return False, f"接口返回 HTTP {resp.status_code}：{detail}", {}
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return False, "接口返回格式不正确", {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return True, str(content or ""), usage


def parse_action(text: str) -> dict | None:
    """从模型输出里取出 JSON 动作；兼容 ```json 包裹和前后废话。"""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
