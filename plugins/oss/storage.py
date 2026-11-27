"""对象存储插件的核心逻辑：远端发布、URL 双向回写、存量迁移。

设计原则（对应「停用即恢复原状」的硬要求）：

1. **本地永远保留一份**。启用时先按原有逻辑把文件写进 var/uploads/，
   再额外传一份到 OSS。停用后本地文件还在，回写地址不会裂图。
2. **对象 key 与站内相对路径一一对应**：
   本地 `/uploads/2026/11/a.jpg` → OSS key `uploads/2026/11/a.jpg`。
   回写时只做「前缀 ↔ 路径」的转换，不猜、不模糊匹配。
3. **URL 双向可逆**：
   - 迁移：`/uploads/x` → `{public_base}/uploads/x`
   - 停用：`{public_base}/uploads/x` → `/uploads/x`
4. **只在插件启用时接管**。发布函数每次调用都实时读插件状态，
   停用后下一个上传请求立即回到本地规则。
"""

from __future__ import annotations

import logging
import mimetypes
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from config import UPLOADS_DIR

from . import s3

KEY = "oss"
logger = logging.getLogger(__name__)

# 需要扫描 URL 的「内容字段」白名单。
# 只覆盖真正会展示给读者的文本，日志表（op_logs / ai_messages）不碰：
# 那是历史快照，改了反而会篡改审计记录。
TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("posts", ("title", "content", "excerpt", "cover")),
    ("comments", ("content",)),
    ("links", ("name", "url", "description", "avatar")),
    ("memories", ("title", "text", "image")),
    ("projects", ("name", "description", "url")),
    ("timeline", ("content",)),
    ("settings", ("value",)),
    ("plugins", ("config",)),
    # 读者头像 /uploads/reader/avatar/... 不在保留目录里，必须按引用保护
    ("reader_users", ("avatar_url",)),
)

# 站内上传路径：排除引号、括号、尖括号与空白；同时要求前面不是 URL 字符，
# 避免把 https://host/uploads/x 这种完整地址再替换一次。
_REL_RE = re.compile(r"(?<![\w:/.])/uploads/[^\s\"'<>()\[\]]+")
# 私有桶的站点代理路径
_MEDIA_RE = re.compile(r"/oss-media/[^\s\"'<>()\[\]]+")
_URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]]+")
# 迁移时跳过的目录：原图备份不对外，隐藏目录一律不传；
# avatar 是站点头像（`/uploads/avatar/`），属于后台品牌资源，不参与对象存储——
# 它由设置页直接覆盖写入，进了 OSS 反而会出现「本地已换、远端还是旧图」。
_SKIP_DIRS = {".originals", ".trash", ".tmp", "avatar", "originals"}


# ── 配置 ──────────────────────────────────────────────

def raw_config() -> dict:
    from services import plugins as plugins_service

    data = plugins_service.config(KEY)
    return data if isinstance(data, dict) else {}


def get_cfg() -> s3.S3Config | None:
    """配置不完整时返回 None：宁可回退本地，也不要半套配置。"""
    data = raw_config()
    endpoint = str(data.get("endpoint") or "").strip()
    bucket = str(data.get("bucket") or "").strip()
    access_key = str(data.get("access_key") or "").strip()
    secret_key = str(data.get("secret_key") or "").strip()
    if not (endpoint and bucket and access_key and secret_key):
        return None
    sign_host = data.get("sign_host")
    return s3.S3Config(
        endpoint=endpoint,
        bucket=bucket,
        access_key=access_key,
        secret_key=secret_key,
        region=str(data.get("region") or "us-east-1").strip() or "us-east-1",
        public_base=str(data.get("public_base") or "").strip(),
        prefix=str(data.get("prefix") or "uploads").strip() or "uploads",
        sign_host=True if sign_host is None else bool(sign_host),
    )


def is_enabled() -> bool:
    """实时判断：插件启用 + 配置完整。每次上传都会调用，不缓存。"""
    from services import plugins as plugins_service

    return plugins_service.enabled(KEY) and get_cfg() is not None


def bucket_policy() -> str:
    """桶策略：public（匿名可读）或 private（必须经站点代理）。

    由测试连接时自动探测后写入；没探测过时按 public 处理，
    与 v3.9.18 的行为保持一致。
    """
    return "private" if str(raw_config().get("policy") or "public") == "private" else "public"


def proxy_enabled() -> bool:
    """兼容旧配置：私有桶优先用预签名直链，不再默认走站点代理。"""
    return False


