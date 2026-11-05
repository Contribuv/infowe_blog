"""评论者身份与改名验证码。

规则：
- 邮箱哈希是身份，昵称只是展示名；
- 同一邮箱换昵称必须选择「沿用曾用名」或完成邮箱验证码验证；
- 改名成功后同步该邮箱的历史评论昵称，保证前台展示统一。
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import db
from services import avatar, ratelimit

CODE_TTL = 600          # 验证码 10 分钟
TOKEN_TTL = 300         # 改名令牌 5 分钟
MAX_ATTEMPTS = 5        # 同一验证码最多尝试 5 次
PURPOSE = "rename"


def normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if re.fullmatch(r"\d{5,12}", value):
        value += "@qq.com"
    return value


def email_hash(email: str) -> str:
    return avatar.email_hash(normalize_email(email))


def get_row(email: str):
    value = email_hash(email)
    if not value:
        return None
    return db.one(
        "SELECT * FROM comment_identities WHERE email_hash = ?", (value,)
    )


def mask_author(author: str) -> str:
    """曾用名打码，避免输入任意邮箱就能查到别人的昵称。"""
    value = (author or "").strip()
    if not value:
        return ""
    if len(value) == 1:
        return value + "*"
    return value[0] + "*" * min(2, len(value) - 1)


def conflict(email: str, author: str) -> dict | None:
    """返回冲突信息；昵称一致或首次评论返回 None。"""
    row = get_row(email)
    if not row:
        return None
    current = str(row["current_author"] or "").strip()
    if not current:
        return None
    if (author or "").strip().casefold() == current.casefold():
        return None
    return {"current_author": current, "masked_author": mask_author(current)}


def remember(email: str, author: str) -> None:
    """首次评论时记住昵称；已存在时不覆盖当前昵称。"""
    value = normalize_email(email)
    name = (author or "").strip()
    if not value or not name:
        return
    key = avatar.email_hash(value)
    now = db.now()
    db.execute(
        "INSERT INTO comment_identities "
        "(email_hash, email, current_author, created_at, updated_at) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(email_hash) DO UPDATE SET email=excluded.email, updated_at=excluded.updated_at",
        (key, value, name, now, now),
    )


def rename(email: str, author: str) -> None:
    """验证通过后改名，并同步历史评论昵称。"""
    value = normalize_email(email)
    name = (author or "").strip()
    key = avatar.email_hash(value)
    if not key or not name:
        return
    row = get_row(value)
    previous = str(row["current_author"] or "") if row else ""
    now = db.now()
    db.execute(
        "UPDATE comment_identities SET previous_author=?, current_author=?, "
        "verified_at=?, updated_at=? WHERE email_hash=?",
        (previous, name, now, now, key),
    )
    db.execute(
        "UPDATE comments SET author=? WHERE email_hash=? AND is_owner=0 AND is_ai=0",
        (name, key),
    )


def _code_hash(key: str, code: str) -> str:
    return hashlib.sha256(f"{key}:{code}".encode("utf-8")).hexdigest()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="comment-rename")


def issue_code(email: str, new_author: str, ip: str = "") -> tuple[str, str]:
    """生成验证码并返回 (code, error)。限频按邮箱和 IP。"""
    value = normalize_email(email)
    key = avatar.email_hash(value)
    name = (new_author or "").strip()
    if not key or "@" not in value:
        return "", "邮箱格式不正确"
    if not name:
        return "", "请填写新昵称"

    checks = [
        ("identity_code_minute", key, 60, 1, "发送太频繁，请 60 秒后再试"),
        ("identity_code_10m", key, 600, 5, "验证码发送过于频繁，请稍后再试"),
        ("identity_code_day", key, 86400, 10, "该邮箱今天获取验证码次数过多，请明天再试"),
    ]
    for bucket, item, window, limit, message in checks:
        if not ratelimit.allow(bucket, item, window, limit):
            return "", message
    if ip and not ratelimit.allow("identity_code_ip", ip, 3600, 10):
        return "", "操作过于频繁，请稍后再试"

    code = "%06d" % secrets.randbelow(1_000_000)
    now = db.now()
    # 同一邮箱只保留最新一条未使用验证码
    db.execute(
        "DELETE FROM email_codes WHERE email_hash=? AND used_at=''", (key,)
    )
    db.insert(
        "INSERT INTO email_codes "
        "(email_hash, email, code_hash, new_author, purpose, expires_at, ip, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (key, value, _code_hash(key, code), name, PURPOSE,
         int(time.time()) + CODE_TTL, ip, now),
    )
    for bucket in ("identity_code_minute", "identity_code_10m", "identity_code_day"):
        ratelimit.touch(bucket, key)
    if ip:
        ratelimit.touch("identity_code_ip", ip)
    return code, ""


def verify_code(email: str, code: str) -> tuple[str, str]:
    """校验验证码，成功返回 (token, "")。"""
    value = normalize_email(email)
    key = avatar.email_hash(value)
    if not key:
        return "", "邮箱格式不正确"
    row = db.one(
        "SELECT * FROM email_codes WHERE email_hash=? AND used_at='' AND expires_at>? "
        "ORDER BY id DESC LIMIT 1",
        (key, int(time.time())),
    )
    if not row:
        return "", "验证码已过期，请重新获取"
    if int(row["attempts"] or 0) >= MAX_ATTEMPTS:
        return "", "尝试次数过多，请重新获取验证码"
    if not secrets.compare_digest(
        str(row["code_hash"]), _code_hash(key, (code or "").strip())
    ):
        db.execute(
            "UPDATE email_codes SET attempts=attempts+1 WHERE id=?", (row["id"],)
        )
        return "", "验证码不正确"
    db.execute("UPDATE email_codes SET used_at=? WHERE id=?", (db.now(), row["id"]))
    token = _serializer().dumps(
        {"h": key, "a": str(row["new_author"] or "")}
    )
    return token, ""


def verify_token(token: str, email: str, author: str) -> bool:
    key = avatar.email_hash(normalize_email(email))
    if not key or not token:
        return False
    try:
        data = _serializer().loads(token, max_age=TOKEN_TTL)
    except (BadSignature, SignatureExpired):
        return False
    return (
        str(data.get("h") or "") == key
        and str(data.get("a") or "").strip().casefold()
        == (author or "").strip().casefold()
    )


def backfill(conn) -> int:
    """为历史评论补身份记录；取每个邮箱最新一条评论的昵称。

    直接接收 sqlite3 连接，供启动迁移阶段调用。
    """
    rows = conn.execute(
        "SELECT id, email_hash, email, author, created_at FROM comments "
        "WHERE email_hash != '' AND deleted_at IS NULL "
        "ORDER BY created_at ASC, id ASC"
    ).fetchall()
    latest: dict[str, object] = {}
    for row in rows:
        latest[str(row["email_hash"])] = row
    inserted = 0
    for key, row in latest.items():
        exists = conn.execute(
            "SELECT 1 FROM comment_identities WHERE email_hash=?", (key,)
        ).fetchone()
        if exists:
            continue
        name = str(row["author"] or "").strip()
        if not name:
            continue
        stamp = str(row["created_at"] or "")
        conn.execute(
            "INSERT INTO comment_identities "
            "(email_hash, email, current_author, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (key, str(row["email"] or "").strip().lower(), name, stamp, stamp),
        )
        inserted += 1
    conn.commit()
    return inserted
