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
RESET_PURPOSE = "reset"
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


def issue_code(email: str, ip: str = "", purpose: str = PURPOSE) -> tuple[str, str]:
    """生成邮箱验证码，返回 (code, error)。

    purpose="register" 只给未注册邮箱，purpose="reset" 只给已注册邮箱；
    两种用途分开存，注册验证码不能拿去重置密码。
    """
    value = normalize_email(email)
    key = avatar.email_hash(value)
    if not valid_email(value):
        return "", "邮箱格式不正确"
    exists = bool(get_by_hash(key))
    if purpose == PURPOSE and exists:
        return "", "该邮箱已注册，请直接登录"
    if purpose == RESET_PURPOSE and not exists:
        return "", "该邮箱还没有注册"

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
        (key, purpose),
    )
    db.insert(
        "INSERT INTO email_codes "
        "(email_hash, email, code_hash, new_author, purpose, expires_at, ip, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (key, value, _code_hash(key, code), "", purpose,
         int(time.time()) + CODE_TTL, ip, now),
    )
    for bucket in ("reader_code_minute", "reader_code_10m", "reader_code_day"):
        ratelimit.touch(bucket, key)
    if ip:
        ratelimit.touch("reader_code_ip", ip)
    return code, ""


def verify_code(email: str, code: str, purpose: str = PURPOSE) -> str:
    """校验验证码，成功返回空错误串。"""
    value = normalize_email(email)
    key = avatar.email_hash(value)
    if not key:
        return "邮箱格式不正确"
    row = db.one(
        "SELECT * FROM email_codes WHERE email_hash=? AND purpose=? "
        "AND used_at='' AND expires_at>? ORDER BY id DESC LIMIT 1",
        (key, purpose, int(time.time())),
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
    row = get_by_hash(key)
    # 机审直接通过的注册也留一条「账号变更」记录，后台留存页能看到完整账号时间线
    _log_account_change(row, "register", f"昵称机审通过（{source}）")
    return row, ""


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

        # 昵称审核是安全兜底，不受「敏感词过滤」总开关影响：只要词表里配了词就拦
        hit = sensitive.screen(text)
        if hit:
            return "review", "local", f"昵称命中敏感词：{hit}"
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


def reset_password(email: str, code: str, password: str) -> tuple[dict | None, str]:
    """邮箱验证码重置密码；成功后把邮箱验证码标记为已用。"""
    value = normalize_email(email)
    if not valid_email(value):
        return None, "邮箱格式不正确"
    row = get_by_hash(avatar.email_hash(value))
    if not row:
        return None, "该邮箱还没有注册"
    if len(password or "") < 6:
        return None, "密码至少 6 位"
    error = verify_code(value, code, RESET_PURPOSE)
    if error:
        return None, error
    from werkzeug.security import generate_password_hash

    db.execute(
        "UPDATE reader_users SET password_hash=?, updated_at=? WHERE email_hash=?",
        (generate_password_hash(password), db.now(), email_hash(value)),
    )
    # 密码重置后让旧登录态失效：token 里有 password_hash 指纹时由 verify 拒绝；
    # 这里顺带刷新 last_login_at，方便后台看出最近一次操作
    db.execute("UPDATE reader_users SET last_login_at=? WHERE email_hash=?", (db.now(), email_hash(value)))
    return get_by_hash(email_hash(value)), ""


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="reader-session")


def _pw_fingerprint(password_hash: str) -> str:
    """登录 token 绑定密码指纹：改密后旧 token 自动失效。"""
    return hashlib.sha256(str(password_hash or "").encode("utf-8")).hexdigest()[:12]


def issue_token(row: dict) -> str:
    return _serializer().dumps({
        "h": str(row.get("email_hash") or ""),
        "n": str(row.get("name") or ""),
        "p": _pw_fingerprint(str(row.get("password_hash") or "")),
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
    # 旧 token（无指纹）或改密前的 token 一律拒绝
    if str(data.get("p") or "") != _pw_fingerprint(str(row.get("password_hash") or "")):
        return None
    # 昵称以 comment_identities 的统一昵称为准
    identity = comment_identity.get_row(str(row.get("email") or ""))
    if identity and identity["current_author"]:
        row["name"] = str(identity["current_author"])
    return row


# ── 账号管理：昵称 / 头像 / 邮箱 ──
ACCOUNT_SOURCE = "account"
ACCOUNT_LABELS = {
    "register": "注册账号",
    "avatar": "修改头像",
    "email": "换绑邮箱",
    "name": "修改昵称",
    "password": "修改密码",
}


def _log_account_change(row: dict, kind: str, detail: str = "") -> None:
    """把账号自助变更写进审核留存（reader_reviews），后台可追溯。

    与昵称机审共用一张表：source=account 表示账号操作，status=done 表示已完成，
    前端「来源」列会显示成「账号变更」。
    """
    if not row:
        return
    label = ACCOUNT_LABELS.get(kind, kind)
    reason = label + ("：" + detail if detail else "")
    try:
        db.insert(
            "INSERT INTO reader_reviews "
            "(user_id, email_hash, email, name, source, decision, reason, status, operator, created_at, reviewed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                int(row.get("id") or 0), str(row.get("email_hash") or ""),
                str(row.get("email") or ""), str(row.get("name") or ""),
                ACCOUNT_SOURCE, "", reason, "done", str(row.get("name") or ""),
                db.now(), db.now(),
            ),
        )
    except Exception:  # noqa: BLE001
        # 留存失败不影响账号操作本身
        pass


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
        _log_account_change({**row, "name": name}, "name")
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
    _log_account_change(row, "avatar", "已更新" if value else "已移除")
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
    _log_account_change(row, "password")
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
                # 点赞按 voter_hash 归属，必须一起迁移，否则旧赞无法取消、新 hash 可重复投票。
                # 先删掉与目标 hash 重复的旧赞，避免撞唯一约束。
                conn.execute(
                    "DELETE FROM comment_likes WHERE voter_hash=? AND comment_id IN "
                    "(SELECT comment_id FROM comment_likes WHERE voter_hash=?)",
                    (old_key, new_key),
                )
                conn.execute(
                    "UPDATE comment_likes SET voter_hash=? WHERE voter_hash=?",
                    (new_key, old_key),
                )
                continue
            conn.execute(f"UPDATE {table} SET email_hash=? WHERE email_hash=?", (new_key, old_key))
        # 身份表的 email 字段仍留着旧地址，会导致展示与账号不一致
        conn.execute(
            "UPDATE comment_identities SET email=? WHERE email_hash=?",
            (normalize_email(new_email), new_key),
        )
        conn.execute(
            "UPDATE reader_users SET email=?, email_hash=?, verified_at=?, updated_at=? WHERE email_hash=?",
            (normalize_email(new_email), new_key, db.now(), db.now(), old_key),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return None, f"换绑失败：{exc}"
    updated = get_by_hash(new_key)
    _log_account_change(updated or row, "email", f"{row.get('email') or ''} → {normalize_email(new_email)}")
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



