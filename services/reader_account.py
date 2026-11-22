"""读者账号：邮箱 + 密码注册登录。

与单管理员 users 表隔离，身份以 email_hash 为准，与 comment_identities /
comments 共用同一哈希体系。登录态用 itsdangerous 签名 token 写入 HttpOnly Cookie
（blog_reader_session），前端只通过 /api/reader/me 读取状态，token 不由 JS 触碰。

注册必须先验证邮箱验证码（复用 email_codes 表，purpose='register'）；
验证码只存哈希、一次性、10 分钟有效，发送限频与改名验证码一致。
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import db
from services import avatar, comment_identity, hooks, ratelimit

TOKEN_TTL = 30 * 24 * 3600  # 登录态 30 天
CODE_TTL = 600              # 验证码 10 分钟
MAX_ATTEMPTS = 5
PURPOSE = "register"
COOKIE_NAME = "blog_reader_session"

# 昵称审核状态：approved 正常可用；manual 待人工审核（禁止登录）；
# rejected 已拒绝（禁止登录）
REVIEW_APPROVED = "approved"
REVIEW_MANUAL = "manual"
REVIEW_REJECTED = "rejected"


def normalize_email(email: str) -> str:
    return comment_identity.normalize_email(email)


def email_hash(email: str) -> str:
    return avatar.email_hash(normalize_email(email))


def valid_email(email: str) -> bool:
    value = normalize_email(email)
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


def get_by_hash(key: str) -> dict | None:
    row = db.one("SELECT * FROM reader_users WHERE email_hash = ?", (key,))
    return dict(row) if row else None


def public_user(row: dict) -> dict:
    """对外暴露的用户信息，不含哈希/令牌等敏感字段。"""
    return {
        "name": str(row.get("name") or ""),
        "email": str(row.get("email") or ""),
        "link": str(row.get("link") or ""),
    }


def _code_hash(key: str, code: str) -> str:
    return hashlib.sha256(f"{key}:{code}".encode("utf-8")).hexdigest()


def issue_code(email: str, ip: str = "") -> tuple[str, str]:
    """生成注册验证码，返回 (code, error)。已注册邮箱不允许重复注册。"""
    value = normalize_email(email)
    key = avatar.email_hash(value)
    if not valid_email(value):
        return "", "邮箱格式不正确"
    if get_by_hash(key):
        return "", "该邮箱已注册，请直接登录"

    checks = [
        ("reader_code_minute", key, 60, 1, "发送太频繁，请 60 秒后再试"),
        ("reader_code_10m", key, 600, 5, "验证码发送过于频繁，请稍后再试"),
        ("reader_code_day", key, 86400, 10, "该邮箱今天获取验证码次数过多，请明天再试"),
    ]
    for bucket, item, window, limit, message in checks:
        if not ratelimit.allow(bucket, item, window, limit):
            return "", message
    if ip and not ratelimit.allow("reader_code_ip", ip, 3600, 10):
        return "", "操作过于频繁，请稍后再试"

    code = "%06d" % secrets.randbelow(1_000_000)
    now = db.now()
    db.execute(
        "DELETE FROM email_codes WHERE email_hash=? AND purpose=? AND used_at=''",
        (key, PURPOSE),
    )
    db.insert(
        "INSERT INTO email_codes "
        "(email_hash, email, code_hash, new_author, purpose, expires_at, ip, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (key, value, _code_hash(key, code), "", PURPOSE,
         int(time.time()) + CODE_TTL, ip, now),
    )
    for bucket in ("reader_code_minute", "reader_code_10m", "reader_code_day"):
        ratelimit.touch(bucket, key)
    if ip:
        ratelimit.touch("reader_code_ip", ip)
    return code, ""


def verify_code(email: str, code: str) -> str:
    """校验注册验证码，成功返回空错误串。"""
    value = normalize_email(email)
    key = avatar.email_hash(value)
    if not key:
        return "邮箱格式不正确"
    row = db.one(
        "SELECT * FROM email_codes WHERE email_hash=? AND purpose=? "
        "AND used_at='' AND expires_at>? ORDER BY id DESC LIMIT 1",
        (key, PURPOSE, int(time.time())),
    )
    if not row:
        return "验证码已过期，请重新获取"
    if int(row["attempts"] or 0) >= MAX_ATTEMPTS:
        return "尝试次数过多，请重新获取验证码"
    if not secrets.compare_digest(
        str(row["code_hash"]), _code_hash(key, (code or "").strip())
    ):
        db.execute("UPDATE email_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
        return "验证码不正确"
    db.execute("UPDATE email_codes SET used_at=? WHERE id=?", (db.now(), row["id"]))
    return ""


def register(email: str, code: str, password: str, name: str, link: str = "") -> tuple[dict | None, str]:
    """注册读者账号，成功返回 (用户信息, '')。"""
    email = normalize_email(email)
    name = (name or "").strip()
    link = (link or "").strip()
    if not valid_email(email):
        return None, "邮箱格式不正确"
    if not name:
        return None, "请填写昵称"
    if len(name) > 30:
        return None, "昵称过长"
    if len(password or "") < 6:
        return None, "密码至少 6 位"
    if link and not valid_link(link):
        return None, "网址格式不正确"
    error = verify_code(email, code)
    if error:
        return None, error

    key = avatar.email_hash(email)
    if get_by_hash(key):
        return None, "该邮箱已注册，请直接登录"

    # 昵称机审：通过的直接可用，被判违规的一律转人工（账号先落库但禁止登录）
    decision, source, reason = moderate_name(name)
    review_status = REVIEW_APPROVED if decision == "pass" else REVIEW_MANUAL

    from werkzeug.security import generate_password_hash

    now = db.now()
    try:
        user_id = db.insert(
            "INSERT INTO reader_users "
            "(email_hash, email, name, password_hash, link, verified_at, "
            " review_status, review_note, reviewed_at, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                key, email, name, generate_password_hash(password), link, now,
                review_status, reason if review_status == REVIEW_MANUAL else "", "",
                now, now,
            ),
        )
    except Exception:
        return None, "注册失败，请稍后重试"

    if review_status != REVIEW_APPROVED:
        # 留存：机审结论 + 待人工处理，后台「用户管理」可见
        db.insert(
            "INSERT INTO reader_reviews "
            "(user_id, email_hash, email, name, source, decision, reason, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (int(user_id or 0), key, email, name, source, decision, reason, "open", now),
        )
        # 同步进后台「留存记录」插件（op_logs）：从注册这一刻起就有痕迹
        hooks.emit("admin.action", {
            "action": "user.review.queue",
            "target": f"#{int(user_id or 0)} {name}"[:200],
            "detail": f"注册昵称转人工（{source}）：{reason}"[:500],
        })
        return None, "昵称需人工审核，已提交给博主；审核通过后即可登录"

    # 与 comment_identities 打通：让注册用户的昵称成为该邮箱的统一昵称
    comment_identity.remember(email, name)
    return get_by_hash(key), ""


def moderate_name(name: str) -> tuple[str, str, str]:
    """昵称机审：返回 (decision, source, reason)，decision = pass | review。

    1) 本地敏感词命中一律转人工，不自动放行；
    2) 再看 AI 插件（未启用/调用失败时按本地规则放行，避免模型故障卡死注册）。
    """
    text = (name or "").strip()
    if not text:
        return "review", "local", "昵称为空"
    try:
        from services import sensitive

        if sensitive.has(text):
            return "review", "local", "昵称命中敏感词"
    except Exception:
        pass
    try:
        from plugins.ai_assistant.jobs import review_nickname

        decision, reason = review_nickname(text)
    except Exception:
        return "pass", "local", ""
    if decision == "pass":
        return "pass", "ai", reason or ""
    return "review", "ai", reason or "AI 判定昵称违规"


def valid_link(link: str) -> bool:
    value = (link or "").strip()
    if not value:
        return True
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", value):
        value = "https://" + value
    return bool(re.match(r"^https?://\S+$", value, re.I)) and len(value) <= 200


def login(email: str, password: str) -> tuple[dict | None, str]:
    """密码登录，成功返回 (用户信息, '')。"""
    email = normalize_email(email)
    key = avatar.email_hash(email)
    row = get_by_hash(key)
    if not row:
        return None, "邮箱或密码错误"
    from werkzeug.security import check_password_hash

    if not check_password_hash(str(row["password_hash"] or ""), password or ""):
        return None, "邮箱或密码错误"
    # 密码正确后才暴露审核状态，避免泄露账号是否存在
    status = str(row["review_status"] or REVIEW_APPROVED)
    if status == REVIEW_MANUAL:
        return None, "昵称待人工审核，通过后即可登录，请稍后再试"
    if status == REVIEW_REJECTED:
        return None, "该账号昵称未通过审核，请联系博主"
    db.execute("UPDATE reader_users SET last_login_at=? WHERE id=?", (db.now(), row["id"]))
    # 昵称以 comment_identities 的统一昵称为准，保证历史评论展示一致
    identity = comment_identity.get_row(email)
    if identity and identity["current_author"]:
        row["name"] = str(identity["current_author"])
    return row, ""


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="reader-session")


def issue_token(row: dict) -> str:
    return _serializer().dumps({
        "h": str(row.get("email_hash") or ""),
        "n": str(row.get("name") or ""),
    })


def verify_token(token: str) -> dict | None:
    """校验登录 token，返回用户行或 None。"""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=TOKEN_TTL)
    except (BadSignature, SignatureExpired):
        return None
    key = str(data.get("h") or "")
    if not key:
        return None
    row = get_by_hash(key)
    if not row:
        return None
    # 审核未通过的账号不应继续持有登录态：否则「拒绝」只挡住下一次密码登录，
    # 已登录的人靠 30 天 token 照旧能用账号身份、改昵称、看个人中心，等于没拒绝。
    if str(row.get("review_status") or REVIEW_APPROVED) != REVIEW_APPROVED:
        return None
    # 昵称以 comment_identities 的统一昵称为准
    identity = comment_identity.get_row(str(row.get("email") or ""))
    if identity and identity["current_author"]:
        row["name"] = str(identity["current_author"])
    return row


# ── 账号管理：昵称 / 头像 / 邮箱 ──
def update_name(row: dict, new_name: str) -> tuple[bool, str]:
    name = str(new_name or "").strip()
    if len(name) < 1 or len(name) > 30:
        return False, "昵称需 1-30 个字符"
    key = str(row.get("email_hash") or "")
    email = str(row.get("email") or "")
    # 改名同样走昵称机审：违规的直接拒绝并留存记录（已通过审核的账号不再进人工队列，
    # 避免账号状态在「正常 / 待审」之间反复横跳）
    decision, source, reason = moderate_name(name)
    if decision != "pass":
        db.insert(
            "INSERT INTO reader_reviews "
            "(user_id, email_hash, email, name, source, decision, reason, status, operator, created_at, reviewed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (int(row.get("id") or 0), key, email, name, source, decision, reason,
             "rejected", "auto", db.now(), db.now()),
        )
        hooks.emit("admin.action", {
            "action": "user.review.reject_name",
            "target": f"#{int(row.get('id') or 0)} {name}"[:200],
            "detail": f"改昵称被拦截（{source}）：{reason}"[:500],
        })
        return False, "该昵称未通过审核，请换一个昵称"
    conn = db.get_db()
    try:
        conn.execute("UPDATE reader_users SET name=?, updated_at=? WHERE email_hash=?",
                     (name, db.now(), key))
        # 统一昵称：comment_identities + 该用户全部评论
        if email:
            conn.execute(
                "INSERT INTO comment_identities (email_hash, email, current_author, created_at, updated_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(email_hash) DO UPDATE SET current_author=excluded.current_author, updated_at=excluded.updated_at",
                (key, email, name, db.now(), db.now()),
            )
        conn.execute("UPDATE comments SET author=? WHERE email_hash=? AND deleted_at IS NULL", (name, key))
        conn.commit()
        return True, ""
    except Exception as exc:
        conn.rollback()
        return False, f"修改失败：{exc}"


def delete_user(user_id: int) -> tuple[bool, str]:
    """删除读者账号（只删 reader_users 一行）。

    评论、评论身份、站内通知、审核留存都不动：删除账号是「这个邮箱不能再登录」，
    不是抹掉历史；评论正文与审核轨迹仍能在「留存记录」里追溯，
    这样误删之后也能凭邮箱哈希找回上下文。
    """
    row = db.one("SELECT id FROM reader_users WHERE id = ?", (user_id,))
    if not row:
        return False, "账号不存在或已被删除"
    db.execute("DELETE FROM reader_users WHERE id = ?", (user_id,))
    return True, ""


def update_avatar(row: dict, url: str) -> tuple[bool, str]:
    value = str(url or "").strip()
    key = str(row.get("email_hash") or "")
    if not key:
        return False, "用户不存在"
    if value and not (value.startswith("/uploads/") or value.startswith("https://") or value.startswith("http://")):
        return False, "头像地址无效"
    db.execute("UPDATE reader_users SET avatar_url=?, updated_at=? WHERE email_hash=?",
               (value, db.now(), key))
    return True, ""


def update_password(row: dict, old_password: str, new_password: str) -> tuple[bool, str]:
    """修改密码：需校验旧密码，新密码至少 6 位。"""
    from werkzeug.security import check_password_hash, generate_password_hash

    if not check_password_hash(str(row.get("password_hash") or ""), old_password or ""):
        return False, "当前密码不正确"
    pwd = str(new_password or "")
    if len(pwd) < 6:
        return False, "新密码至少 6 位"
    db.execute(
        "UPDATE reader_users SET password_hash=?, updated_at=? WHERE email_hash=?",
        (generate_password_hash(pwd), db.now(), str(row.get("email_hash") or "")),
    )
    return True, ""


def update_email(row: dict, new_email: str, code: str) -> tuple[dict | None, str]:
    """换绑邮箱：验证码校验新邮箱后，迁移所有身份数据到新 email_hash。"""
    new_email = str(new_email or "").strip()
    if not valid_email(new_email):
        return None, "邮箱格式不正确"
    new_key = email_hash(new_email)
    old_key = str(row.get("email_hash") or "")
    if new_key == old_key:
        return None, "新邮箱与当前邮箱相同"
    if get_by_hash(new_key):
        return None, "该邮箱已注册"
    msg = verify_code(new_email, code)
    if msg:
        return None, msg
    conn = db.get_db()
    try:
        # 迁移各表 email_hash
        for table in ("comments", "comment_identities", "comment_notifications", "comment_likes"):
            if table == "comment_likes":
                continue  # 点赞按 voter_hash，不对应用户邮箱，不迁移
            conn.execute(f"UPDATE {table} SET email_hash=? WHERE email_hash=?", (new_key, old_key))
        conn.execute(
            "UPDATE reader_users SET email=?, email_hash=?, verified_at=?, updated_at=? WHERE email_hash=?",
            (normalize_email(new_email), new_key, db.now(), db.now(), old_key),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return None, f"换绑失败：{exc}"
    updated = get_by_hash(new_key)
    return updated, ""


# ── 后台：用户管理与昵称审核 ──
def _status_clause(status: str, keyword: str) -> tuple[str, list]:
    where: list[str] = []
    params: list = []
    if status in (REVIEW_APPROVED, REVIEW_MANUAL, REVIEW_REJECTED):
        where.append("review_status = ?")
        params.append(status)
    if keyword:
        like = f"%{keyword}%"
        where.append("(name LIKE ? OR email LIKE ?)")
        params.extend([like, like])
    return (" WHERE " + " AND ".join(where)) if where else "", params


def admin_list(page: int = 1, per_page: int = 20, status: str = "", keyword: str = "") -> tuple[list[dict], int]:
    """后台用户列表：按审核状态过滤 + 昵称/邮箱搜索 + 分页。"""
    clause, params = _status_clause(status, keyword)
    total = int(db.scalar(f"SELECT COUNT(*) FROM reader_users{clause}", tuple(params), 0) or 0)
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 20), 100))
    rows = db.query(
        f"SELECT * FROM reader_users{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        tuple(params) + (per_page, (page - 1) * per_page),
    )
    return [dict(r) for r in rows], total


def status_counts() -> dict:
    """各审核状态的账号数，用于筛选条上的计数。"""
    out = {REVIEW_APPROVED: 0, REVIEW_MANUAL: 0, REVIEW_REJECTED: 0}
    for row in db.query("SELECT review_status AS s, COUNT(*) AS c FROM reader_users GROUP BY review_status"):
        out[str(row["s"] or REVIEW_APPROVED)] = int(row["c"] or 0)
    out["all"] = sum(out.values())
    return out


def set_review(user_id: int, status: str, operator: str = "", note: str = "") -> tuple[bool, str]:
    """人工审核结果落库：更新账号状态，并把该账号的待审记录一并结案。"""
    if status not in (REVIEW_APPROVED, REVIEW_REJECTED):
        return False, "无效的审核结果"
    row = db.one("SELECT * FROM reader_users WHERE id = ?", (int(user_id or 0),))
    if not row:
        return False, "用户不存在"
    now = db.now()
    db.execute(
        "UPDATE reader_users SET review_status=?, review_note=?, reviewed_at=?, updated_at=? WHERE id=?",
        (status, str(note or ""), now, now, int(user_id)),
    )
    db.execute(
        "UPDATE reader_reviews SET status=?, operator=?, reviewed_at=? "
        "WHERE email_hash=? AND status='open'",
        (status, str(operator or ""), now, str(row["email_hash"] or "")),
    )
    if status == REVIEW_APPROVED:
        # 通过后昵称才正式生效：写入统一身份表，历史评论昵称同步
        email = str(row["email"] or "")
        name = str(row["name"] or "")
        if email and name:
            comment_identity.remember(email, name)
    return True, ""



