"""读者登录/注册的图形验证码（算术题 SVG）。

答案不写入客户端可读的 session，只存 HMAC 签名；校验时用恒定时间比较。
与后台管理登录的验证码机制一致（见 routes/auth.py），但作用于读者账号体系。
"""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets

from flask import current_app, session

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
    return question


def current_question() -> str:
    return str(session.get(SESSION_Q) or "")


def verify(answer: str) -> bool:
    nonce = session.get(SESSION_NONCE)
    sig = session.get(SESSION_SIG)
    clear()
    if not nonce or not sig:
        return False
    text = str(answer or "").strip()
    if not text.isdigit():
        return False
    try:
        return hmac.compare_digest(_sign(str(nonce), int(text)), str(sig))
    except (ValueError, TypeError):
        return False


def clear() -> None:
    session.pop(SESSION_NONCE, None)
    session.pop(SESSION_SIG, None)
    session.pop(SESSION_Q, None)
