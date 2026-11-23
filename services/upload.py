"""上传文件服务：校验、保存、水印、缩略图、孤儿扫描。"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from werkzeug.datastructures import FileStorage

from config import (
    BACKUPS_DIR, CACHE_DIR, COMMENT_IMAGE_MAX_SIZE, FILE_EXTS, FONTS_DIR,
    IMAGE_EXTS, MEDIA_EXTS, UPLOADS_DIR,
)
from services import settings

BLOCKED_EXTS = {
    "php", "php3", "php4", "php5", "php7", "php8", "phtml", "phar", "pht", "shtml",
    "htaccess", "htpasswd", "cgi", "pl", "asp", "aspx", "jsp", "jspx",
    "exe", "dll", "sh", "bat", "cmd", "com", "scr", "msi", "vbs",
    "html", "htm", "xhtml", "svg",
}

logger = logging.getLogger(__name__)

# ── 远端存储钩子 ──────────────────────────────────────
# 插件（对象存储等）通过 register_remote() 注册发布函数：
#   入参 (本地文件路径, 站内相对 URL)，返回公网 URL；返回空串表示失败、回退本地。
# 核心代码不认识任何具体插件：没有注册时，下面这些函数等同于不存在。
_remote_publishers: list = []


def register_remote(func) -> None:
    """注册一个远端发布函数（插件启用时调用）。"""
    if func not in _remote_publishers:
        _remote_publishers.append(func)


def unregister_remote(func) -> None:
    """注销远端发布函数（插件停用时调用），停用后立即恢复本地规则。"""
    if func in _remote_publishers:
        _remote_publishers.remove(func)


# 惰性补注册节流：本进程钩子为空时，最多每隔这段时间查一次数据库启用标记。
# 钩子一旦存在，_ensure_hooks() 首行即返回，正常上传/渲染零额外开销。
_last_hook_check = 0.0
_HOOK_CHECK_INTERVAL = 5.0


def _ensure_hooks() -> None:
    """按数据库启用标记，为本进程惰性补注册远端钩子。

    多进程部署下，运行时启用对象存储插件只会在处理启用请求的那个进程注册钩子，
    其余进程 _remote_publishers 为空，导致上传不 sync 到 OSS（与文件大小无关）。
    这里在钩子为空时补加载已启用插件，使各进程无需重启即可生效。
    没有应用上下文（CLI 迁移等）时跳过，行为与原来一致。
    """
    global _last_hook_check
    if _remote_publishers:
        return
    now = time.time()
    if now - _last_hook_check < _HOOK_CHECK_INTERVAL:
        return
    _last_hook_check = now
    try:
        from flask import current_app, has_app_context

        if not has_app_context():
            return
        from services import plugins as plugins_service

        plugins_service.ensure_enabled_loaded(current_app._get_current_object())
    except Exception:  # noqa: BLE001
        logger.warning("惰性注册远端钩子失败", exc_info=True)


def remote_active() -> bool:
    """当前是否有「真正可用」的远端存储接管上传。

    发布函数可以挂 ``is_active`` 属性做二次判断（例如插件已启用但配置不完整）。
    没有任何远端时返回 False，孤儿清理等逻辑保持原样。
    """
    _ensure_hooks()
    for func in list(_remote_publishers):
        checker = getattr(func, "is_active", None)
        if checker is None:
            return True
        try:
            if checker():
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def publish(local_path, rel_url: str) -> str:
    """把刚写入本地的文件交给远端存储；没有可用远端时返回空串。"""
    _ensure_hooks()
    for func in list(_remote_publishers):
        try:
            url = func(local_path, rel_url)
        except Exception:  # noqa: BLE001
            logger.exception("远端发布失败：%s", rel_url)
            continue
        if url:
            return str(url)
    return ""


# ── 后台发布 ──────────────────────────────────────────
# 上传请求只等「本地落盘 + 校验」，远端上传放后台，编辑器拿回 URL 就能立刻插入。
# 一致性靠保存前的 sync_remote_urls() 兜底：先等后台传完，再确认远端是否真有对象。

_publish_guard = threading.Lock()
_publish_locks: dict[str, threading.RLock] = {}
_pending_events: dict[str, threading.Event] = {}
_failed_uploads: set[str] = set()

# 浏览器直传（presigned PUT）状态：
# - _direct_done：后台推送等待的「直传已完成」事件，每个待传文件一个；
# - _direct_pending：生成 PUT URL 的时间戳，用来校验通知接口的合法性（半小时有效）。
# 浏览器直传成功后调 mark_direct_done()，后台推送就跳过，避免再走慢链路。
DIRECT_GRACE = 20.0  # 后台等直传结果的秒数；超时则兜底由服务器推
_direct_done: dict[str, threading.Event] = {}
_direct_pending: dict[str, float] = {}


def _lock_for(rel_url: str) -> threading.RLock:
    """同一个文件只允许一个线程在传（后台 publish 与保存前补传可能撞车）。"""
    with _publish_guard:
        lock = _publish_locks.get(rel_url)
        if lock is None:
            lock = _publish_locks[rel_url] = threading.RLock()
        return lock


def wait_remote(rel_url: str, timeout: float = 30.0) -> None:
    """等这个文件的后台发布结束（已在跑才等，没记录立即返回）。"""
    with _publish_guard:
        event = _pending_events.get(rel_url)
    if event is not None:
        event.wait(timeout)


def defer_publish(local_path, rel_url: str) -> None:
    """后台把文件推到远端，并顺手生成预览副本。

    原图仍会完整上传，只是不再阻塞 HTTP 响应；保存文章/评论时
    sync_remote_urls() 会等它结束并在必要时补传，前台不会拿到死链。
    线程里要用 settings 与插件配置，所以带着创建时的应用上下文跑。
    """
    try:
        if not remote_active():
            return
    except Exception:  # noqa: BLE001
        # 没有应用上下文（CLI 迁移等）：退回同步发布，行为与旧版一致
        try:
            publish(local_path, rel_url)
        except Exception:  # noqa: BLE001
            logger.warning("同步发布失败：%s", rel_url, exc_info=True)
        return

    event = threading.Event()
    with _publish_guard:
        _pending_events[rel_url] = event

    try:
        from flask import current_app, has_app_context

        app = current_app._get_current_object() if has_app_context() else None
    except Exception:  # noqa: BLE001
        app = None

    def run() -> None:
        ok = False
        try:
            if app is not None:
                with app.app_context():
                    ok = _publish_and_preview(local_path, rel_url, event)
            else:
                ok = _publish_and_preview(local_path, rel_url, event)
        except Exception:  # noqa: BLE001
            logger.warning("后台上传失败：%s", rel_url, exc_info=True)
        finally:
            event.set()
            with _publish_guard:
                _pending_events.pop(rel_url, None)
                _direct_done.pop(rel_url, None)
                _direct_pending.pop(rel_url, None)
                if ok:
                    _failed_uploads.discard(rel_url)
                else:
                    # 失败留个记号：保存文章时只对这些补传，不用每张图都去 HEAD
                    if len(_failed_uploads) > 1000:
                        _failed_uploads.clear()
                    _failed_uploads.add(rel_url)
            _forget_preview_cache(rel_url)

    threading.Thread(target=run, daemon=True, name="upload-publish").start()


def _publish_and_preview(local_path, rel_url: str, done: threading.Event | None = None) -> bool:
    """上传展示图 + 预览副本，返回远端是否拿到展示图。

    浏览器直传（presigned PUT）流程：
    - 若 presign_put_url() 已登记「等待直传」，先等一小段时间看浏览器是否成功；
      成功则跳过服务器推送（省掉慢链路），只补一份小预览副本；
    - 超时未收到通知（浏览器直传失败/未实现）才走服务器兜底推送。
    旧客户端不会生成 PUT URL，也就没有登记，行为与以前完全一致。

    展示图一确定就 set(done)，让正在保存文章的那个请求先走；
    预览副本（PIL 缩放 + 小文件 PUT）继续在后台跑，不必拖住保存。
    """
    with _publish_guard:
        direct_event = _direct_done.get(rel_url)
        waiting_direct = rel_url in _direct_pending
    direct_ok = False
    if waiting_direct and direct_event is not None:
        direct_ok = direct_event.wait(DIRECT_GRACE)
    if direct_ok:
        url = remote_url(rel_url) or "direct"
    else:
        with _lock_for(rel_url):
            url = publish(local_path, rel_url)
    if done is not None:
        done.set()
    if not url:
        return False
    _store_preview(Path(local_path), rel_url)
    return True


def _forget_preview_cache(rel_url: str) -> None:
    """上传完成后清掉「远端没有」的预览缓存，下一次预览就能直接走对象存储。"""
    with _publish_guard:
        for key in [k for k in _remote_preview_cache if k[0] == rel_url]:
            _remote_preview_cache.pop(key, None)


def sync_remote_urls(text: str) -> None:
    """保存前兜住「上传已返回、远端还没传完」的那几张。

    只处理两种：后台还在传的（等它结束）和传失败的（补传一次）。
    不逐个 HEAD 历史文件——对象存储一次 HEAD 就要几百毫秒，
    十张图就把保存拖慢好几秒，而历史文件在 v3.9.28 之前都是同步传上去的。
    """
    if not text:
        return
    try:
        if not remote_active():
            return
    except Exception:  # noqa: BLE001
        return
    for rel_url in extract_urls(text):
        if not rel_url.startswith("/uploads/"):
            continue
        # 后台可能还在传：等它结束（最多 30 秒），避免保存时远端还缺文件
        wait_remote(rel_url)
        with _publish_guard:
            failed = rel_url in _failed_uploads
        if not failed:
            continue
        path = resolve(rel_url[len("/uploads/"):])
        if path is None or not path.is_file():
            continue
        try:
            if ensure_remote(path, rel_url):
                with _publish_guard:
                    _failed_uploads.discard(rel_url)
        except Exception:  # noqa: BLE001
            logger.warning("保存前补传失败：%s", rel_url)


def delete_remote(rel_url: str) -> None:
    """删除远端同名对象（本地删除时同步）；没有远端能力时什么也不做。"""
    _ensure_hooks()
    for func in list(_remote_publishers):
        deleter = getattr(func, "delete", None)
        if deleter is None:
            continue
        try:
            deleter(rel_url)
        except Exception:  # noqa: BLE001
            logger.warning("远端删除失败：%s", rel_url)


def remote_url(rel_url: str) -> str:
    """只取远端地址、不上传；用于「文件已经存在」的场景。

    例如项目 README 图片缓存：文件可能早就在本地了，
    但页面仍然应该展示远端地址，没必要每次渲染都重传一遍。
    """
    _ensure_hooks()
    for func in list(_remote_publishers):
        getter = getattr(func, "url_for", None)
        if getter is None:
            continue
        try:
            url = getter(rel_url)
        except Exception:  # noqa: BLE001
            continue
        if url:
            return str(url)
    return ""


def presign_put_url(rel_url: str) -> str:
    """生成 PUT 预签名 URL 供浏览器直传对象存储。

    浏览器拿到后直接 PUT，绕开「服务器 → 对象存储」这段公网链路；
    服务端后台推送作为兜底保留。对象 key 由 rel 推导，与 /uploads/ 一一对应。
    未启用远端能力时返回空串。

    成功生成 URL 时会登记「等待直传」状态：后台推送会先等一小段时间，
    等浏览器直传成功的通知；超时未收到才走服务器兜底推送。
    """
    _ensure_hooks()
    for func in list(_remote_publishers):
        getter = getattr(func, "presign_put", None)
        if getter is None:
            continue
        try:
            url = getter(rel_url)
        except Exception:  # noqa: BLE001
            continue
        if url:
            with _publish_guard:
                _direct_pending[rel_url] = time.time()
                # 后台线程可能已经先跑到 publish 了；若它当时没看到 pending，
                # 这里补一个事件也无妨——它不会等，直接兜底推送（幂等覆盖）。
                _direct_done.setdefault(rel_url, threading.Event())
            return str(url)
    return ""


def mark_direct_done(rel_url: str) -> bool:
    """标记浏览器已直传成功；返回 False 表示这个 URL 未在等待列表中。

    只有刚刚通过 presign_put_url() 生成过 PUT URL 的文件才接受通知，
    防止任意外部请求干扰后台推送。通知后后台线程跳过兜底推送。
    """
    with _publish_guard:
        pending_at = _direct_pending.get(rel_url)
        if pending_at is None or time.time() - pending_at > 1800:
            return False
        event = _direct_done.get(rel_url)
        if event is not None:
            event.set()
        _direct_pending.pop(rel_url, None)
        # 直传成功即视为远端已有对象，不再算失败
        _failed_uploads.discard(rel_url)
    return True


def ensure_remote(local_path, rel_url: str) -> str:
    """确保文件已经在远端（本地已存在但从未上传的历史文件）。

    发布器可以提供 `ensure`：先检查远端是否存在，不存在才上传。
    没有这份能力时退回 `publish`。
    同一文件与后台发布共用一把锁，避免两个线程同时 PUT 同一个 key。
    """
    _ensure_hooks()
    with _lock_for(rel_url):
        for func in list(_remote_publishers):
            ensure = getattr(func, "ensure", None)
            if ensure is None:
                continue
            try:
                url = ensure(local_path, rel_url)
            except Exception:  # noqa: BLE001
                logger.exception("远端补传失败：%s", rel_url)
                continue
            if url:
                return str(url)
        return publish(local_path, rel_url)


_remote_exists_cache: dict[str, tuple[float, bool]] = {}
_REMOTE_EXISTS_TTL = 300.0


def remote_exists(rel_url: str) -> bool:
    """远端是否已有这个对象（插件未提供检查能力时按「有」处理）。

    编辑器预览会把音视频 302 到远端地址。历史文件可能从没迁到对象存储，
    直接跳过去就是一次 404 + 播放器报错 + 再回退本地，
    所以先问一句「远端有没有」，没有就老老实实走本地。

    结果缓存 5 分钟：一次播放会发多次 Range 请求，不该每次都去 HEAD。
    """
    _ensure_hooks()
    now = time.time()
    cached = _remote_exists_cache.get(rel_url)
    if cached and now - cached[0] < _REMOTE_EXISTS_TTL:
        return cached[1]

    result = True  # 乐观：插件没实现存在性检查，就相信上传时的双写
    for func in list(_remote_publishers):
        checker = getattr(func, "exists", None)
        if checker is None:
            continue
        try:
            result = bool(checker(rel_url))
        except Exception:  # noqa: BLE001
            logger.warning("远端存在性检查失败，按不存在处理：%s", rel_url)
            result = False
        break

    if len(_remote_exists_cache) > 500:
        _remote_exists_cache.clear()
    _remote_exists_cache[rel_url] = (now, result)
    return result


def publish_preview(local_path, rel_url: str) -> str:
    """上传后把预览副本交给远端存储；没有可用远端时返回空串。"""
    _ensure_hooks()
    for func in list(_remote_publishers):
        publisher = getattr(func, "publish_preview", None)
        if publisher is None:
            continue
        try:
            result = publisher(local_path, rel_url)
        except Exception:  # noqa: BLE001
            logger.exception("预览副本发布失败：%s", rel_url)
            continue
        if result:
            return str(result)
    return ""


_remote_preview_cache: dict[tuple[str, int], tuple[float, str]] = {}
_REMOTE_PREVIEW_TTL = 300.0


def remote_preview(rel_url: str, expires: int = 3600) -> str:
    """编辑器预览该用的远端地址；没有远端或远端没有对象时返回空串。

    预览地址只在浏览器真正来取时才现算，所以签名永远新鲜，
    DOM 里留的是稳定的中转地址，不会把过期链接写进正文。

    结果缓存 5 分钟：一次预览会连续请求多个资源，
    没必要每次都去 HEAD 一遍对象存储。
    """
    _ensure_hooks()
    cache_key = (rel_url, expires)
    now = time.time()
    cached = _remote_preview_cache.get(cache_key)
    if cached and now - cached[0] < _REMOTE_PREVIEW_TTL:
        return cached[1]

    url = ""
    for func in list(_remote_publishers):
        getter = getattr(func, "preview_url", None)
        if getter is None:
            continue
        try:
            url = str(getter(rel_url, expires) or "")
        except Exception:  # noqa: BLE001
            logger.warning("预览地址生成失败：%s", rel_url)
            url = ""
        break

    if len(_remote_preview_cache) > 500:
        _remote_preview_cache.clear()
    _remote_preview_cache[cache_key] = (now, url)
    return url


def preview_assets(html: str, base: str) -> str:
    """后台预览专用：把 HTML 里的 /uploads/... 换成中转地址。

    只用于编辑器预览弹层这类「看一眼效果」的 HTML，不落库：
    中转地址每次请求都会重新决定从本地还是对象存储取，签名不会过期。
    代码块里的路径是说明文字，保持原样。
    """
    if not html or "/uploads/" not in html or not base:
        return html
    prefix = str(base).rstrip("/")

    def _one(text: str) -> str:
        return re.sub(
            r"(?<![\w:/.])/uploads/[^\s\"'<>()\[\]]+",
            lambda m: prefix + m.group(0)[len("/uploads"):],
            text,
        )

    return rewrite_outside_code(html, _one)


# 代码区域：README / 文章里经常贴 `location ~ ^/uploads/...`、
# `curl https://host/uploads/x` 这类示例。它们必须原样展示，
# 一旦被改写成带签名的真实地址，等于把存储端点、Access Key 与签名全部公开。
_PROTECTED_RE = re.compile(
    r"<(pre|code|script|style|textarea)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)


def rewrite_outside_code(html: str, rewrite) -> str:
    """只对代码区域（pre / code / script / style / textarea）之外的 HTML 执行改写。

    代码块里的路径是「给人看的文本」，不是要加载的资源，
    改写它既破坏示例、又会泄露真实地址。
    """
    if not html:
        return html
    parts: list[str] = []
    pos = 0
    for match in _PROTECTED_RE.finditer(html):
        parts.append(rewrite(html[pos:match.start()]))
        parts.append(match.group(0))
        pos = match.end()
    parts.append(rewrite(html[pos:]))
    return "".join(parts)


def rewrite_html(html: str) -> str:
    """把 HTML 里的规范上传路径按当前存储策略改写成最终地址。

    由 app.after_request 在页面缓存写入之后调用：
    - 页面缓存里存的是 /uploads/...，切换策略后旧缓存依然正确；
    - 停用插件后没有改写器，输出自然回到 /uploads/...。
    """
    if not html:
        return html
    for func in list(_remote_publishers):
        rewriter = getattr(func, "rewrite_html", None)
        if rewriter is None:
            continue
        try:
            html = rewriter(html)
        except Exception:  # noqa: BLE001
            logger.exception("远端地址改写失败")
    return html


def normalize_html(html: str) -> str:
    """把 HTML 里各种远端地址剥回 /uploads/...，代码块保持原样。

    预签名地址只有十几分钟寿命，而页面缓存与 README 缓存是按天活着
    的——地址一旦进了缓存，缓存越新、图越旧，到期后整页图片 403。
    输出前统一归一化，展示时再按当前策略现场签名；
    这里只处理代码块之外的文本，README 里的 `curl .../uploads/x`
    这类示例保持原样。
    """
    if not html:
        return html
    return rewrite_outside_code(html, normalize_text)


def normalize_text(text: str) -> str:
    """把各种远端地址归一化回 /uploads/...，用于保存前清洗。

    编辑器和剪贴板里可能带进 OSS 直链、预签名 URL 或代理路径；
    这些都带有效期或与当前策略绑定，落库后会过期。
    保存前统一剥回规范路径，展示时再按当前策略重新生成。
    """
    if not text:
        return text
    # 通用兜底：预签名地址带 X-Amz-Signature，十几分钟就过期，
    # 无论插件当前是否启用（停用后也拿不到它的 normalize），
    # 都不能让它留在正文或缓存里。路径里的 /uploads/ 是本站规范前缀。
    text = re.sub(
        r"https?://[^\s\"'<>()\[\]]*?/uploads/([^\s\"'<>()\[\]?]+)"
        r"\?[^\s\"'<>()\[\]]*X-Amz-Signature=[^\s\"'<>()\[\]]*",
        lambda m: "/uploads/" + m.group(1),
        text,
    )
    # 原图路径只用于显示，不该进正文/封面：万一被保存进来，统一剥回展示图路径
    text = re.sub(r"/uploads/originals/", "/uploads/", text)
    # 编辑器预览中转地址是后台路由，前台访客打不开，落库前必须剥掉。
    # 形如 /manage/preview/asset/uploads/2026/11/a.png → /uploads/2026/11/a.png
    text = re.sub(r"/[^/\s\"'<>()\[\]]*/preview/asset/uploads/", "/uploads/", text)
    for func in list(_remote_publishers):
        normalizer = getattr(func, "normalize", None)
        if normalizer is None:
            continue
        try:
            text = normalizer(text)
        except Exception:  # noqa: BLE001
            logger.exception("远端地址归一化失败")
    return text

# HEIC/HEIF 浏览器支持面窄，上传后统一转成 WebP 再落盘
HEIC_EXTS = {".heic", ".heif"}

_heif_ready = False
_heif_warned = False


def _ensure_heif() -> bool:
    """按需注册 pillow-heif 解码器；未安装时降级为不支持 HEIC。"""
    global _heif_ready, _heif_warned
    if _heif_ready:
        return True
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        _heif_ready = True
    except Exception as exc:  # noqa: BLE001
        if not _heif_warned:
            _heif_warned = True
            logger.warning("pillow-heif 不可用，HEIC/HEIF 将无法转码: %s", exc)
    return _heif_ready


def normalize_ext_input(raw: str, fallback: set[str]) -> set[str]:
    result: set[str] = set()
    for item in re.split(r"[\s,;，；、]+", raw or ""):
        ext = item.strip().lower().lstrip(".")
        if not ext or not re.fullmatch(r"[a-z0-9]{1,10}", ext) or ext in BLOCKED_EXTS:
            continue
        result.add("." + ext)
        if len(result) >= 60:
            break
    return result or set(fallback)


def image_exts() -> set[str]:
    raw = settings.get_str("upload_image_ext", "")
    return normalize_ext_input(raw, IMAGE_EXTS) if raw else set(IMAGE_EXTS)


def media_exts() -> set[str]:
    raw = settings.get_str("upload_media_ext", "")
    return normalize_ext_input(raw, MEDIA_EXTS) if raw else set(MEDIA_EXTS)


def file_exts() -> set[str]:
    raw = settings.get_str("upload_file_ext", "")
    return normalize_ext_input(raw, FILE_EXTS) if raw else set(FILE_EXTS)


def max_size() -> int:
    mb = settings.get_int("upload_max_size", 0)
    return mb * 1024 * 1024 if mb > 0 else 20 * 1024 * 1024


def root() -> Path:
    return Path(UPLOADS_DIR)


def fmt_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def safe_stem(filename: str) -> str:
    """把原始文件名清洗成可用的文件名主干，**保留中文**。

    这里以前还会再走一遍 secure_filename()，它会把非 ASCII 字符全部删掉：
    「水果店花生.png」最终落成 file.png，图注、下载名全变成无意义的 file。
    现在只在本地清洗，替换掉路径分隔符、Windows 保留字符、URL 里有特殊含义的字符，
    中文、日文、韩文等直接保留。
    """
    stem = Path(filename).stem
    # 路径分隔符（防目录穿越）、Windows 保留字符、URL 里会截断或改变含义的字符
    stem = re.sub(r'[\\/:*?"<>|#%&]', "-", stem)
    stem = re.sub(r"[\x00-\x1f\x7f]", "", stem)   # 控制字符
    stem = re.sub(r"\s+", "-", stem)              # 空白换成连字符，避免 URL 里出现空格
    stem = re.sub(r"\.{2,}", ".", stem)           # 连续的 . 收成一个，避免出现 .. 片段
    stem = re.sub(r"-{2,}", "-", stem)
    stem = stem.strip("-. ")
    return stem[:80] or "file"


def random_stem() -> str:
    return secrets.token_hex(8)


def _watermark_text() -> str:
    """后台自定义文本优先；留空回退「站点名 · 域名」，与 PHP 版一致。"""
    text = settings.get_str("watermark_text", "").strip()
    if text:
        return text
    name = settings.get_str("blog_name", "").strip()
    host = ""
    try:
        from services import site_url

        host = urlparse(site_url.base()).hostname or ""
    except Exception:
        host = ""
    if host in {"127.0.0.1", "localhost", "::1"}:
        host = ""
    return " · ".join(part for part in (name, host) if part)


def _apply_watermark(path: Path) -> None:
    if not settings.bool_of("watermark_enabled", True):
        return
    text = _watermark_text()
    if not text or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return
    from PIL import Image, ImageDraw, ImageFont

    try:
        with Image.open(path) as img:
            img = img.convert("RGBA")
            width, height = img.size
            size_key = settings.get_str("watermark_size", "m").strip().lower()
            # 与表单「图宽 2% / 3% / 4%」和 PHP 版一致，并限制最小/最大字号
            ratio, min_px, max_px = {
                "s": (0.02, 14, 28),
                "m": (0.03, 18, 52),
                "l": (0.04, 24, 76),
            }.get(size_key, (0.03, 18, 52))
            font_size = max(min_px, min(max_px, int(round(width * ratio))))
            font = None
            font_path = FONTS_DIR / "wqy-microhei.ttc"
            if font_path.is_file():
                font = ImageFont.truetype(str(font_path), font_size)
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pad = max(10, int(round(font_size * 0.45)))
            pos = settings.get_str("watermark_position", "br").strip().lower()
            if pos not in {"br", "bl", "tr", "tl", "bc"}:
                pos = "br"
            if pos == "bc":
                x = max(pad, (width - tw) // 2)
            elif "r" in pos:
                x = max(pad, width - tw - pad)
            else:
                x = pad
            y = height - th - pad if "b" in pos else pad
            draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 110))
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 170))
            out = Image.alpha_composite(img, overlay)
            if path.suffix.lower() in {".jpg", ".jpeg"}:
                out.convert("RGB").save(path, quality=90, optimize=True)
            else:
                out.save(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("watermark failed for %s: %s", path, exc)
        return


def _convert_heic(src: Path, quality: int = 92) -> Path | None:
    """把 HEIC/HEIF（以及改名成其它扩展的 AVIF）解码并转存为 WebP，返回新路径；失败返回 None。"""
    _ensure_heif()  # 装不上也让 Pillow 原生解码试一次
    out = src.with_suffix(".webp")
    try:
        from PIL import Image, ImageOps

        index = 1
        while out.exists():
            out = src.with_name(f"{src.stem}_{index}.webp")
            index += 1
        with Image.open(src) as img:
            # 手机竖拍依赖 EXIF Orientation，先摆正再转码
            img = ImageOps.exif_transpose(img)
            if img.mode not in {"RGB", "RGBA"}:
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            img.save(out, "WEBP", quality=quality, method=4)
    except Exception as exc:  # noqa: BLE001
        logger.warning("heic convert failed for %s: %s", src, exc)
        out.unlink(missing_ok=True)
        return None
    src.unlink(missing_ok=True)
    return out


def _square_crop(path: Path, size: int) -> Path | None:
    """居中裁成正方形并转 WebP（头像用）。失败返回 None，调用方保留原图。"""
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in {"RGB", "RGBA"}:
                img = img.convert("RGB")
            img = ImageOps.fit(img, (size, size), Image.LANCZOS, centering=(0.5, 0.5))
            out = path.with_suffix(".webp")
            img.save(out, "WEBP", quality=90, method=4)
        if out != path:
            path.unlink(missing_ok=True)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("头像裁切失败 %s: %s", path, exc)
        return None


def save(
    file: FileStorage | None,
    allowed_ext: set[str],
    max_bytes: int | None = None,
    sub_dir: str | None = None,
    randomize: bool = False,
    square: int = 0,
    watermark: bool = True,
) -> tuple[str, str]:
    """返回 (相对 URL, 错误信息)。

    square > 0 时居中裁成正方形并转 WebP（头像）；watermark=False 时不叠水印。
    """
    if file is None or not file.filename:
        return "", "未选择文件或上传失败"
    limit = max_bytes or max_size()
    # 最多读 limit+1 字节，避免超大盘直接整块读进内存
    data = file.read(limit + 1)
    if not data:
        return "", "文件为空"
    if len(data) > limit:
        return "", f"文件大小不能超过 {fmt_size(limit)}"

    original = file.filename
    ext = Path(original).suffix.lower()
    if ext not in allowed_ext:
        return "", f"不支持的文件类型：{ext or '(无扩展名)'}"

    sub = (sub_dir or datetime.now().strftime("%Y/%m")).strip("/")
    folder = root() / sub
    folder.mkdir(parents=True, exist_ok=True)

    stem = random_stem() if randomize else safe_stem(original)
    filename = f"{stem}{ext}"
    i = 1
    while (folder / filename).exists():
        filename = f"{stem}_{i}{ext}"
        i += 1
    dest = folder / filename
    dest.write_bytes(data)

    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"} | HEIC_EXTS:
        _ensure_heif()
        try:
            from PIL import Image
            with Image.open(dest) as img:
                real_fmt = (img.format or "").upper()
                img.verify()
        except Exception as exc:  # noqa: BLE001
            logger.warning("图片校验失败 %s: %s", dest, exc)
            dest.unlink(missing_ok=True)
            return "", "图片文件损坏或格式不受支持"
        # .jpg 里装 HEIC/AVIF 的情况（iPhone 改扩展名）：按真实格式转成 WebP
        if ext in HEIC_EXTS or real_fmt in {"HEIF", "HEIC", "AVIF"}:
            converted = _convert_heic(dest)
            if converted is None:
                dest.unlink(missing_ok=True)
                return "", "图片解析失败（HEIC/AVIF），请先转换为 JPG/WebP 后重试"
            dest = converted
            filename = dest.name
        # 水印只在上传这一刻决定：开着就叠上去，关着就存原样。
        # 不另存副本，同一张图在磁盘上只有一份；切换开关只影响之后的新图。
        if watermark:
            _apply_watermark(dest)
    if square:
        cropped = _square_crop(dest, int(square))
        if cropped is not None:
            dest = cropped
            filename = dest.name
    rel_url = f"/uploads/{sub}/{filename}"
    # 远端存储（如对象存储插件）只负责「额外上传一份」，
    # 返回给调用方的永远是规范路径 /uploads/...。
    # 数据库里只存这一种形式，页面输出时再按当前策略换成直链或代理地址，
    # 这样切换策略不需要回写内容。
    # 本地落盘完成就返回；远端上传与预览副本放后台，
    # 保存文章/评论时由 sync_remote_urls() 等它结束并兜底补传。
    defer_publish(dest, rel_url)
    return rel_url, ""


PHOTO_THUMB_WIDTHS = (320, 560, 960)


def drop_thumbs(rel_url: str) -> None:
    """删掉某张照片各宽度的缩略图缓存。"""
    rel = unquote(str(rel_url or "")).replace("\\", "/")
    if "/uploads/" in rel:
        rel = rel.split("/uploads/", 1)[1]
    rel = rel.lstrip("/")
    if not rel:
        return
    cache_dir = Path(CACHE_DIR) / "photos"
    for width in PHOTO_THUMB_WIDTHS:
        key = hashlib.sha1(f"{rel}|{width}".encode()).hexdigest()
        (cache_dir / f"{key}-{width}.webp").unlink(missing_ok=True)



def photo_thumb(filename: str, width: int = 560) -> Path | None:
    """照片墙缩略图：固定宽度 WebP，缓存到 var/cache/photos。

    网格一屏可能几十张图，直接加载原图会把带宽打满；这里统一缩到 560 宽，
    与正文预览用的 preview_thumb 分开目录，互不干扰。
    源图不存在、动图或非位图时返回 None，由调用方回退原图。
    """
    if width not in PHOTO_THUMB_WIDTHS:
        width = 560
    src = resolve(filename)
    if src is None or not src.is_file():
        return None
    if src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return None

    from services import cachefs

    cache_dir = Path(CACHE_DIR) / "photos"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{unquote(filename)}|{width}".encode()).hexdigest()
    out = cache_dir / f"{key}-{width}.webp"
    try:
        if out.is_file() and out.stat().st_mtime >= src.stat().st_mtime:
            return out
    except OSError:
        return None

    tmp = cache_dir / f"{key}-{width}-{secrets.token_hex(4)}.tmp"
    try:
        from PIL import Image, ImageOps

        with Image.open(src) as img:
            if getattr(img, "n_frames", 1) > 1:
                return None
            if img.format in {"JPEG", "MPO"}:
                img.draft("RGB", (width * 2, width * 2))
            img = ImageOps.exif_transpose(img)
            img.thumbnail((width, width * 8), Image.LANCZOS)
            if img.mode not in {"RGB", "RGBA"}:
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            img.save(tmp, "WEBP", quality=82, method=4)
        tmp.replace(out)
    except Exception as exc:  # noqa: BLE001
        logger.warning("photo thumb failed for %s: %s", src, exc)
        return None
    finally:
        tmp.unlink(missing_ok=True)

    cachefs.cap(cache_dir, 2000)
    return out


def resolve(filename: str) -> Path | None:
    """安全拼接 uploads 下路径，防目录穿越；隐藏目录（.originals 等）不可访问。"""
    rel = unquote(str(filename or "")).replace("\\", "/").lstrip("/")
    parts = rel.split("/")
    if not rel or ".." in parts or any(part.startswith(".") for part in parts):
        return None
    path = (root() / rel).resolve()
    try:
        path.relative_to(root().resolve())
    except ValueError:
        return None
    return path


# 后台编辑器预览允许的宽度档位：固定几档，避免 ?w=1..9999 把缓存刷爆
PREVIEW_WIDTHS = (480, 960, 1440)


def preview_thumb(filename: str, width: int = 960) -> Path | None:
    """后台编辑器预览用的缩略图，返回缓存文件路径；不能缩小时返回 None。

    预览区只用来判断版式，用不到原图分辨率：手机原图动辄 4000px、几 MB，
    一次插入十几张会让后台卡顿，也把出站带宽全吃在本地副本上。
    这里按固定宽度缩放成 WebP 并缓存，源文件更新后自动失效。

    GIF 动图、SVG、视频不处理，由调用方回退原图。
    """
    if width not in PREVIEW_WIDTHS:
        width = 960
    src = resolve(filename)
    if src is None or not src.is_file():
        return None
    if src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return None

    from services import cachefs

    cache_dir = Path(CACHE_DIR) / "previews"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{unquote(filename)}|{width}".encode()).hexdigest()
    out = cache_dir / f"{key}-{width}.webp"
    try:
        if out.is_file() and out.stat().st_mtime >= src.stat().st_mtime:
            return out
    except OSError:
        return None

    tmp = cache_dir / f"{key}-{width}-{secrets.token_hex(4)}.tmp"
    try:
        from PIL import Image, ImageOps

        with Image.open(src) as img:
            if getattr(img, "n_frames", 1) > 1:
                return None  # 动图缩放会丢帧，直接回退原图
            if img.format in {"JPEG", "MPO"}:
                # 让解码器直接按 2 倍目标宽度出图，省内存也更快
                img.draft("RGB", (width * 2, width * 2))
            img = ImageOps.exif_transpose(img)
            img.thumbnail((width, width * 8), Image.LANCZOS)
            if img.mode not in {"RGB", "RGBA"}:
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            img.save(tmp, "WEBP", quality=82, method=4)
        tmp.replace(out)
    except Exception as exc:  # noqa: BLE001
        logger.warning("preview thumb failed for %s: %s", src, exc)
        return None
    finally:
        tmp.unlink(missing_ok=True)

    cachefs.cap(cache_dir, 1200)
    return out


_PREVIEW_WIDTH = 960
_PREVIEW_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _store_preview(path: Path, rel_url: str) -> None:
    """给远端存储准备一份 960 宽预览副本，失败不影响上传结果。

    预览副本让「编辑器里走对象存储」和「预览要快」不再二选一：
    原图 500KB 的截图，副本只有 30KB 左右。
    .webp 源本身就是压缩格式，再生成副本会得到 xxx.webp.webp 这种怪名字，直接跳过。
    """
    if not remote_active() or not rel_url.startswith("/uploads/"):
        return
    if path.suffix.lower() not in _PREVIEW_EXTS or path.suffix.lower() == ".webp":
        return
    rel = rel_url[len("/uploads/"):]
    try:
        thumb = preview_thumb(rel, _PREVIEW_WIDTH)
    except Exception:  # noqa: BLE001
        logger.warning("预览副本生成失败：%s", rel_url)
        return
    if thumb is None:
        return
    publish_preview(thumb, rel_url)


def image_dims(rel_url: str) -> tuple[int, int] | None:
    rel = rel_url
    if "/uploads/" in rel:
        rel = rel.split("/uploads/", 1)[1]
    path = resolve(rel)
    if path is None or not path.is_file():
        return None
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def share_thumb(filename: str) -> Path | None:
    src = resolve(filename)
    if src is None or not src.is_file():
        return None
    cache_dir = Path(CACHE_DIR) / "share_thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / (hashlib.sha1(unquote(filename).encode()).hexdigest() + ".jpg")
    if out.is_file() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    try:
        from PIL import Image
        with Image.open(src) as img:
            img = img.convert("RGB")
            width, height = img.size
            tw, th = 800, 600
            target = tw / th
            src_ratio = width / max(1, height)
            if src_ratio > target:
                sh = height
                sw = round(height * target)
                sx, sy = round((width - sw) / 2), 0
            else:
                sw = width
                sh = round(width / target)
                sx, sy = 0, round((height - sh) / 2)
            dst = img.crop((sx, sy, sx + sw, sy + sh)).resize((tw, th), Image.LANCZOS)
            dst.save(out, "JPEG", quality=82, optimize=True)
        return out
    except Exception:
        # 非位图（SVG 等）不生成分享图，避免以图片 MIME 返回可执行内容
        return None


def _normalize_upload_path(url: str) -> str:
    """私有桶的代理路径 /oss-media/uploads/... 与站内 /uploads/... 等价。"""
    if url.startswith("/oss-media/"):
        return "/" + url[len("/oss-media/"):]
    return url


def extract_urls(*texts: str) -> set[str]:
    urls: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in re.finditer(r"/(?:uploads|oss-media)/[/\w%.\-]+", str(text), re.U):
            urls.add(unquote(_normalize_upload_path(match.group(0))))
    return urls


def first_url(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        match = re.search(r"/(?:uploads|oss-media)/[/\w%.\-]+", str(text), re.U)
        if match:
            return unquote(_normalize_upload_path(match.group(0)))
    return ""


def referenced_urls() -> set[str]:
    """收集仍被视为「有效引用」的上传文件 URL。

    判断口径是「这条内容是否仍可能展示、或仍能在后台恢复编辑」：

    - **文章**：回收站里的软删除文章仍可恢复，且彻底删除时由
      `Post._purge_rows` 负责清图，所以这里全部统计。
      字段必须覆盖 `cover`——只在封面用到的图若漏扫，会被孤儿清理误删。
    - **评论**：正文里的图片一律保护（含软删除、待审、已拒绝）。
      「留存记录 → 评论留存」会永久展示正文，图片被清理后回溯就会缺图；
      未提交就放弃的图片不在这类引用里，仍会正常出现在孤儿列表。
    - **友链**：`rejected` 仍可在后台恢复通过，按「可恢复」处理，全部统计。
    - **记忆 / 项目 / 时间线**：没有删除或审核标记，全部统计。
    - **设置项**：头像、自定义 logo 等图片一并保护，避免被当成孤儿。
    - 不扫描 `ai_messages` / `op_logs`：那是操作历史快照（例如 AI 调用参数
      里带过的旧正文），不代表当前引用，否则清理过的图会被永久钉住。
    """
    import db

    referenced: set[str] = set()
    sources = [
        "SELECT title, content, excerpt, tags, cover FROM posts",
        "SELECT author, website, content FROM comments",
        "SELECT name, url, description, avatar FROM links",
        "SELECT title, text, image FROM memories",
        "SELECT name, description, url FROM projects",
        "SELECT content FROM timeline",
        "SELECT key, value FROM settings",
        # 读者上传的头像：路径是 /uploads/reader/avatar/...，不在 avatar/ 目录下，
        # 必须显式扫描，否则会被当成孤儿清理
        "SELECT avatar_url FROM reader_users",
    ]
    for sql in sources:
        for row in db.query(sql):
            referenced |= extract_urls(*[str(v) for v in tuple(row)])
    return referenced


def orphans(protect_hours: int = 24) -> list[dict]:
    """列出本地孤儿文件。

    protect_hours：最近 N 小时内新上传的文件先保护起来——评论区编辑器里
    可能刚上传、还没提交，这时数据库里还没有引用，直接清理会把图删掉。
    """
    # 远端存储可用时，本地文件是「停用后的回退副本」，不能当孤儿清理：
    # 一旦删掉，停用插件把地址改回本地就会全部裂图。
    # 对象存储启用时，本地文件是「停用后的回退副本」，但孤儿本身已经没有任何内容引用，
    # 删掉不会影响回退；因此照常列出，便于本地与远端一起清理。
    referenced = referenced_urls()
    base = root()
    result: list[dict] = []
    if not base.is_dir():
        return result
    cutoff = time.time() - max(0, int(protect_hours)) * 3600
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        parts = rel.split("/")
        if not parts or parts[0].startswith("."):
            continue
        # 跳过保留目录（头像 / AI 头像 / 用户头像 / 项目文件 / 派生预览）与隐藏目录。
        # 不再要求至少两级路径：uploads 根下直接放置的文件同样可能是孤儿，
        # 之前 len(parts) < 2 的过滤会让它们永远不显示、也永远清理不到。
        if parts[0] in {"avatar", "ai-avatar", "projects", "reader", "previews"}:
            continue
        url = "/uploads/" + rel
        if url in referenced:
            continue
        stat = path.stat()
        if stat.st_mtime >= cutoff:
            # 刚上传的文件可能是「编辑器里还没提交」的评论图片，本轮先跳过
            continue
        result.append(
            {
                "rel": rel,
                "url": url,
                "size": fmt_size(stat.st_size),
                "size_bytes": stat.st_size,
                "ext": path.suffix.lower().lstrip("."),
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "kind": "file",
            }
        )
    result.sort(key=lambda item: item["mtime"], reverse=True)
    return result


def delete_rel(rel: str) -> str:
    rel = unquote(str(rel or "")).replace("\\", "/").lstrip("/")
    parts = rel.split("/")
    if not rel or ".." in parts or parts[0].startswith(".") or parts[0] in {"avatar", "ai-avatar", "projects", "reader", "previews"}:
        return "非法路径"
    path = root() / rel
    existed = path.is_file()
    if existed:
        try:
            path.unlink()
        except OSError:
            return "删除失败"
        drop_thumbs("/uploads/" + rel)
    # 不管本地有没有都尝试删远端：这个文件可能只存在于对象存储。
    # 未启用 OSS 时 delete_remote 自己会直接返回。
    delete_remote("/uploads/" + rel)
    if existed or remote_active():
        return ""
    return "文件不存在"


def auto_clean_orphans(retention_days: int = 7) -> dict:
    """定期清理：删除超过保留天数且无引用的本地孤儿（连同 OSS 副本），删前备份本地。

    只处理本地扫描得到的孤儿；仅存于 OSS、本地已没有的对象留给后台人工清理，
    避免自动任务对不可逆的远端删除做太多主张。保留天数下限 1 天，比 24h 显示
    保护期更保守，给「刚上传还没提交」留足缓冲。
    """
    import shutil

    days = max(1, int(retention_days))
    items = orphans(protect_hours=days * 24)
    referenced = referenced_urls()
    deleted = failed = freed = 0
    trash = Path(BACKUPS_DIR) / "orphans" / datetime.now().strftime("%Y%m%d_%H%M%S")
    for item in items:
        rel = item["rel"]
        # 扫描到执行之间内容可能刚被引用，删前再校验一次
        if unquote("/uploads/" + rel) in referenced:
            failed += 1
            continue
        src = root() / rel
        if src.is_file():
            dest = trash / rel
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            except OSError:
                pass
        if delete_rel(rel):
            failed += 1
        else:
            deleted += 1
            freed += int(item.get("size_bytes") or 0)
    return {
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "deleted": deleted,
        "failed": failed,
        "freed_bytes": freed,
        "freed": fmt_size(freed),
        "retention_days": days,
    }


def merge_orphan_sources(local: list[dict], remote: list[dict]) -> list[dict]:
    """把本地孤儿与对象存储孤儿合并成一份清单。

    同一路径两边都有时只保留一条，标 sources 为 ["local", "remote"]，
    后台据此提示「删一条 = 两边一起删」。
    """
    merged: dict[str, dict] = {}
    for item in local:
        entry = dict(item)
        entry["sources"] = ["local"]
        merged[entry["rel"]] = entry

    for item in remote:
        rel = item.get("rel") or ""
        if not rel:
            continue
        if rel in merged:
            entry = merged[rel]
            if "remote" not in entry["sources"]:
                entry["sources"].append("remote")
            if int(item.get("size") or 0) > int(entry.get("size_bytes") or 0):
                entry["size_bytes"] = int(item["size"])
                entry["size"] = item.get("size_text") or fmt_size(entry["size_bytes"])
            entry["remote_url"] = item.get("url", "")
        else:
            size = int(item.get("size") or 0)
            merged[rel] = {
                "rel": rel,
                "url": "/uploads/" + rel,
                "size": item.get("size_text") or fmt_size(size),
                "size_bytes": size,
                "ext": item.get("ext") or "",
                "mtime": str(item.get("uploaded_at") or "")[:19].replace("T", " "),
                "kind": "file",
                "sources": ["remote"],
                "remote_url": item.get("url", ""),
            }

    return sorted(merged.values(), key=lambda x: x.get("size_bytes") or 0, reverse=True)


def delete_by_url(url: str) -> bool:
    if "/uploads/" not in url:
        return False
    rel = unquote(url.split("/uploads/", 1)[1])
    parts = rel.split("/")
    if not rel or ".." in parts or parts[0].startswith(".") or parts[0] in {"avatar", "ai-avatar", "projects"}:
        return False
    path = root() / rel
    if not path.is_file():
        return False
    try:
        path.unlink()
        drop_thumbs("/uploads/" + rel)
        # 文章删除时的清理同样同步远端，避免本地没了、OSS 上还挂着
        delete_remote("/uploads/" + rel)
        return True
    except OSError:
        return False


# 启动时注册一次，让 image_dims / share_thumb / 头像裁剪等 PIL 调用也能识别 HEIC
_ensure_heif()


