"""AI 托管：评论审核/回复、友链回链检测、定时任务。"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import current_app

import db
from config import CACHE_DIR
from models import Comment, Link, Post
from services import notify, plugins, site_url

from . import ai_client, config

KEY = "ai_assistant"
_lock = threading.Lock()
_thread_started = False


_WORD_CACHE: dict = {"mtime": 0.0, "words": []}


def _sensitive_words() -> list[str]:
    """内置黑名单 + 后台 sensitive_words + 插件配置追加词。"""
    path = Path(__file__).with_name("sensitive.txt")
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    if _WORD_CACHE["mtime"] != mtime:
        try:
            words = [w.strip() for w in path.read_text(encoding="utf-8").splitlines() if w.strip()]
        except OSError:
            words = []
        _WORD_CACHE.update(mtime=mtime, words=words)
    words = list(_WORD_CACHE["words"])
    extra = str(config.get().get("extra_blocked_words") or "")
    for raw in extra.replace("，", ",").replace("\n", ",").split(","):
        word = raw.strip()
        if word:
            words.append(word)
    try:
        from services import settings
        for word in str(settings.get_str("sensitive_words", "") or "").replace("\n", ",").split(","):
            word = word.strip()
            if word:
                words.append(word)
    except Exception:
        pass
    return list(dict.fromkeys(words))


def _blocked_word(text: str) -> str:
    content = str(text or "").lower()
    for word in _sensitive_words():
        if word and word.lower() in content:
            return word
    return ""


def _enabled() -> bool:
    return plugins.enabled(KEY)


# ── 评论托管 ──────────────────────────────────────────────
def on_comment(payload: dict) -> None:
    if not _enabled():
        return
    cfg = config.get()
    if not cfg.get("comment_moderation"):
        return
    if payload.get("is_admin"):
        return
    cid = int(payload.get("id") or 0)
    if not cid:
        return
    raw = str(payload.get("raw_content") or "")
    app = current_app._get_current_object()
    threading.Thread(target=_process_comment, args=(app, cid, raw), daemon=True).start()


def _process_comment(app, cid: int, raw_content: str = "") -> None:
    with app.app_context():
        try:
            cfg = config.get()
            cur = db.execute(
                "UPDATE comments SET ai_state='running' WHERE id=? AND ai_state='idle'",
                (cid,),
            )
            if cur.rowcount == 0:
                return
            comment = Comment.get(cid)
            if not comment:
                return
            content = str(comment.get("content") or "").strip()
            if len(content) < int(cfg.get("comment_min_length") or 10):
                db.execute("UPDATE comments SET ai_state='skipped' WHERE id=?", (cid,))
                return
            # 本地硬规则先拦：领导人、官员、政府敏感词直接拒绝，不交给模型判断
            blocked = _blocked_word(raw_content or content)
            if blocked:
                meta = json.dumps({"decision": "reject", "reason": f"命中敏感词：{blocked}"}, ensure_ascii=False)
                db.execute("UPDATE comments SET status='rejected', ai_state='done', ai_meta=? WHERE id=?", (meta, cid))
                return
            post = Post.get(int(comment.get("post_id") or 0)) if comment.get("post_id") else None
            title = str((post or {}).get("title") or "项目")
            excerpt = str((post or {}).get("excerpt") or "")[:500]

            prompt = (
                "你是博客评论审核助手，只能用简体中文。判断下面评论是否属于："
                "垃圾广告、辱骂攻击、无意义灌水、违法敏感内容。\n"
                "涉及中国国家领导人、国家官员、政府敏感话题、分裂国家、政治事件的内容，一律 reject。\n"
                "只返回 JSON：{\"decision\":\"approve|reject|review\",\"reason\":\"简短理由\","
                "\"reply\":\"给这条评论的回复，50-150字中文，可结合文章内容，不要营销\"}\n"
                f"文章标题：{title}\n文章摘要：{excerpt}\n"
                f"评论作者：{comment.get('author')}\n评论内容：\n<<<\n{content[:2000]}\n>>>"
            )
            ok, text, _ = ai_client.chat(
                [{"role": "system", "content": "你是中文内容审核助手，只输出 JSON。"},
                 {"role": "user", "content": prompt}],
                temperature=0.2,
            )
            if not ok:
                db.execute("UPDATE comments SET ai_state='review', ai_meta=? WHERE id=?",
                           (json.dumps({"error": text[:300]}, ensure_ascii=False), cid))
                return
            action = ai_client.parse_action(text) or {}
            decision = str(action.get("decision") or "review")
            reason = str(action.get("reason") or "")[:300]
            reply = str(action.get("reply") or "").strip()
            meta = json.dumps({"decision": decision, "reason": reason}, ensure_ascii=False)

            if decision == "reject":
                db.execute("UPDATE comments SET status='rejected', ai_state='done', ai_meta=? WHERE id=?", (meta, cid))
                return
            if decision != "approve":
                db.execute("UPDATE comments SET ai_state='review', ai_meta=? WHERE id=?", (meta, cid))
                return

            db.execute("UPDATE comments SET status='approved', ai_state='done', ai_meta=? WHERE id=?", (meta, cid))
            if cfg.get("comment_reply") and reply and not _blocked_word(reply):
                profile = config.active_profile()
                avatar = config.provider_avatar(profile)
                new_id = Comment.save(
                    comment.get("post_id"), "AI 助手", "", "", "", reply,
                    cid, 0, "", "", "approved", comment.get("project_id"), "",
                    is_ai=1,
                )
                reply_meta = {
                    "avatar": avatar,
                    "provider": (profile or {}).get("id"),
                    "model": (profile or {}).get("model"),
                }
                db.execute("UPDATE comments SET ai_meta=? WHERE id=?", (json.dumps(reply_meta, ensure_ascii=False), new_id))
                db.execute("UPDATE comments SET ai_meta=? WHERE id=?", (
                    json.dumps({"decision": "approve", "reason": reason, "ai_reply": new_id}, ensure_ascii=False), cid,
                ))
        except Exception:
            try:
                db.execute("UPDATE comments SET ai_state='review' WHERE id=?", (cid,))
            except Exception:
                pass


# ── 友链托管 ──────────────────────────────────────────────
def on_link(payload: dict) -> None:
    if not _enabled() or not config.get().get("link_moderation"):
        return
    email = str(payload.get("email") or "").strip()
    if not email:
        return
    name = str(payload.get("name") or "")
    url = str(payload.get("url") or "")
    site = site_url.base()
    text = (
        f"你好，{name}：\n\n"
        f"已收到你的友链申请。请先在贵站添加本站友链，添加后系统会自动审核：\n\n"
        f"站点名称：{settings.get_str('blog_name', '本站')}\n"
        f"站点地址：{site}\n\n"
        f"你提交的地址：{url}\n\n"
        "审核通过后会再发一封邮件通知。\n"
    )
    notify.send(email, "[友链申请] 请先添加本站友链", text)


def _site_host() -> str:
    from services import settings
    raw = settings.get_str("site_url", "").strip() or site_url.base()
    host = urlparse(raw).hostname or ""
    return host.lower().removeprefix("www.")


def _safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        ip = socket.gethostbyname(parsed.hostname)
        addr = ipaddress.ip_address(ip)
        return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved)
    except Exception:
        return False


def _has_backlink(url: str, host: str) -> bool:
    if not host or not _safe_url(url):
        return False
    try:
        resp = requests.get(
            url, timeout=8, stream=True,
            headers={"User-Agent": "infowe-link-check/1.0"},
            allow_redirects=True,
        )
        chunk = resp.raw.read(2 * 1024 * 1024, decode_content=True) or b""
        text = chunk.decode("utf-8", "ignore").lower()
        return host in text and "href" in text
    except requests.RequestException:
        return False


def check_pending_links() -> None:
    """检查待审核友链：对方页面出现本站链接即通过。"""
    if not _enabled() or not config.get().get("link_moderation"):
        return
    host = _site_host()
    if not host:
        return
    rows = db.query(
        "SELECT * FROM links WHERE status='pending' AND ai_state!='done' ORDER BY id ASC LIMIT 20"
    )
    for row in rows:
        link = dict(row)
        url = str(link.get("url") or "")
        meta = {}
        try:
            meta = json.loads(link.get("ai_meta") or "{}")
        except (TypeError, ValueError):
            meta = {}
        attempts = int(meta.get("attempts") or 0) + 1
        if _has_backlink(url, host):
            db.execute(
                "UPDATE links SET status='approved', ai_state='done', ai_meta=? WHERE id=?",
                (json.dumps({"checked": True, "attempts": attempts, "backlink": True}, ensure_ascii=False), link["id"]),
            )
            email = str(link.get("email") or "").strip()
            if email:
                notify.send(
                    email,
                    "[友链] 已通过审核",
                    f"你好，{link.get('name')}：\n\n已在贵站检测到本站友链，申请已自动通过。\n{site_url.base()}\n",
                )
            continue
        hours = int(config.get().get("link_check_hours") or 72)
        if attempts * 10 >= hours * 60:
            db.execute(
                "UPDATE links SET ai_state='review', ai_meta=? WHERE id=?",
                (json.dumps({"checked": True, "attempts": attempts, "backlink": False}, ensure_ascii=False), link["id"]),
            )
        else:
            db.execute(
                "UPDATE links SET ai_meta=? WHERE id=?",
                (json.dumps({"checked": True, "attempts": attempts, "backlink": False}, ensure_ascii=False), link["id"]),
            )


# ── 定时任务 ──────────────────────────────────────────────
def start_scheduler(app) -> None:
    global _thread_started
    with _lock:
        if _thread_started:
            return
        _thread_started = True

    def loop() -> None:
        try:
            import fcntl
        except ImportError:
            return
        time.sleep(30)
        while True:
            try:
                lock_path = Path(CACHE_DIR) / "ai_link_check.lock"
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                with app.app_context():
                    with open(lock_path, "w") as fh:
                        try:
                            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except OSError:
                            pass
                        else:
                            check_pending_links()
            except Exception:
                app.logger.exception("ai link check failed")
            time.sleep(600)

    threading.Thread(target=loop, daemon=True, name="ai-link-check").start()