def presign_expires() -> int:
    """预签名有效期（秒），文档建议 300~900。"""
    try:
        value = int(raw_config().get("presign_expires") or 900)
    except (TypeError, ValueError):
        value = 900
    return max(60, min(value, 604800))


def url_for(rel: str) -> str:
    """生成对外 URL：公共桶直链；私有桶现场签一个临时 GET 链接。

    私有桶不再走站点代理——那会把 OSS 的流量绕回服务器，
    既拖带宽又失去对象存储的意义。

    站点头像例外：后台头像按设计不进对象存储（见 publish），OSS 上不会有这个对象，
    生成签名地址必然 404，所以本地存在时直接返回规范路径。读者头像不在例外内。
    """
    clean = str(rel or "").lstrip("/")
    # 站点头像按设计不进 OSS；读者头像虽走 OSS，但上传是异步的，对象可能还没到。
    # 本地文件在、远端没有时用本地地址，避免上传时序造成死链。
    if clean.startswith(("uploads/avatar/", "uploads/reader/avatar/")) and _local_exists(clean):
        if clean.startswith("uploads/avatar/") or not _remote_exists(clean):
            return "/" + clean
    cfg = get_cfg()
    if cfg is None:
        return rel
    if bucket_policy() == "private":
        return s3.presign(cfg, rel, presign_expires())
    return cfg.url_of(rel)


def presign_put_url(rel: str) -> str:
    """生成 PUT 预签名 URL 供浏览器直传；未启用/配置不全时返回空串。

    浏览器拿到后直接 PUT 文件到 OSS，避开「服务器 → 对象存储」这段公网链路。
    对象 key 与站内 /uploads/ 路径一一对应（key_of），孤儿识别照常工作。
    """
    if not is_enabled():
        return ""
    cfg = get_cfg()
    if cfg is None:
        return ""
    return s3.presign_put(cfg, rel, presign_expires())


def rewrite_html(html: str) -> str:
    """把 HTML 里的 /uploads/... 换成当前策略对应的最终地址。

    这是「单一真相」的关键：数据库永远只存 /uploads/...，
    页面输出时才决定是 OSS 直链还是站点代理，
    所以切换策略不需要回写任何内容。

    代码块（<pre> / <code> 等）不参与改写：README 与文章里的
    `location ~ ^/uploads/...`、`curl .../uploads/x` 是示例文本，
    改写后会变成带 Access Key 与签名的真实地址。
    """
    if not html or "/uploads/" not in html:
        return html
    cfg = get_cfg()
    if cfg is None:
        return html

    from services.upload import rewrite_outside_code

    if bucket_policy() == "private":
        # 私有：逐张现场签名，浏览器直接去 OSS 取图，不经过本站带宽
        expires = presign_expires()

        def _sign(text: str) -> str:
            def _one(match: re.Match) -> str:
                raw = match.group(0)
                raw_path = unquote(raw.split("?", 1)[0])
                # 本地有、远端没有的头像用本地地址，避免异步上传时序造成 404
                if "local=1" in raw or (
                    raw_path.startswith(("/uploads/avatar/", "/uploads/reader/avatar/"))
                    and _local_exists(raw_path)
                    and (raw_path.startswith("/uploads/avatar/") or not _remote_exists(raw_path))
                ):
                    return raw
                rel = raw_path
                return s3.presign(cfg, rel, expires)

            return _REL_RE.sub(_one, text)

        return rewrite_outside_code(html, _sign)

    # 公共读：统一换成直链；本地文件被清理过、只剩远端副本的图也能正常显示
    def _sub(text: str) -> str:
        def _one(match: re.Match) -> str:
            raw = match.group(0)
            raw_path = unquote(raw.split("?", 1)[0])
            # 本地有、远端没有的头像用本地地址，避免异步上传时序造成 404
            if "local=1" in raw or (
                raw_path.startswith(("/uploads/avatar/", "/uploads/reader/avatar/"))
                and _local_exists(raw_path)
                and (raw_path.startswith("/uploads/avatar/") or not _remote_exists(raw_path))
            ):
                return raw
            rel = raw_path
            return cfg.url_of(rel)

        return _REL_RE.sub(_one, text)

    return rewrite_outside_code(html, _sub)


def normalize_text(text: str) -> str:
    """把 OSS 直链 / 预签名 URL / 代理路径剥回 /uploads/...。

    保存文章或评论前调用：编辑器里可能粘贴了带签名的临时链接，
    直接落库会在有效期后变成死链。
    """
    if not text:
        return text
    cfg = get_cfg()
    if cfg is None:
        return text
    bases = sorted(public_bases(), key=len, reverse=True)
    for base in bases:
        text = re.sub(
            re.escape(base) + r"/(uploads/[^\s\"'<>()\[\]]+)",
            lambda m: "/" + m.group(1).split("?", 1)[0].split("#", 1)[0],
            text,
        )
    text = _MEDIA_RE.sub(lambda m: "/" + m.group(0)[len("/oss-media/"):], text)
    return text


