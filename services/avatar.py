"""头像地址与缓存辅助。"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from config import BASE_DIR, CACHE_DIR, UPLOADS_DIR
from services import settings

# Gravatar 不存在的负缓存（digest -> 时间戳）：避免同一邮箱反复走外网
_gravatar_missing: dict[str, float] = {}
_GRAVATAR_MISS_TTL = 600.0


def default_url() -> str:
    return "/static/images/default-avatar.svg"


def email_hash(email: str | None) -> str:
    email = (email or "").strip().lower()
    return hashlib.md5(email.encode("utf-8")).hexdigest() if email else ""


def qq_from_email(email: str | None) -> str:
    import re

    email = (email or "").strip().lower()
    match = re.fullmatch(r"(\d{5,12})@qq\.com", email)
    return match.group(1) if match else ""


def qq_avatar_size(size: int) -> int:
    if size <= 40:
        return 40
    if size <= 100:
        return 100
    return 640


def urls(email_hash_value: str | None, qq: str = "", size: int = 80) -> tuple[str, str]:
    """头像地址：Gravatar 优先、QQ 头像保底，返回 (地址, 回退地址)。

    Gravatar 地址带上 ``?qq=``：头像代理在 Gravatar 不存在时会 302 到 QQ 头像，
    这样「自定义头像 > Gravatar > QQ > 默认」的回退不需要渲染时逐个探测网络。
    """
    email_hash_value = (email_hash_value or "").strip()
    qq = (qq or "").strip()
    if not email_hash_value and not qq:
        return "", ""
    qq_path = f"/avatar/q{qq}/{qq_avatar_size(size)}.png" if qq else ""
    if not email_hash_value:
        return qq_path, ""
    path = f"/avatar/e{email_hash_value}/{max(1, size)}.png"
    if qq:
        return path + f"?qq={qq}", qq_path
    return path, ""


def gravatar_file(digest: str | None, size: int = 80) -> Path | None:
    """确保 Gravatar 已缓存，返回本地文件路径；确认不存在时返回 None。

    抓不到就是真的没有（cravatar / weavatar 都返回 404），不会写占位图。
    失败结果缓存 10 分钟：评论列表一次会并发请求十几个头像，
    没有负缓存的话每个都会重新走一遍外网。
    """
    digest = (digest or "").strip().lower()
    if len(digest) != 32 or any(c not in "0123456789abcdef" for c in digest):
        return None
    size = max(1, min(int(size or 80), 640))
    cache_file = Path(CACHE_DIR) / "avatars" / f"e{digest}_{size}.png"
    if cache_file.is_file():
        return cache_file
    now = time.time()
    missed_at = _gravatar_missing.get(digest)
    if missed_at and now - missed_at < _GRAVATAR_MISS_TTL:
        return None

    import requests

    from services import cachefs

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    for url in (
        f"https://cravatar.cn/avatar/{digest}?s={size}&d=404",
        f"https://weavatar.com/avatar/{digest}?s={size}&d=404",
    ):
        try:
            resp = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and resp.content:
                cache_file.write_bytes(resp.content)
                cachefs.cap(cache_file.parent, 2000)
                _gravatar_missing.pop(digest, None)
                return cache_file
        except Exception:  # noqa: BLE001
            continue
    if len(_gravatar_missing) > 2000:
        _gravatar_missing.clear()
    _gravatar_missing[digest] = now
    return None


def custom_url(email_hash_value: str | None) -> str:
    """注册用户上传的自定义头像（规范路径 /uploads/reader/avatar/...）。

    查不到或没上传过时返回空串，由调用方回退 Gravatar / QQ 头像。
    """
    key = (email_hash_value or "").strip().lower()
    if not key:
        return ""
    try:
        import db

        value = db.scalar(
            "SELECT avatar_url FROM reader_users WHERE email_hash = ?", (key,), ""
        )
    except Exception:  # noqa: BLE001
        return ""
    return str(value or "").strip()


def mail_url(url: str, site: str) -> str:
    """邮件里的图片地址：绝对地址 + 站内本地直连。

    邮件 HTML 不经过页面输出阶段的 OSS 改写，但如果数据库里存的是对象存储
    直链或预签名地址，收件人隔天打开时签名早就过期了。这里先归一化回
    ``/uploads/...`` 再拼站点域名——站点的 /uploads 路由直接读本地文件，
    不会 302 到对象存储，邮件客户端什么时候打开都能取到图。

    外部地址（Gravatar 等）保持原样。
    """
    value = str(url or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    if value.startswith(("http://", "https://")):
        normalized = value
        try:
            from services import upload

            normalized = upload.normalize_text(value)
        except Exception:  # noqa: BLE001
            normalized = value
        if normalized.startswith("/uploads/"):
            return (site or "").rstrip("/") + normalized
        # 兜底：配置里换过的旧域名、已停用插件留下的直链，只要路径带 /uploads/
        # 就改回站内直连——邮件里出现带签名的地址，收件人过一会儿打开就是裂图
        match = re.search(r"/uploads/[^\s\"'<>()\[\]?#]+", value)
        if match:
            return (site or "").rstrip("/") + match.group(0)
        return value
    # 私有桶的站点代理路径与 /uploads/... 等价，统一成本地直连
    if value.startswith("/oss-media/"):
        value = "/" + value[len("/oss-media/"):]
    if value.startswith("/"):
        return (site or "").rstrip("/") + value
    return value


def mail_avatar(email: str | None, site: str) -> str:
    """邮件通知里的评论者头像，与全站同一套优先级：

    自定义头像 > 博主后台头像 > Gravatar > QQ 头像（保底） > 首字母色块。

    邮件没有前端 onerror 可以回退，所以这里必须给出确定的地址：
    先确认 Gravatar 真的存在，不存在才落到 QQ 头像。
    """
    email = (email or "").strip()
    if not email:
        return ""
    base = (site or "").rstrip("/")
    key = email_hash(email)
    custom = custom_url(key)
    if custom:
        return mail_url(custom, site)
    if _is_blogger_email(email) and configured_avatar_exists():
        admin = admin_url(80)
        if admin:
            return mail_url(admin, site)
    if key and gravatar_file(key, 80) is not None:
        return f"{base}/avatar/e{key}/80.png"
    qq = qq_from_email(email)
    if qq:
        return f"{base}/avatar/q{qq}/100.png"
    return ""


def _is_blogger_email(email: str) -> bool:
    """是否博主的通知邮箱（notify_email / contact_email）。"""
    lowered = (email or "").strip().lower()
    if not lowered:
        return False
    return lowered in {
        settings.get_str("notify_email", "").strip().lower(),
        settings.get_str("contact_email", "").strip().lower(),
    } - {""}


def configured_avatar_exists() -> bool:
    cfg = settings.get_str("avatar", "").strip()
    if not cfg:
        return False
    # /uploads/xxx 实际落在 var/uploads/xxx（UPLOADS_DIR），
    # 旧实现拼的是 BASE_DIR/uploads/xxx，永远不存在，
    # 结果就是后台上传成功、预览和前台关于页都不显示头像。
    rel = cfg.split("/uploads/", 1)[1] if "/uploads/" in cfg else cfg.lstrip("/")
    rel = rel.split("?", 1)[0]
    parts = rel.split("/")
    if not rel or ".." in parts or rel.startswith("/"):
        return False
    return (Path(UPLOADS_DIR) / rel).is_file()


def admin_url(size: int = 40) -> str:
    cfg = settings.get_str("avatar", "").strip()
    if cfg and configured_avatar_exists():
        return cfg
    contact = settings.get_str("contact_email", "").strip().lower()
    if not contact:
        return ""
    return urls(email_hash(contact), qq_from_email(contact), size)[0]
