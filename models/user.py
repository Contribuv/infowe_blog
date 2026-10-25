"""管理员账户。"""

from __future__ import annotations

import db
from werkzeug.security import check_password_hash, generate_password_hash

from models.base import row_to_dict


def count() -> int:
    return int(db.scalar("SELECT COUNT(*) FROM users", (), 0))


def get(user_id: int) -> dict | None:
    return row_to_dict(db.one("SELECT * FROM users WHERE id = ?", (user_id,)))


def get_by_username(username: str) -> dict | None:
    return row_to_dict(db.one("SELECT * FROM users WHERE username = ?", (username,)))


def first() -> dict | None:
    return row_to_dict(db.one("SELECT * FROM users ORDER BY id ASC LIMIT 1"))


def create(username: str, password: str) -> int:
    # 单管理员：已存在则不允许再创建
    if count() > 0:
        raise RuntimeError("只允许一个管理员账户")
    return db.insert(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )


def verify(username: str, password: str) -> dict | None:
    user = get_by_username(username)
    if not user:
        return None
    stored = str(user["password_hash"] or "")
    # 兼容 PHP password_hash() 生成的 bcrypt（$2y$/$2b$/$2a$）
    if stored.startswith(("$2y$", "$2b$", "$2a$")):
        try:
            import bcrypt

            hashed = stored.replace("$2y$", "$2b$", 1).encode("utf-8")
            if bcrypt.checkpw(password.encode("utf-8"), hashed):
                return user
        except Exception:
            return None
        return None
    if check_password_hash(stored, password):
        return user
    return None


def update_password(user_id: int, password: str) -> None:
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user_id),
    )


def update_username(user_id: int, username: str) -> None:
    db.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