def public_bases() -> list[str]:
    """当前与历史公网基址。改过 public_base 之后，旧地址也要能回写。"""
    data = raw_config()
    bases: list[str] = []
    for item in (data.get("public_base"), data.get("public_base_prev")):
        value = str(item or "").strip().rstrip("/")
        if value and value not in bases:
            bases.append(value)
    cfg = get_cfg()
    if cfg is not None:
        base = cfg.public_root.rstrip("/")
        if base not in bases:
            bases.append(base)
    return bases


# ── 上传 ──────────────────────────────────────────────

def _content_type(path: Path) -> str:
    guess, _ = mimetypes.guess_type(path.name)
    return guess or "application/octet-stream"


def _remember_sign_host(value: bool) -> None:
    """把「不签 host」的探测结果写回配置，避免每次上传都先失败一次。"""
    from services import plugins as plugins_service

    data = raw_config()
    if data.get("sign_host") is value:
        return
    data["sign_host"] = value
    plugins_service.save_config(KEY, data)


def _call_s3(cfg: s3.S3Config, func):
    """执行一次 S3 调用；签名被服务端拒绝时，退化为「不签 host」重试。

    这是为了兼容前面挂了反向代理、且代理改写了 Host 头的部署：
    标准 SigV4 会把 host 纳入签名，Host 一变签名就对不上。
    """
    from dataclasses import replace

    try:
        return func(cfg)
    except s3.S3Error as exc:
        if exc.code == "SignatureDoesNotMatch" and cfg.sign_host:
            result = func(replace(cfg, sign_host=False))
            _remember_sign_host(False)
            logger.warning("对象存储签名方式已自动降级：检测到 Host 被改写")
            return result
        raise


def publish(local_path: str | Path, rel_url: str) -> str:
    """把本地文件额外传一份到 OSS，返回公网 URL；失败返回空串由调用方回退。"""
    if str(rel_url or "").lstrip("/").startswith("uploads/avatar/"):
        return ""  # 站点头像始终留在本地，不进对象存储
    if not is_enabled():
        return ""
    cfg = get_cfg()
    if cfg is None:
        return ""
    path = Path(local_path)
    try:
        data = path.read_bytes()
        _call_s3(cfg, lambda c: s3.put(c, rel_url, data, _content_type(path)))
    except Exception as exc:  # noqa: BLE001
        # 上传失败不能让文章插入死链：记日志，返回空串，调用方继续用本地地址
        logger.warning("OSS 上传失败 %s：%s", rel_url, exc)
        return ""
    _record_object(cfg.key_of(rel_url), len(data))
    _invalidate_head(rel_url)
    return url_for(rel_url)


def ensure_remote(local_path: str | Path, rel_url: str) -> str:
    """本地已有文件：远端存在就只返回 URL，不存在才补传一次。

    项目 README 图片是「先下载到本地、再渲染」的，历史缓存从未上传过 OSS，
    所以不能只取 URL，否则私有桶下代理回源会失败。
    """
    cfg = get_cfg()
    if cfg is None:
        return ""
    try:
        if s3.head(cfg, cfg.key_of(rel_url)):
            return url_for(rel_url)
    except Exception:  # noqa: BLE001
        pass
    return publish(local_path, rel_url)


def exists(rel_url: str) -> bool:
    """远端是否已有这个对象。

    不做长期缓存，由调用方（编辑器音视频预览）自己控制频率：
    文件可能刚补传过，永久缓存会把「后来才有」判定成没有。
    """
    if not is_enabled():
        return False
    cfg = get_cfg()
    if cfg is None:
        return False
    try:
        return bool(s3.head(cfg, cfg.key_of(rel_url)))
    except Exception:  # noqa: BLE001
        return False


# ── 编辑器预览副本 ────────────────────────────────────
# 预览只用于判断版式，用不到原图分辨率。上传时额外转一份 960 宽 WebP 存进
# previews/ 前缀，编辑器预览直接取它：既走对象存储，又只有几十 KB。
# 命名沿用原相对路径再补 .webp，删原图时能反查出对应副本。

PREVIEW_WIDTH = 960


