"""AI 托管：评论审核/回复、友链回链检测、定时任务。"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import current_app

import db
from config import CACHE_DIR
from models import Comment, Link, Post, Project
from services import notify, plugins, settings, site_url

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
            # 敏感词文件支持 # 注释行（分类标题），只取非注释的词条
            words = [w.strip() for w in path.read_text(encoding="utf-8").splitlines()
                     if w.strip() and not w.strip().startswith("#")]
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
    """安全拦截：返回命中的敏感词，未命中返回空串。

    除原文直接匹配外，再做一次「去分隔符」归一化匹配：
    发帖人常在词中间插符号绕过过滤（如「习*近*平」「六-四」），
    把汉字/字母数字之间的符号和空白去掉后再比对，兜住这类变体。
    """
    content = str(text or "").lower()
    normalized = re.sub(
        r"([0-9a-z\u4e00-\u9fff])[^0-9a-z\u4e00-\u9fff]+(?=[0-9a-z\u4e00-\u9fff])",
        r"\1", content,
    )
    for word in _sensitive_words():
        if not word:
            continue
        low = word.lower()
        if low in content or low in normalized:
            return word
    return ""


def _enabled() -> bool:
    return plugins.enabled(KEY)


# 审核视角的元信息词：模型把「这条评论属于正常提问」这类判断写进了 reply 里，
# 出现在回复开头会像审核报告，必须裁掉
_REPLY_META_WORDS = (
    "审核", "这条评论", "该评论", "此评论", "评论内容", "此条评论",
    "判定", "判断", "属于正常", "正常提问", "正常的技术提问",
    "无违规", "未发现", "通过审核", "置信度",
    "灌水", "广告", "辱骂", "敏感内容", "垃圾",
)


def _clean_reply(text: str) -> str:
    """裁掉 AI 回复开头的「审核视角」开场白，只保留真正对访客说的话。

    模型在同一次调用里既做审核又写回复，容易把审核结论串进 reply
    （如「你好，这条评论属于正常的技术提问。……」。这里只裁剪开头连续
    含审核元信息的句子，正文中间正常提及不影响；裁空则原样返回，避免误伤。
    """
    reply = str(text or "").strip().strip('"').strip()
    if not reply:
        return ""
    # 去掉「回复：」「答：」之类前缀
    reply = re.sub(r"^(回复|答复|答)\s*[：:]\s*", "", reply)
    parts = re.split(r"(?<=[。！？!?；;])", reply)
    skip = 0
    for index, seg in enumerate(parts):
        if any(word in seg for word in _REPLY_META_WORDS):
            skip = index + 1
            continue
        break
    cleaned = "".join(parts[skip:]).strip()
    # 裁得太短说明可能误删了正文，退回原文
    if len(cleaned) < 15:
        return reply
    return cleaned


# ── 评论托管 ──────────────────────────────────────────────
def _in_reply_time_window(cfg: dict) -> bool:
    mode = str(cfg.get("comment_reply_time_mode") or "all").strip().lower()
    if mode == "all":
        return True
    try:
        hour = datetime.now().hour
    except Exception:
        return True
    if mode == "day":
        return 9 <= hour < 21
    if mode == "night":
        return hour >= 21 or hour < 9
    return True


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
            min_len = int(cfg.get("comment_min_length") or 10)
            max_len = int(cfg.get("comment_max_length") or 0)
            if len(content) < min_len:
                db.execute("UPDATE comments SET ai_state='skipped' WHERE id=?", (cid,))
                return
            if max_len > 0 and len(content) > max_len:
                db.execute("UPDATE comments SET ai_state='skipped' WHERE id=?", (cid,))
                return
            # 本地硬规则先拦：领导人、官员、政府敏感词直接拒绝，不交给模型判断
            blocked = _blocked_word(raw_content or content)
            if blocked:
                meta = json.dumps({"decision": "reject", "reason": f"命中敏感词：{blocked}"}, ensure_ascii=False)
                db.execute("UPDATE comments SET status='rejected', ai_state='done', ai_meta=? WHERE id=?", (meta, cid))
                return
            post = Post.get(int(comment.get("post_id") or 0)) if comment.get("post_id") else None
            project = Project.get(int(comment.get("project_id") or 0)) if comment.get("project_id") else None
            title = str((post or {}).get("title") or (project or {}).get("name") or "项目")
            excerpt = str((post or {}).get("excerpt") or (project or {}).get("description") or "")[:500]
            # 回复必须只基于当前文章正文：以前只喂标题/摘要，AI 容易自由发挥、答非所问。
            # 正文压成单行后截断 4000 字，既控制 token，也保留足够上下文。
            body = re.sub(r"\s+", " ", str((post or {}).get("content") or "")).strip()[:4000]
            context = body or excerpt

            prompt = (
                "你是博客评论审核助手，只能用简体中文。判断下面评论是否属于："
                "垃圾广告、辱骂攻击、无意义灌水、违法敏感内容。\n"
                "涉及中国国家领导人、国家官员、政府敏感话题、分裂国家、政治事件的内容，一律 reject。\n"
                "回复只能依据「当前内容正文」：正文没有提到的信息不要臆测、不要编造，"
                "确实没写就直说文章里没有提到；不要营销、不要推广站外内容。\n"
                "只返回 JSON：{\"decision\":\"approve|reject|review\",\"reason\":\"简短理由\","
                "\"reply\":\"给这条评论的回复，60-150字中文，必须紧扣当前内容正文\"}\n"
                "reply 的写法（重要）：\n"
                "- 你在扮演博主本人直接回答访客，语气自然，不要有客服腔。\n"
                "- 严禁输出审核结论或任何元信息，例如「这条评论属于正常的技术提问」"
                "「该评论无违规」「已通过审核」「内容正常」「根据正文…」这类句子。\n"
                "- 不要用「你好，这条评论…」开头，直接进入答复内容；"
                "需要称呼时直接说事，不要先复述自己在做什么判断。\n"
                "- reply 里只写对访客说的话，审核判断只能写进 decision 和 reason。\n"
                "- reply 严禁涉及国家领导人、政治、宗教、违法（毒品/赌博/诈骗/色情/枪爆）"
                "等敏感话题，即使评论原文提到，也只能礼貌回避、不复述不展开。\n"
                f"当前内容标题：{title}\n当前内容摘要：{excerpt}\n"
                f"当前内容正文（节选）：\n<<<\n{context}\n>>>\n"
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
            # 模型有时把审核结论写进 reply，这里裁掉开头的审核视角句子
            reply = _clean_reply(str(action.get("reply") or ""))
            meta = json.dumps({"decision": decision, "reason": reason}, ensure_ascii=False)

            if decision == "reject":
                db.execute("UPDATE comments SET status='rejected', ai_state='done', ai_meta=? WHERE id=?", (meta, cid))
                return
            if decision != "approve":
                db.execute("UPDATE comments SET ai_state='review', ai_meta=? WHERE id=?", (meta, cid))
                return

            # 兜底复检：即使模型判 approve，原文再过一遍安全拦截
            # （防模型漏判或变体绕过），命中敏感词直接拒绝，不放行
            final_hit = _blocked_word(content)
            if final_hit:
                meta = json.dumps({"decision": "reject", "reason": f"兜底拦截命中敏感词：{final_hit}"}, ensure_ascii=False)
                db.execute("UPDATE comments SET status='rejected', ai_state='done', ai_meta=? WHERE id=?", (meta, cid))
                return

            db.execute("UPDATE comments SET status='approved', ai_state='done', ai_meta=? WHERE id=?", (meta, cid))
            if cfg.get("comment_reply") and reply and not _blocked_word(reply) and _in_reply_time_window(cfg):
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
                if cfg.get("comment_reply_notify", True):
                    try:
                        comment_notify = str(settings.get_str("comment_notify", "0") or "0").lower()
                        if comment_notify in {"1", "on", "true", "yes"}:
                            parent_email = str(comment.get("email") or "").strip()
                            if parent_email and "@" in parent_email and not parent_email.lower().endswith("@qq.com"):
                                post = Post.get(int(comment.get("post_id") or 0))
                                title = str((post or {}).get("title") or "")
                                link = site_url.post_url(post) if post else site_url.base()
                                content_text = (
                                    f"你好，{comment.get('author') or '访客'}：\n\n"
                                    f"你在《{title}》的评论有了新的回复：\n\n"
                                    f"{reply}\n\n"
                                    f"查看原文：{link}#comment-{new_id}\n\n"
                                    "此邮件由系统自动发送，请勿直接回复。"
                                )
                                notify.send(parent_email, "[评论回复] " + (title or "博客评论"), content_text)
                    except Exception:
                        pass
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
