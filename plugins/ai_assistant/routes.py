"""AI 助手后台路由：配置页、聊天页、聊天 API。"""

from __future__ import annotations

import json

import db
from flask import jsonify, redirect, render_template, request, url_for

from services import auth
from services import plugins as plugins_service

from . import ai_client, config, tools

KEY = "ai_assistant"


def _conv_title(text: str) -> str:
    text = (text or "").strip().replace("\n", " ")
    return (text[:28] + "…") if len(text) > 28 else (text or "新对话")


def _new_conversation(title: str) -> int:
    return db.insert(
        "INSERT INTO ai_conversations (title, created_at, updated_at) VALUES (?, datetime('now','localtime'), datetime('now','localtime'))",
        (_conv_title(title),),
    )


def _add_message(conv_id: int, role: str, content: str, meta: dict | None = None) -> int:
    mid = db.insert(
        "INSERT INTO ai_messages (conversation_id, role, content, meta, created_at) VALUES (?,?,?,?,datetime('now','localtime'))",
        (conv_id, role, content or "", json.dumps(meta or {}, ensure_ascii=False)),
    )
    db.execute("UPDATE ai_conversations SET updated_at=datetime('now','localtime') WHERE id=?", (conv_id,))
    return mid


def _history(conv_id: int, limit: int = 20) -> list[dict]:
    rows = db.query(
        "SELECT role, content FROM ai_messages WHERE conversation_id=? AND role IN ('user','assistant') "
        "ORDER BY id DESC LIMIT ?",
        (conv_id, limit),
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _daily_calls() -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM ai_messages WHERE role='assistant' AND date(created_at)=date('now','localtime')",
        (), 0,
    ) or 0)