def preview_rel(rel_url: str) -> str:
    """站内规范路径 → 预览副本的虚拟路径（/previews/2026/11/a.png.webp）。"""
    rel = str(rel_url or "").lstrip("/")
    if rel.startswith("uploads/"):
        rel = rel[len("uploads/"):]
    # .webp 源不再生成副本（见 _store_preview）；这里返回空串做兜底，
    # 避免旧调用拼出 a.webp.webp
    if rel.lower().endswith(".webp"):
        return ""
    return f"/previews/{rel}.webp"


def preview_of_key(key: str) -> str:
    """previews/ 下的副本 key → 对应原图 key；不是副本则返回空串。

    key 的两种形式都要兼容：
    - previews/2026/11/a.png.webp        （顶层前缀）
    - uploads/previews/2026/11/a.png.webp（桶前缀为 uploads 时）
    """
    parts = str(key or "").lstrip("/").split("/")
    if "previews" not in parts:
        return ""
    idx = parts.index("previews")
    rest = parts[idx + 1:]
    if not rest or not rest[-1].endswith(".webp"):
        return ""
    rest[-1] = rest[-1][: -len(".webp")]
    base = parts[:idx]
    # parts 里已经带 uploads/ 时不要再插一层，否则会得到 uploads/uploads/...
    if not base or base[-1] != "uploads":
        base = base + ["uploads"]
    return "/".join(base + rest)


def publish_preview(local_path: str | Path, rel_url: str) -> str:
    """把预览副本推一份到对象存储；失败返回空串（不影响上传主流程）。"""
    if not is_enabled():
        return ""
    cfg = get_cfg()
    if cfg is None:
        return ""
    path = Path(local_path)
    target = preview_rel(rel_url)
    if not target:
        return ""
    try:
        data = path.read_bytes()
        s3.put(cfg, target, data, "image/webp")
    except Exception as exc:  # noqa: BLE001
        logger.warning("预览副本上传失败 %s：%s", rel_url, exc)
        return ""
    _record_object(cfg.key_of(target), len(data))
    return target


def preview_url(rel_url: str, expires: int | None = None) -> str:
    """编辑器预览该用的远端地址：优先预览副本，其次原图；都没有返回空串。"""
    cfg = get_cfg()
    if cfg is None:
        return ""
    ttl = expires or presign_expires()
    for candidate in (preview_rel(rel_url), rel_url):
        if not candidate:
            continue
        try:
            if not s3.head(cfg, cfg.key_of(candidate)):
                continue
        except Exception:  # noqa: BLE001
            return ""
        if bucket_policy() == "private":
            return s3.presign(cfg, candidate, ttl)
        return cfg.url_of(candidate)
    return ""


# ── 对象清单（孤儿扫描的唯一数据来源） ──────────────

def _record_object(key: str, size: int = 0) -> None:
    """记录「本插件上传过」的对象。孤儿扫描只在这张表里找候选。"""
    try:
        import db

        db.execute(
            "INSERT INTO oss_objects (key, size, uploaded_at) "
            "VALUES (?, ?, datetime('now','localtime')) "
            "ON CONFLICT(key) DO UPDATE SET size = excluded.size, "
            "uploaded_at = excluded.uploaded_at",
            (key, int(size or 0)),
        )
    except Exception:  # noqa: BLE001
        logger.exception("记录 OSS 对象失败：%s", key)


def _forget_object(key: str) -> None:
    try:
        import db

        db.execute("DELETE FROM oss_objects WHERE key = ?", (key,))
    except Exception:  # noqa: BLE001
        logger.exception("移除 OSS 对象记录失败：%s", key)


def delete_remote(rel_url: str) -> None:
    """删除 OSS 上的同名对象（本地删除时同步，失败只记日志）。

    展示图会连带删掉它的预览副本，避免「图删了、previews 里还留一份」。
    """
    if not is_enabled():
        return
    cfg = get_cfg()
    if cfg is None:
        return
    for target in (rel_url, preview_rel(rel_url)):
        try:
            s3.delete(cfg, target)
            _forget_object(cfg.key_of(target))
            _invalidate_head(target)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OSS 删除失败 %s：%s", target, exc)


# ── URL 转换 ──────────────────────────────────────────

def _local_exists(rel: str) -> bool:
    rel = unquote(rel).replace("\\", "/").lstrip("/")
    if not rel.startswith("uploads/"):
        return False
    path = (Path(UPLOADS_DIR) / rel[len("uploads/"):]).resolve()
    try:
        path.relative_to(Path(UPLOADS_DIR).resolve())
    except ValueError:
        return False
    return path.is_file()


# HEAD 结果缓存：回写时同一对象可能被多篇文章引用，避免重复请求 OSS
_HEAD_TTL = 300
_head_cache: dict[str, tuple[float, bool]] = {}


