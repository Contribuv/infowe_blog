"""OpenAI 兼容的 chat/completions 客户端（多服务商）。"""

from __future__ import annotations

import json
import re
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
    content = str(content or "").strip()
    if not content and reasoning:
        # 部分中转模型把全部输出塞进 reasoning_content，content 为空；
        # 这时用 reasoning 兜底，parse_action 会从里面找 JSON。
        content = str(reasoning)
        meta["from_reasoning"] = True
    return True, content, meta


def stream_chat(messages: list[dict], temperature: float | None = None,
                max_tokens: int | None = None) -> "Iterator[tuple[str, object]]":
    """流式对话：依次产出 ("reasoning", 增量)、("content", 增量)、("done", meta)。

    出错时产出 ("error", 错误文案)。调用方据此实时渲染推理与正文。
    """
    cfg = config.get()
    profile = config.active_profile()
    if not profile:
        yield "error", "还没有添加模型，请先到「模型管理」添加接口和 API Key"
        return
    base_url = str(profile.get("base_url") or "").strip()
    api_key = str(profile.get("api_key") or "").strip()
    model = str(profile.get("model") or "").strip()
    if not base_url or not api_key or not model:
        yield "error", f"{profile.get('name') or '当前接口'} 尚未配置接口地址 / API Key / 模型"
        return

    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(cfg.get("temperature") if temperature is None else temperature),
        "max_tokens": int(cfg.get("max_tokens") if max_tokens is None else max_tokens),
        "stream": True,
    }
    started = time.time()
    meta = {"provider": profile.get("id"), "model": model}
    try:
        resp = requests.post(
            _endpoint(base_url),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=(15, int(cfg.get("timeout") or 120)),
            stream=True,
        )
    except requests.RequestException as exc:
        yield "error", f"请求失败：{exc}"
        return

    if resp.status_code >= 400:
        detail = resp.text[:300]
        yield "error", f"接口返回 HTTP {resp.status_code}：{detail}"
        return

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage: dict = {}
    try:
        for raw in resp.iter_lines(decode_unicode=False):
            if not raw:
                continue
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if chunk.get("model"):
                meta["model"] = str(chunk["model"])
            if isinstance(chunk.get("usage"), dict):
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or choices[0].get("message") or {}
            piece = delta.get("reasoning_content") or delta.get("reasoning")
            if piece:
                reasoning_parts.append(str(piece))
                yield "reasoning", str(piece)
            piece = delta.get("content")
            if piece:
                content_parts.append(str(piece))
                yield "content", str(piece)
    except requests.RequestException as exc:
        yield "error", f"连接中断：{exc}"
        return
    finally:
        resp.close()

    meta["elapsed_ms"] = int((time.time() - started) * 1000)
    if usage:
        meta["usage"] = usage
    text = "".join(content_parts).strip()
    reasoning = "".join(reasoning_parts).strip()
    if not text and reasoning:
        text = reasoning
        meta["from_reasoning"] = True
    if reasoning:
        meta["reasoning"] = reasoning[:6000]
    yield "done", {"text": text, "meta": meta}


def _json_partial_string(src: str) -> str:
    """尽力解析 JSON 字符串的已知前缀（流式输出时内容可能还没写完）。"""
    out: list[str] = []
    i = 0
    length = len(src)
    simple = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "\\": "\\", "/": "/"}
    while i < length:
        ch = src[i]
        if ch == '"':
            break
        if ch == "\\":
            if i + 1 >= length:
                break  # 转义符刚到，等下一个分片
            nxt = src[i + 1]
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if nxt == "u":
                hexs = src[i + 2:i + 6]
                if len(hexs) < 4:
                    break
                try:
                    out.append(chr(int(hexs, 16)))
                except ValueError:
                    break
                i += 6
                continue
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def partial_reply_text(raw: str) -> str:
    """从流式累积的模型输出里取出「已经生成的回复正文」。

    约定 reply 动作形如 {"type":"reply","content":"..."}；普通纯文本则原样返回。
    还没进入 content 字段时返回空串，调用方据此决定要不要往前端推送。
    """
    text = raw or ""
    stripped = text.lstrip()
    if stripped and not stripped.startswith("{"):
        return stripped
    match = re.search(r'\{\s*"type"\s*:\s*"reply"\s*,\s*"content"\s*:\s*"', text)
    if not match:
        return ""
    return _json_partial_string(text[match.end():])


def parse_action(text: str) -> dict | None:
    """从模型输出里取出 JSON 动作；兼容 ```json、前后废话和 reasoning 草稿。"""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass

    # 逐候选解析：只认 {"type": ...} 开头的 JSON，raw_decode 能处理嵌套
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{\s*"type"', raw):
        try:
            data, _ = decoder.raw_decode(raw[match.start():])
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("type"):
            return data
    return None
