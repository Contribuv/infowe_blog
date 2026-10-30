"""AI 助手后台路由：模型管理、配置页、聊天页、聊天 API。"""

from __future__ import annotations

import json

import db
from flask import flash, jsonify, redirect, render_template, request, url_for

from services import auth
from services import plugins as plugins_service

from . import ai_client, config, tools

KEY = "ai_assistant"


def _save_ai_avatar(file) -> tuple[str, str]:
    """上传 AI 头像：居中裁方并缩到 144px，存 var/uploads/ai-avatar/。

    返回 (相对 URL, 错误信息)。透明图先铺白底再存 JPEG，避免透明区域发黑；
    保存新图后删除上一张自定义头像，避免 uploads 目录堆积。
    """
    from pathlib import Path

    from PIL import Image

    from config import UPLOADS_DIR

    try:
        img = Image.open(file.stream).convert("RGBA")
        w, h = img.size
        size = max(1, min(w, h))
        left, top = (w - size) // 2, (h - size) // 2
        img = img.crop((left, top, left + size, top + size)).resize((144, 144), Image.LANCZOS)
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        folder = Path(UPLOADS_DIR) / "ai-avatar"
        folder.mkdir(parents=True, exist_ok=True)
        import secrets as _secrets
        import time as _time
        # 时间戳 + 随机后缀：URL 每次必变，换头像后不会被浏览器缓存挡住
        name = f"avatar_{int(_time.time())}_{_secrets.token_hex(3)}.jpg"
        bg.save(folder / name, "JPEG", quality=85)
        old_url = str(config.get().get("ai_avatar") or "")
        if "/uploads/ai-avatar/" in old_url:
            old_name = old_url.split("/uploads/ai-avatar/", 1)[1].split("?", 1)[0]
            if old_name and old_name != name:
                (folder / old_name).unlink(missing_ok=True)
        return f"/uploads/ai-avatar/{name}", ""
    except Exception:
        return "", "不是有效的图片文件"