def _invalidate_head(rel: str) -> None:
    """对象上传/删除后清除存在性缓存，避免头像判断长期停在旧状态。"""
    _head_cache.pop(str(rel or "").lstrip("/"), None)


def _remote_exists(rel: str) -> bool:
    key = str(rel or "").lstrip("/")
    cached = _head_cache.get(key)
    if cached and time.time() - cached[0] < _HEAD_TTL:
        return cached[1]
    cfg = get_cfg()
    if cfg is None:
        return False
    try:
        ok = s3.head(cfg, key)
    except Exception:  # noqa: BLE001
        ok = False
    _head_cache[key] = (time.time(), ok)
    return ok


def ensure_local(rel: str) -> Path | None:
    """返回本地副本；没有就带签名从 OSS 拉一份并缓存下来。

    私有桶里的对象可能是用户直接传到 OSS 的（本地从来就没有），
    站点代理必须能回源，否则这类图片在私有模式下必然 404。
    """
    rel = "/" + str(rel or "").lstrip("/")
    if not rel.startswith("/uploads/"):
        return None
    local = (Path(UPLOADS_DIR) / rel[len("/uploads/"):]).resolve()
    try:
        local.relative_to(Path(UPLOADS_DIR).resolve())
    except ValueError:
        return None
    if local.is_file():
        return local
    cfg = get_cfg()
    if cfg is None:
        return None
    try:
        data = s3.fetch(cfg, rel)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OSS 回源失败 %s：%s", rel, exc)
        return None
    if data is None:
        return None
    try:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
    except OSError:
        return None
    logger.info("已从 OSS 回源并缓存：%s", rel)
    return local


def _normalize_for_remote(text: str) -> str:
    """把 OSS 直链与代理路径统一成 /uploads/...（不判断本地是否存在）。

    用于迁移回写：只要对象在 OSS 上，私有模式就能通过代理回源，
    不该因为本地缺副本而漏改。
    """
    bases = sorted(public_bases(), key=len, reverse=True)
    for base in bases:
        # 兼容历史脏数据：base/oss-media/uploads/...（之前回写拼错的形式）
        text = re.sub(
            re.escape(base) + r"/oss-media/(uploads/[^\s\"'<>()\[\]]+)",
            lambda m: "/" + m.group(1),
            text,
        )
        text = re.sub(
            re.escape(base) + r"/(uploads/[^\s\"'<>()\[\]]+)",
            lambda m: "/" + m.group(1),
            text,
        )
    text = _MEDIA_RE.sub(lambda m: "/" + m.group(0)[len("/oss-media/"):], text)
    return text


def to_remote_text(text: str) -> tuple[str, int]:
    """把文本里的站内上传路径换成目标地址（公共桶直链 / 私有桶代理）。"""
    cfg = get_cfg()
    if cfg is None or not text:
        return text, 0
    # 先把已有的 OSS 直链和代理路径归一到 /uploads/，
    # 否则「在已经是指链的 URL 里再替换一次」会拼出重复地址。
    text = _normalize_for_remote(text)
    if "/uploads/" not in text:
        return text, 0
    replaced = 0

    def _sub(match: re.Match) -> str:
        nonlocal replaced
        raw = match.group(0)
        rel_path, sep, query = raw.partition("?")
        rel = unquote(rel_path)
        if rel.startswith("/uploads/avatar/"):
            return raw  # 站点头像留在本地，不参与回写
        if not _local_exists(rel):
            # 私有模式下，本地没有但 OSS 上确实存在的对象也可以回写：
            # 代理路由会带签名回源并缓存，图片照样能显示。
            if not (bucket_policy() == "private" and proxy_enabled() and _remote_exists(rel)):
                return raw
        replaced += 1
        url = url_for(rel)
        return url + (sep + query if sep else "")

    return _REL_RE.sub(_sub, text), replaced