def register(app) -> None:
    prefix = app.config.get("ADMIN_PREFIX", "/admin")

    @auth.admin_required
    def ai_config():
        cfg = config.get()
        key = str(cfg.get("api_key") or "")
        masked = ("****" + key[-4:]) if len(key) > 4 else ("****" if key else "")
        return render_template(
            "ai/config.html",
            cfg=cfg,
            masked_key=masked,
            plugin=plugins_service.get(KEY),
            daily_calls=_daily_calls(),
        )

    @auth.admin_required
    def ai_config_save():
        old = config.get()
        data = dict(old)
        for key in ("base_url", "model", "system_prompt"):
            if key in request.form:
                data[key] = request.form.get(key, "").strip()
        for key in ("temperature", "max_tokens", "timeout", "comment_min_length", "comment_daily_limit", "link_check_hours", "daily_call_limit"):
            if key in request.form:
                try:
                    data[key] = float(request.form.get(key)) if key == "temperature" else int(request.form.get(key))
                except (TypeError, ValueError):
                    pass
        for key in ("comment_moderation", "comment_reply", "link_moderation"):
            data[key] = str(request.form.get(key, "")).lower() in {"1", "on", "true", "yes"}
        new_key = (request.form.get("api_key") or "").strip()
        if new_key and not new_key.startswith("****"):
            data["api_key"] = new_key
        config.save(data)
        return redirect(url_for("admin_plugin_ai_config"))

    @auth.admin_required
    def ai_chat():
        convs = [dict(r) for r in db.query(
            "SELECT id, title, updated_at FROM ai_conversations ORDER BY updated_at DESC LIMIT 30"
        )]
        conv_id = request.args.get("c", type=int) or 0
        messages = []
        if conv_id:
            messages = [dict(r) for r in db.query(
                "SELECT id, role, content, meta, created_at FROM ai_messages WHERE conversation_id=? ORDER BY id ASC",
                (conv_id,),
            )]
        return render_template(
            "ai/chat.html",
            conversations=convs,
            conversation_id=conv_id,
            messages=messages,
            cfg=config.get(),
            daily_calls=_daily_calls(),
        )

    @auth.admin_required
    def ai_api_chat():
        data = request.get_json(silent=True) or {}
        message = str(data.get("message") or "").strip()
        if not message:
            return jsonify({"error": "消息不能为空"}), 400
        cfg = config.get()
        if _daily_calls() >= int(cfg.get("daily_call_limit") or 300):
            return jsonify({"error": "已达到今日 AI 调用上限，请到配置页调整"}), 429
        conv_id = int(data.get("conversation_id") or 0)
        if not conv_id:
            conv_id = _new_conversation(message)
        _add_message(conv_id, "user", message)

        history = _history(conv_id, 20)
        messages = [{"role": "system", "content": str(cfg.get("system_prompt") or "")}] + history
        if history and history[-1]["role"] != "user":
            messages.append({"role": "user", "content": message})

        for _ in range(4):
            ok, text, usage = ai_client.chat(messages)
            if not ok:
                _add_message(conv_id, "assistant", text)
                return jsonify({"conversation_id": conv_id, "reply": text, "error": True})
            action = ai_client.parse_action(text)
            if action and action.get("type") == "tool":
                name = str(action.get("tool") or "")
                args = action.get("args") if isinstance(action.get("args"), dict) else {}
                if name in tools.READ_TOOLS:
                    result = tools.execute(name, args)
                    _add_message(conv_id, "tool", json.dumps(result, ensure_ascii=False), {"tool": name})
                    messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user", "content": "工具结果：" + json.dumps(result, ensure_ascii=False)[:6000]})
                    continue
                if name in tools.WRITE_TOOLS:
                    meta = {"tool": name, "args": args}
                    mid = _add_message(conv_id, "pending", text, meta)
                    return jsonify({
                        "conversation_id": conv_id,
                        "pending": {"id": mid, "tool": name, "args": args, "text": text},
                    })
            content = action.get("content") if action and action.get("type") == "reply" else text
            content = str(content or "").strip() or "（模型没有返回内容）"
            _add_message(conv_id, "assistant", content)
            return jsonify({"conversation_id": conv_id, "reply": content})

        fallback = "这一步没有完成，请换一种说法再试。"
        _add_message(conv_id, "assistant", fallback)
        return jsonify({"conversation_id": conv_id, "reply": fallback})

    @auth.admin_required
    def ai_api_confirm():
        data = request.get_json(silent=True) or {}
        mid = int(data.get("id") or 0)
        row = db.one("SELECT * FROM ai_messages WHERE id=? AND role='pending'", (mid,))
        if not row:
            return jsonify({"error": "待确认操作不存在或已执行"}), 404
        try:
            meta = json.loads(row["meta"] or "{}")
        except (TypeError, ValueError):
            meta = {}
        name = str(meta.get("tool") or "")
        args = meta.get("args") if isinstance(meta.get("args"), dict) else {}
        if name not in tools.WRITE_TOOLS:
            return jsonify({"error": "操作不在白名单内"}), 400
        result = tools.execute(name, args)
        db.execute("UPDATE ai_messages SET role='tool', content=? WHERE id=?", (json.dumps(result, ensure_ascii=False), mid))
        _add_message(int(row["conversation_id"]), "assistant", result.get("message") or result.get("error") or "已执行")
        return jsonify({"result": result, "conversation_id": int(row["conversation_id"])})

    @auth.admin_required
    def ai_api_new():
        conv_id = _new_conversation("新对话")
        return jsonify({"conversation_id": conv_id})

    app.add_url_rule(prefix + "/plugins/ai", "admin_plugin_ai_config", ai_config, methods=["GET"])
    app.add_url_rule(prefix + "/plugins/ai/save", "admin_plugin_ai_save", ai_config_save, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/chat", "admin_plugin_ai_chat", ai_chat, methods=["GET"])
    app.add_url_rule(prefix + "/plugins/ai/api/chat", "admin_plugin_ai_api_chat", ai_api_chat, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/api/confirm", "admin_plugin_ai_api_confirm", ai_api_confirm, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/api/new", "admin_plugin_ai_api_new", ai_api_new, methods=["POST"])
