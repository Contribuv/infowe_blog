"""上传文件服务：校验、保存、水印、缩略图、孤儿扫描。"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

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
    """
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
    stem = Path(filename).stem
    stem = re.sub(r'[\\/:*?"<>|]', "-", stem).strip()
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

    stem = random_stem() if randomize else secure_filename(safe_stem(original)) or "file"
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
    publish(dest, rel_url)
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