def to_local_text(text: str) -> tuple[str, int]:
    """把文本里的 OSS 地址 / 私有代理路径换回站内上传路径（本地文件必须存在）。"""
    if not text:
        return text, 0
    bases = public_bases()
    replaced = 0

    def _sub_url(match: re.Match) -> str:
        nonlocal replaced
        url = match.group(0)
        # 从长到短匹配：改了 public_base 之后，短前缀可能只是长前缀的一段，
        # 先匹配短的会把 path 切错，导致回写漏掉。
        for base in sorted(bases, key=len, reverse=True):
            if not url.startswith(base + "/"):
                continue
            path_part = url[len(base):].split("?", 1)[0].split("#", 1)[0]
            rel = unquote(path_part)
            if not rel.startswith("/uploads/"):
                continue
            if not _local_exists(rel):
                # 本地没有回退副本：保留 OSS 地址，宁可有图也不要裂图
                return url
            replaced += 1
            query = url[len(base) + len(path_part):]
            return rel + query
        return url

    def _sub_media(match: re.Match) -> str:
        nonlocal replaced
        raw = match.group(0)
        # raw 形如 /oss-media/uploads/2026/11/a.jpg，去掉前缀后就是 uploads/...
        rel = unquote(raw[len("/oss-media/"):])
        if not _local_exists("/" + rel):
            return raw
        replaced += 1
        return "/" + rel

    if bases:
        text = _URL_RE.sub(_sub_url, text)
    # 私有桶的站点代理路径也要能回退（不依赖 public_base）
    text = _MEDIA_RE.sub(_sub_media, text)
    return text, replaced


# ── 数据库回写 ────────────────────────────────────────

def _backup_db(reason: str) -> str:
    """回写前备份数据库；失败不阻断（由调用方记录）。"""
    try:
        import db
        from db import _backup_database

        return _backup_database(db.get_db(), reason)
    except Exception as exc:  # noqa: BLE001
        logger.warning("回写前备份数据库失败：%s", exc)
        return ""


def rewrite_db(direction: str) -> dict:
    """把内容字段里的上传地址批量改写。

    direction='remote'：本地 /uploads/... → OSS URL
    direction='local' ：OSS URL → 本地 /uploads/...
    """
    import db

    convert = to_remote_text if direction == "remote" else to_local_text
    stats = {"rows": 0, "refs": 0, "backup": "", "tables": {}}
    if direction not in {"remote", "local"}:
        return stats

    _head_cache.clear()

    stats["backup"] = _backup_db(f"oss_rewrite_{direction}")
    for table, columns in TARGETS:
        row_changed = 0
        ref_changed = 0
        try:
            rows = db.query(f"SELECT rowid AS _rid, {', '.join(columns)} FROM {table}")
        except Exception:
            continue
        for row in rows:
            updates: dict[str, str] = {}
            for column in columns:
                value = row[column]
                if not isinstance(value, str) or not value:
                    continue
                new_value, count = convert(value)
                if count:
                    updates[column] = new_value
                    ref_changed += count
            if not updates:
                continue
            assignments = ", ".join(f"{name} = ?" for name in updates)
            db.execute(
                f"UPDATE {table} SET {assignments} WHERE rowid = ?",
                (*updates.values(), row["_rid"]),
            )
            row_changed += 1
        if row_changed:
            stats["tables"][table] = {"rows": row_changed, "refs": ref_changed}
        stats["rows"] += row_changed
        stats["refs"] += ref_changed
    return stats


def count_remote_refs() -> int:
    """统计数据库里还引用着多少个 OSS 上传地址，用于后台状态显示。"""
    import db

    bases = public_bases()
    if not bases:
        return 0
    total = 0
    for table, columns in TARGETS:
        try:
            rows = db.query(f"SELECT {', '.join(columns)} FROM {table}")
        except Exception:
            continue
        for row in rows:
            for column in columns:
                value = row[column]
                if not isinstance(value, str):
                    continue
                for base in bases:
                    # 只统计真正的上传地址，避免把插件配置里的 endpoint/public_base 算进来
                    total += value.count(base + "/uploads/")
    return total


def count_local_refs() -> int:
    """统计数据库里还引用着多少个站内上传路径。"""
    import db

    total = 0
    for table, columns in TARGETS:
        try:
            rows = db.query(f"SELECT {', '.join(columns)} FROM {table}")
        except Exception:
            continue
        for row in rows:
            for column in columns:
                value = row[column]
                if isinstance(value, str) and "/uploads/" in value:
                    total += len(_REL_RE.findall(value))
    return total


# ── 存量迁移 ──────────────────────────────────────────

def list_local_files() -> list[tuple[str, Path]]:
    """列出可迁移的本地文件：/uploads/ 相对地址 + 绝对路径。"""
    root = Path(UPLOADS_DIR)
    result: list[tuple[str, Path]] = []
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        parts = rel.split("/")
        if any(part.startswith(".") for part in parts):
            continue
        if parts[0] in _SKIP_DIRS:
            continue
        result.append(("/uploads/" + rel, path))
    return result


