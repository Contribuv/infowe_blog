"""上传文件服务：校验、保存、水印、缩略图、孤儿扫描。"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from werkzeug.datastructures import FileStorage

from config import (
    CACHE_DIR, COMMENT_IMAGE_MAX_SIZE, FILE_EXTS, FONTS_DIR, IMAGE_EXTS,
    MEDIA_EXTS, UPLOADS_DIR,
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


def remote_active() -> bool:
    """当前是否有「真正可用」的远端存储接管上传。

    发布函数可以挂 ``is_active`` 属性做二次判断（例如插件已启用但配置不完整）。
    没有任何远端时返回 False，孤儿清理等逻辑保持原样。
    """
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
    """上传原图 + 预览副本，返回远端是否拿到原图。

    原图一传完就 set(done)，让正在保存文章的那个请求先走；
    副本（PIL 缩放 + 小文件 PUT）继续在后台跑，不必拖住保存。
    """
    with _lock_for(rel_url):
        url = publish(local_path, rel_url)
    if done is not None:
        done.set()
    if url:
        _store_preview(Path(local_path), rel_url)
    return bool(url)


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


def remote_url(rel_url: str) -> str:
    """只取远端地址、不上传；用于「文件已经存在」的场景。

    例如项目 README 图片缓存：文件可能早就在本地了，
    但页面仍然应该展示远端地址，没必要每次渲染都重传一遍。
    """
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


def ensure_remote(local_path, rel_url: str) -> str:
    """确保文件已经在远端（本地已存在但从未上传的历史文件）。

    发布器可以提供 `ensure`：先检查远端是否存在，不存在才上传。
    没有这份能力时退回 `publish`。
    同一文件与后台发布共用一把锁，避免两个线程同时 PUT 同一个 key。
    """
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


def normalize_text(text: str) -> str:
    """把各种远端地址归一化回 /uploads/...，用于保存前清洗。

    编辑器和剪贴板里可能带进 OSS 直链、预签名 URL 或代理路径；
    这些都带有效期或与当前策略绑定，落库后会过期。
    保存前统一剥回规范路径，展示时再按当前策略重新生成。
    """
    if not text:
        return text
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


def save(
    file: FileStorage | None,
    allowed_ext: set[str],
    max_bytes: int | None = None,
    sub_dir: str | None = None,
    randomize: bool = False,
) -> tuple[str, str]:
    """返回 (相对 URL, 错误信息)。"""
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
        # 先备份无痕原图（公网不可达），再叠水印；关闭水印时原图和展示图一致
        try:
            origin = root() / ".originals" / sub / filename
            origin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, origin)
        except OSError:
            pass
        _apply_watermark(dest)
    rel_url = f"/uploads/{sub}/{filename}"
    # 远端存储（如对象存储插件）只负责「额外上传一份」，
    # 返回给调用方的永远是规范路径 /uploads/...。
    # 数据库里只存这一种形式，页面输出时再按当前策略换成直链或代理地址，
    # 这样切换策略不需要回写内容。
    # 本地落盘完成就返回；远端上传与预览副本放后台，
    # 保存文章/评论时由 sync_remote_urls() 等它结束并兜底补传。
    defer_publish(dest, rel_url)
    return rel_url, ""


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
    """
    if not remote_active() or not rel_url.startswith("/uploads/"):
        return
    if path.suffix.lower() not in _PREVIEW_EXTS:
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
    - **评论**：只有已软删除（`deleted_at`）的评论才算孤儿——后台没有恢复
      入口，图片交给孤儿清理。**已拒绝（`rejected`）的评论图片保留**：
      拒绝态随时可能在后台恢复通过，若提前清理，恢复后就会缺图。
      `pending` 同理保留（作者本人可见、管理员随时可通过）。
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
        "SELECT author, website, content FROM comments WHERE deleted_at IS NULL",
        "SELECT name, url, description, avatar FROM links",
        "SELECT title, text, image FROM memories",
        "SELECT name, description, url FROM projects",
        "SELECT content FROM timeline",
        "SELECT key, value FROM settings",
    ]
    for sql in sources:
        for row in db.query(sql):
            referenced |= extract_urls(*[str(v) for v in tuple(row)])
    return referenced


def orphans() -> list[dict]:
    # 远端存储可用时，本地文件是「停用后的回退副本」，不能当孤儿清理：
    # 一旦删掉，停用插件把地址改回本地就会全部裂图。
    if remote_active():
        return []
    referenced = referenced_urls()
    base = root()
    result: list[dict] = []
    if not base.is_dir():
        return result
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        parts = rel.split("/")
        # 跳过保留目录（头像 / AI 头像 / 项目文件）与隐藏目录（.originals 等）。
        # 不再要求至少两级路径：uploads 根下直接放置的文件同样可能是孤儿，
        # 之前 len(parts) < 2 的过滤会让它们永远不显示、也永远清理不到。
        if not parts or parts[0].startswith(".") or parts[0] in {"avatar", "ai-avatar", "projects"}:
            continue
        url = "/uploads/" + rel
        if url in referenced:
            continue
        stat = path.stat()
        result.append(
            {
                "rel": rel,
                "url": url,
                "size": fmt_size(stat.st_size),
                "size_bytes": stat.st_size,
                "ext": path.suffix.lower().lstrip("."),
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "has_origin": (base / ".originals" / rel).is_file(),
            }
        )
    result.sort(key=lambda item: item["mtime"], reverse=True)
    return result


def delete_rel(rel: str) -> str:
    rel = unquote(str(rel or "")).replace("\\", "/").lstrip("/")
    parts = rel.split("/")
    if not rel or ".." in parts or parts[0].startswith(".") or parts[0] in {"avatar", "ai-avatar", "projects"}:
        return "非法路径"
    path = root() / rel
    if not path.is_file():
        return "文件不存在"
    try:
        path.unlink()
    except OSError:
        return "删除失败"
    (root() / ".originals" / rel).unlink(missing_ok=True)
    return ""


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
        (root() / ".originals" / rel).unlink(missing_ok=True)
        return True
    except OSError:
        return False


# 启动时注册一次，让 image_dims / share_thumb / 头像裁剪等 PIL 调用也能识别 HEIC
_ensure_heif()