def _mask(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    return "****" + value[-4:] if len(value) > 4 else "****"


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

    # ── 模型管理 ──────────────────────────────────────────
    @auth.admin_required
    def ai_models():
        cfg = config.get()
        edit_id = (request.args.get("edit") or "").strip()
        edit = None
        for provider in cfg.get("providers") or []:
            if provider["id"] == edit_id:
                edit = provider
                break
        return render_template(
            "ai/models.html",
            providers=cfg.get("providers") or [],
            active=cfg.get("active") or "",
            edit=edit,
            masked={p["id"]: _mask(p.get("api_key")) for p in cfg.get("providers") or []},
            new_id=config.new_id(),
        )

    @auth.admin_required
    def ai_models_save():
        pid = (request.form.get("id") or "").strip() or config.new_id()
        old = next((p for p in config.get().get("providers") or [] if p["id"] == pid), {})
        new_key = (request.form.get("api_key") or "").strip()
        item = {
            "id": pid,
            "name": (request.form.get("name") or "").strip(),
            "base_url": (request.form.get("base_url") or "").strip(),
            "model": (request.form.get("model") or "").strip(),
            "api_key": new_key if new_key and not new_key.startswith("****") else old.get("api_key", ""),
        }
        if not item["name"] or not item["base_url"] or not item["model"]:
            flash("名称、接口地址、模型都要填", "error")
            return redirect(url_for("admin_plugin_ai_models"))
        config.save_provider(item)
        flash("模型已保存", "success")
        return redirect(url_for("admin_plugin_ai_models"))

    @auth.admin_required
    def ai_models_delete():
        pid = (request.form.get("id") or "").strip()
        if pid:
            config.delete_provider(pid)
            flash("模型已删除", "success")
        return redirect(url_for("admin_plugin_ai_models"))

    @auth.admin_required
    def ai_models_active():
        pid = (request.form.get("id") or "").strip()
        if pid and config.set_active(pid):
            flash("已切换当前模型", "success")
        return redirect(url_for("admin_plugin_ai_models"))

    # ── 配置 ──────────────────────────────────────────────
    @auth.admin_required
    def ai_config():
        cfg = config.get()
        profile = config.active_profile()
        return render_template(
            "ai/config.html",
            cfg=cfg,
            profile=profile,
            plugin=plugins_service.get(KEY),
            daily_calls=_daily_calls(),
        )

    @auth.admin_required
    def ai_config_save():
        old = config.get()
        data = dict(old)
        for key in ("temperature", "max_tokens", "timeout", "comment_min_length", "comment_max_length", "comment_daily_limit", "link_check_hours", "daily_call_limit"):
            if key in request.form:
                try:
                    data[key] = float(request.form.get(key)) if key == "temperature" else int(request.form.get(key))
                except (TypeError, ValueError):
                    pass
        for key in ("comment_moderation", "comment_reply", "comment_reply_notify", "link_moderation", "auto_execute"):
            data[key] = str(request.form.get(key, "")).lower() in {"1", "on", "true", "yes"}
        if "comment_reply_time_mode" in request.form:
            mode = str(request.form.get("comment_reply_time_mode") or "all").strip().lower()
            if mode not in {"all", "day", "night"}:
                mode = "all"
            data["comment_reply_time_mode"] = mode
        if "system_prompt" in request.form:
            data["system_prompt"] = request.form.get("system_prompt", "")
        identity_changed = False
        if "ai_name" in request.form:
            # 昵称留空时回退默认值，避免评论区出现无名 AI
            name = str(request.form.get("ai_name") or "").strip()[:20] or "AI 助手"
            if name != str(old.get("ai_name") or "AI 助手"):
                identity_changed = True
            data["ai_name"] = name
        if "ai_avatar" in request.form:
            url = str(request.form.get("ai_avatar") or "").strip()[:500]
            # 只接受图片链接或站内路径；缺协议时自动补 https
            if url and not url.startswith(("http://", "https://", "/")):
                url = "https://" + url
            if url != str(old.get("ai_avatar") or "").strip():
                identity_changed = True
            data["ai_avatar"] = url
        # 文件上传优先于链接输入：表单选了图片就用上传结果
        avatar_file = request.files.get("ai_avatar_file")
        if avatar_file and avatar_file.filename:
            url, err = _save_ai_avatar(avatar_file)
            if err:
                flash(f"头像上传失败：{err}", "error")
                # 上传失败不动现有头像：前端已清空链接框，不能被当成「恢复默认」
                data["ai_avatar"] = str(old.get("ai_avatar") or "")
            elif url:
                if url != str(old.get("ai_avatar") or ""):
                    identity_changed = True
                data["ai_avatar"] = url
        # 换成外链或恢复默认时，清掉上一张本地上传的头像文件，避免堆积
        new_url = str(data.get("ai_avatar") or "")
        old_url = str(old.get("ai_avatar") or "")
        if "/uploads/ai-avatar/" in old_url and "/uploads/ai-avatar/" not in new_url:
            from pathlib import Path as _Path

            from config import UPLOADS_DIR

            name = _Path(old_url.split("/uploads/ai-avatar/", 1)[1].split("?", 1)[0]).name
            if name:
                (_Path(UPLOADS_DIR) / "ai-avatar" / name).unlink(missing_ok=True)
        # 防呆：最长长度 ≤ 最短长度时，任何评论都会被跳过（AI 静默不工作），
        # 这类配置没有任何意义，直接按「不限」保存并明确提示，避免再次踩坑
        min_len = int(data.get("comment_min_length") or 0)
        max_len = int(data.get("comment_max_length") or 0)
        if max_len > 0 and max_len <= min_len:
            data["comment_max_length"] = 0
            flash("评论最长长度需大于最短长度，已按「不限」保存", "error")
        config.save(data)
        if identity_changed:
            # 昵称或头像变了：历史 AI 评论同步更新，避免新旧混排
            from . import jobs

            jobs.sync_ai_identity()
        flash("配置已保存", "success")
        return redirect(url_for("admin_plugin_ai_config"))

    # ── 聊天 ──────────────────────────────────────────────
    @auth.admin_required
    def ai_chat():
        convs = [dict(r) for r in db.query(
            "SELECT id, title, updated_at FROM ai_conversations ORDER BY updated_at DESC LIMIT 30"
        )]
        conv_id = request.args.get("c", type=int) or 0
        messages = []
        if conv_id:
            for row in db.query(
                "SELECT id, role, content, meta, created_at FROM ai_messages WHERE conversation_id=? ORDER BY id ASC",
                (conv_id,),
            ):
                item = dict(row)
                try:
                    item["meta"] = json.loads(item.get("meta") or "{}")
                except (TypeError, ValueError):
                    item["meta"] = {}
                messages.append(item)
        cfg = config.get()
        return render_template(
            "ai/chat.html",
            conversations=convs,
            conversation_id=conv_id,
            messages=messages,
            cfg=cfg,
            providers=config.available_providers(),
            active=cfg.get("active") or "",
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

        meta: dict = {}
        write_count = 0
        for _ in range(4):
            ok, text, meta = ai_client.chat(messages)
            if not ok:
                _add_message(conv_id, "assistant", text, meta)
                return jsonify({"conversation_id": conv_id, "reply": text, "error": True, "meta": meta})
            action = ai_client.parse_action(text)
            if action and action.get("type") == "tool":
                name = str(action.get("tool") or "")
                args = action.get("args") if isinstance(action.get("args"), dict) else {}
                if name in tools.READ_TOOLS:
                    result = tools.execute(name, args)
                    _add_message(conv_id, "tool", json.dumps(result, ensure_ascii=False), {"tool": name, **meta})
                    messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user", "content": "工具结果：" + json.dumps(result, ensure_ascii=False)[:6000]})
                    continue
                if name in tools.WRITE_TOOLS:
                    force = name in tools.FORCE_CONFIRM
                    # 「AI 回复评论」由 comment_reply 单独控制：它关闭时，
                    # 即使写操作自动执行开启，reply_comment 也转为逐条确认
                    auto_ok = cfg.get("auto_execute") and (
                        name != "reply_comment" or cfg.get("comment_reply")
                    )
                    if auto_ok and not force and write_count < 3:
                        write_count += 1
                        result = tools.execute(name, args)
                        _add_message(conv_id, "tool", json.dumps(result, ensure_ascii=False), {"tool": name, **meta})
                        messages.append({"role": "assistant", "content": text})
                        messages.append({"role": "user", "content": "工具结果：" + json.dumps(result, ensure_ascii=False)[:6000]})
                        continue
                    action_meta = {"tool": name, "args": args, **meta}
                    mid = _add_message(conv_id, "pending", text, action_meta)
                    return jsonify({
                        "conversation_id": conv_id,
                        "pending": {"id": mid, "tool": name, "args": args, "text": text, "meta": meta, "force": force},
                    })
            content = action.get("content") if action and action.get("type") == "reply" else text
            content = str(content or "").strip() or "（模型没有返回内容）"
            _add_message(conv_id, "assistant", content, meta)
            return jsonify({"conversation_id": conv_id, "reply": content, "meta": meta})

        fallback = "这一步没有完成，请换一种说法再试。"
        _add_message(conv_id, "assistant", fallback, meta)
        return jsonify({"conversation_id": conv_id, "reply": fallback, "meta": meta})

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

    @auth.admin_required
    def ai_api_conversation_delete():
        data = request.get_json(silent=True) or {}
        cid = int(data.get("id") or 0)
        if cid:
            db.execute("DELETE FROM ai_messages WHERE conversation_id=?", (cid,))
            db.execute("DELETE FROM ai_conversations WHERE id=?", (cid,))
        return jsonify({"ok": True})

    @auth.admin_required
    def ai_api_provider():
        data = request.get_json(silent=True) or {}
        pid = str(data.get("id") or "").strip()
        if not config.set_active(pid):
            return jsonify({"error": "模型不存在"}), 400
        profile = config.active_profile() or {}
        return jsonify({"ok": True, "active": pid, "model": profile.get("model")})

    app.add_url_rule(prefix + "/plugins/ai", "admin_plugin_ai_config", ai_config, methods=["GET"])
    app.add_url_rule(prefix + "/plugins/ai/save", "admin_plugin_ai_save", ai_config_save, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/models", "admin_plugin_ai_models", ai_models, methods=["GET"])
    app.add_url_rule(prefix + "/plugins/ai/models/save", "admin_plugin_ai_models_save", ai_models_save, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/models/delete", "admin_plugin_ai_models_delete", ai_models_delete, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/models/active", "admin_plugin_ai_models_active", ai_models_active, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/chat", "admin_plugin_ai_chat", ai_chat, methods=["GET"])
    app.add_url_rule(prefix + "/plugins/ai/api/chat", "admin_plugin_ai_api_chat", ai_api_chat, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/api/confirm", "admin_plugin_ai_api_confirm", ai_api_confirm, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/api/new", "admin_plugin_ai_api_new", ai_api_new, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/api/provider", "admin_plugin_ai_api_provider", ai_api_provider, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/ai/api/conversation/delete", "admin_plugin_ai_api_conversation_delete", ai_api_conversation_delete, methods=["POST"])