def migrate_batch(offset: int, limit: int) -> dict:
    """上传一批本地文件；已存在的对象直接跳过，保证重复点击不会重复传。"""
    cfg = get_cfg()
    if cfg is None:
        return {"error": "对象存储配置不完整"}
    files = list_local_files()
    total = len(files)
    chunk = files[max(0, offset): max(0, offset) + max(1, limit)]
    uploaded = skipped = 0
    failed: list[dict] = []
    for rel, path in chunk:
        try:
            if _call_s3(cfg, lambda c: s3.head(c, rel)):
                skipped += 1
                continue
            data = path.read_bytes()
            _call_s3(cfg, lambda c: s3.put(c, rel, data, _content_type(path)))
            _record_object(cfg.key_of(rel), len(data))
            uploaded += 1
        except Exception as exc:  # noqa: BLE001
            failed.append({"rel": rel, "error": str(exc)[:160]})
    next_offset = max(0, offset) + len(chunk)
    done = next_offset >= total
    if done:
        try:
            mark_migrated()
        except Exception:  # noqa: BLE001
            logger.warning("记录迁移时间失败")
    return {
        "total": total,
        "offset": max(0, offset),
        "processed": len(chunk),
        "uploaded": uploaded,
        "skipped": skipped,
        "failed": failed,
        "next": next_offset,
        "done": done,
    }


