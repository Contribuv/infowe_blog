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

    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        try:
            from PIL import Image
            with Image.open(dest) as img:
                img.verify()
        except Exception:
            dest.unlink(missing_ok=True)
            return "", "图片文件损坏或格式不受支持"
        # 先备份无痕原图（公网不可达），再叠水印；关闭水印时原图和展示图一致
        try:
            origin = root() / ".originals" / sub / filename
            origin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, origin)
        except OSError:
            pass
        _apply_watermark(dest)
    return f"/uploads/{sub}/{filename}", ""


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


def extract_urls(*texts: str) -> set[str]:
    urls: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in re.finditer(r"/uploads/[/\w%.\-]+", str(text), re.U):
            urls.add(unquote(match.group(0)))
    return urls


def first_url(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        match = re.search(r"/uploads/[/\w%.\-]+", str(text), re.U)
        if match:
            return unquote(match.group(0))
    return ""


def referenced_urls() -> set[str]:
    import db

    referenced: set[str] = set()
    sources = [
        "SELECT title, content, excerpt, tags FROM posts",
        "SELECT author, website, content FROM comments",
        "SELECT name, url, description, avatar FROM links",
        "SELECT title, text, image FROM memories",
        "SELECT name, description, url FROM projects",
        "SELECT content FROM timeline",
    ]
    for sql in sources:
        for row in db.query(sql):
            referenced |= extract_urls(*[str(v) for v in tuple(row)])
    return referenced


def orphans() -> list[dict]:
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
        if len(parts) < 2:
            continue
        if parts[0].startswith(".") or parts[0] in {"avatar", "ai-avatar", "projects"}:
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
