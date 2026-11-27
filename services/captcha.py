"""读者登录/注册的图形验证码（算术题 SVG）。

答案不写入客户端可读的 session，只存 HMAC 签名；校验时用恒定时间比较。
与后台管理登录的验证码机制一致（见 routes/auth.py），但作用于读者账号体系。
"""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
import time

from flask import current_app, session

import db

SESSION_NONCE = "reader_captcha_nonce"
SESSION_SIG = "reader_captcha_sig"
SESSION_Q = "reader_captcha_q"


def _sign(nonce: str, answer: int) -> str:
    key = (current_app.secret_key or "").encode("utf-8")
    return hmac.new(key, f"{nonce}:{answer}".encode("utf-8"), hashlib.sha256).hexdigest()


def new_question() -> str:
    """生成一道加法题，题干入 session 供展示，答案只留签名。返回题干文本。"""
    a, b = random.randint(1, 9), random.randint(2, 9)
    nonce = secrets.token_hex(8)
    question = f"{a} + {b}"
    session[SESSION_NONCE] = nonce
    session[SESSION_SIG] = _sign(nonce, a + b)
    session[SESSION_Q] = question
    # 服务端登记一次性令牌，过期记录顺手清掉
    now = int(time.time())
    db.execute("DELETE FROM captcha_tokens WHERE expires_at < ?", (now,))
    db.execute(
        "INSERT INTO captcha_tokens (nonce, expires_at) VALUES (?, ?)",
        (nonce, now + 300),
    )
    return question


def current_question() -> str:
    return str(session.get(SESSION_Q) or "")


def verify(answer: str) -> bool:
    nonce = session.get(SESSION_NONCE)
    sig = session.get(SESSION_SIG)
    clear()
    if not nonce or not sig:
        return False
    # 服务端一次性校验：旧 cookie 重放时 nonce 已消费，直接拒绝
    row = db.one(
        "SELECT nonce FROM captcha_tokens WHERE nonce=? AND used_at='' AND expires_at>?",
        (str(nonce), int(time.time())),
    )
    if not row:
        return False
    text = str(answer or "").strip()
    if not text.isdigit():
        return False
    try:
        ok = hmac.compare_digest(_sign(str(nonce), int(text)), str(sig))
    except (ValueError, TypeError):
        ok = False
    if ok:
        db.execute(
            "UPDATE captcha_tokens SET used_at=? WHERE nonce=?",
            (db.now(), str(nonce)),
        )
    return ok


def clear() -> None:
    session.pop(SESSION_NONCE, None)
    session.pop(SESSION_SIG, None)
    session.pop(SESSION_Q, None)