def mark_migrated() -> None:
    """记录迁移完成时间，后台状态页用。"""
    from datetime import datetime

    from services import plugins as plugins_service

    data = raw_config()
    data["migrated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plugins_service.save_config(KEY, data)


# ── OSS 孤儿扫描 ──────────────────────────────────────
# 安全边界（比本地清理严格得多，因为 OSS 删除不可恢复）：
#   1. 候选只来自 oss_objects——本插件上传过的对象；绝不遍历桶，
#      不会碰用户直接传到 OSS 的其它文件；
#   2. 删除前重新算一遍数据库引用，仍被引用的直接跳过；
#   3. 只允许删除配置前缀（默认 uploads/）下的 key；
#   4. 只删 OSS 对象，不动本地回退副本，停用后图还能回来；
#   5. 单次最多 200 个，且必须在前端输入确认词。

def referenced_keys() -> set[str]:
    """收集数据库里仍被引用的对象 key（本地路径与 OSS 地址都识别）。"""
    import db

    cfg = get_cfg()
    if cfg is None:
        return set()
    prefix = cfg.prefix.strip("/")
    bases = public_bases()
    keys: set[str] = set()

    for table, columns in TARGETS:
        try:
            rows = db.query(f"SELECT {', '.join(columns)} FROM {table}")
        except Exception:
            continue
        for row in rows:
            for column in columns:
                value = row[column]
                if not isinstance(value, str):
                    continue
                # 站内路径：/uploads/2026/11/a.jpg -> uploads/2026/11/a.jpg
                for match in _REL_RE.finditer(value):
                    rel = unquote(match.group(0).split("?", 1)[0])
                    if rel.startswith("/uploads/"):
                        keys.add(f"{prefix}/{rel[len('/uploads/'):]}")
                # OSS 地址：{base}/uploads/2026/11/a.jpg -> 同一个 key
                for base in bases:
                    marker = f"{base}/{prefix}/"
                    start = 0
                    while True:
                        index = value.find(marker, start)
                        if index < 0:
                            break
                        end = index + len(marker)
                        while end < len(value) and value[end] not in " \t\r\n\"'<>()[]":
                            end += 1
                        keys.add(unquote(value[index + len(base) + 1:end]))
                        start = end
    return keys


LIST_MAX_OBJECTS = 20000


def list_remote_objects(prefix: str | None = None, max_objects: int = LIST_MAX_OBJECTS) -> list[dict]:
    """遍历桶里的对象（ListObjectsV2），默认只看配置前缀（uploads/）。

    历史版本上传的对象、手动放进桶里的文件、别的工具传的对象都在桶里，
    只查 oss_objects 清单会漏掉它们，所以孤儿扫描以桶为准。
    """
    cfg = get_cfg()
    if cfg is None:
        return []
    target = prefix if prefix is not None else cfg.prefix.strip("/") + "/"
    items: list[dict] = []
    token = ""
    for _ in range(40):  # 最多 40 页，防止异常配置下无限翻页
        batch, token = s3.list_objects(cfg, target, token, min(1000, max_objects - len(items)))
        items.extend(batch)
        if not token or len(items) >= max_objects:
            break
    return items


def scan_orphans(limit: int = 500) -> list[dict]:
    """列出「对象存储上存在、但数据库已不再引用」的附件。

    以 ListObjectsV2 遍历桶为准（历史对象、手动上传的也能识别）；
    列举失败时回退到 oss_objects 清单，至少还能清掉本插件传过的孤儿。
    """
    import db

    cfg = get_cfg()
    if cfg is None:
        return []
    prefix = cfg.prefix.strip("/")
    referenced = referenced_keys()

    candidates: list[dict] = []
    try:
        candidates = list_remote_objects()
    except Exception as exc:  # noqa: BLE001
        logger.warning("列举对象失败，回退到 oss_objects 清单：%s", exc)
        rows = db.query(
            "SELECT key, size, uploaded_at FROM oss_objects ORDER BY uploaded_at DESC, key ASC LIMIT ?",
            (limit,),
        )
        candidates = [
            {"key": str(row["key"] or ""), "size": int(row["size"] or 0),
             "modified": str(row["uploaded_at"] or "")}
            for row in rows
        ]

    result: list[dict] = []
    # 与本地一致：最近 24 小时新上传的对象先保护，避免删掉编辑器里还没提交的图
    from datetime import datetime, timedelta, timezone

    protect_after = datetime.now(timezone.utc) - timedelta(hours=24)
    for item in candidates:
        key = str(item.get("key") or "").lstrip("/")
        if not key or not key.startswith(prefix + "/"):
            continue
        modified = str(item.get("modified") or "")
        if modified:
            try:
                stamp = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp >= protect_after:
                    continue
            except (ValueError, TypeError):
                pass
        if key in referenced:
            continue
        origin = preview_of_key(key)
        if origin and origin in referenced:
            # 预览副本属于原图的附属对象：原图还被引用时不算孤儿
            continue
        rel = key[len(prefix) + 1:]
        # 头像 / AI 头像 / 项目文件由各自的入口管理，不当孤儿。
        # uploads/previews/ 是旧版派生副本路径（新版顶层 previews/ 不在本扫描的
        # 枚举前缀内，不会被列出）；原图仍被引用时上面已按 preview_of_key 跳过，
        # 能走到这里的都是原图已不存在/无引用的残留孤儿。后台对仅 OSS 的条目
        # 会按完整对象 key 删除，不走 upload.delete_rel（它会把 previews 当保护目录）。
        if rel.startswith(("avatar/", "ai-avatar/", "projects/", "reader/")):
            continue
        local = Path(UPLOADS_DIR) / rel
        name = key.rsplit("/", 1)[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        size = int(item.get("size") or 0)
        result.append(
            {
                "key": key,
                "rel": rel,
                "url": url_for("/" + key),
                "size": size,
                "size_text": _fmt_size(size),
                "uploaded_at": str(item.get("modified") or ""),
                "has_local": local.is_file(),
                "ext": ext,
                "is_image": ext in {"jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "avif", "ico"},
            }
        )
        if len(result) >= limit:
            break
    return result


def _fmt_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def delete_orphans(keys: list[str]) -> dict:
    """删除指定的 OSS 孤儿对象；删除前重新校验引用与前缀。

    删除是网络操作，几十个串行要等很久；先过滤再并发删，
    前端每批 5 个请求，进度才走得动。
    """
    cfg = get_cfg()
    if cfg is None:
        return {"error": "配置不完整"}
    prefix = cfg.prefix.strip("/")
    referenced = referenced_keys()
    deleted = 0
    skipped: list[dict] = []
    failed: list[dict] = []
    candidates: list[str] = []

    for raw in keys[:200]:
        key = str(raw or "").lstrip("/")
        if not key or not key.startswith(prefix + "/"):
            skipped.append({"key": key, "reason": "不在配置前缀内"})
            continue
        if key in referenced:
            skipped.append({"key": key, "reason": "仍被内容引用"})
            continue
        origin = preview_of_key(key)
        if origin and origin in referenced:
            # 预览副本跟着原图走：原图还被引用，副本就不能单独删
            skipped.append({"key": key, "reason": "对应原图仍被内容引用"})
            continue
        candidates.append(key)

    from flask import current_app, has_app_context

    app = current_app._get_current_object() if has_app_context() else None

    def _one(key: str) -> tuple[str, str]:
        try:
            if app is not None:
                # _forget_object 要写数据库；线程池里没有请求上下文，必须显式带上
                with app.app_context():
                    s3.delete(cfg, key)
                    _forget_object(key)
            else:
                s3.delete(cfg, key)
            return key, ""
        except Exception as exc:  # noqa: BLE001
            return key, str(exc)[:160]

    if candidates:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for key, error in pool.map(_one, candidates):
                if error:
                    failed.append({"key": key, "error": error})
                else:
                    deleted += 1

    return {"deleted": deleted, "skipped": skipped, "failed": failed}
