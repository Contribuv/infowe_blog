"""OpenAI 兼容的 chat/completions 客户端（多服务商）。"""

from __future__ import annotations

import json
import time

import requests

from . import config


def _endpoint(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def chat(messages: list[dict], temperature: float | None = None, max_tokens: int | None = None,
         timeout: int | None = None) -> tuple[bool, str, dict]:
    """返回 (ok, content, meta)。meta 含 usage / model / elapsed_ms。"""
    cfg = config.get()
    profile = config.active_profile()
    if not profile:
        return False, "还没有添加模型，请先到「模型管理」添加接口和 API Key", {}
    base_url = str(profile.get("base_url") or "").strip()
    api_key = str(profile.get("api_key") or "").strip()
    model = str(profile.get("model") or "").strip()
    if not base_url or not api_key or not model:
        return False, f"{profile.get('name') or '当前接口'} 尚未配置接口地址 / API Key / 模型", {
            "provider": profile.get("id"),
            "model": model,
        }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(cfg.get("temperature") if temperature is None else temperature),
        "max_tokens": int(cfg.get("max_tokens") if max_tokens is None else max_tokens),
    }
    started = time.time()
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
        return False, f"请求失败：{exc}", {
            "provider": profile.get("id"),
            "model": model,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    elapsed = int((time.time() - started) * 1000)
    meta = {"provider": profile.get("id"), "model": model, "elapsed_ms": elapsed}
    if resp.status_code >= 400:
        detail = resp.text[:300]
        return False, f"接口返回 HTTP {resp.status_code}：{detail}", meta
    try:
        data = resp.json()
        message = data["choices"][0]["message"]
        content = message.get("content")
    except (ValueError, KeyError, IndexError, TypeError):
        return False, "接口返回格式不正确", meta

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    meta["usage"] = usage
    meta["model"] = str(data.get("model") or model)
    reasoning = message.get("reasoning_content") or message.get("reasoning")
    if reasoning:
        meta["reasoning"] = str(reasoning)[:6000]
    return True, str(content or ""), meta


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
