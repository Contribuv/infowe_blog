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
)

# 站内上传路径：排除引号、括号、尖括号与空白，避免把 Markdown 语法吃进去
_REL_RE = re.compile(r"/uploads/[^\s\"'<>()\[\]]+")
_URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]]+")
# 迁移时跳过的目录：原图备份不对外，隐藏目录一律不传
_SKIP_DIRS = {".originals", ".trash", ".tmp"}


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
    return cfg.url_of(rel_url)


def delete_remote(rel_url: str) -> None:
    """删除 OSS 上的同名对象（本地删除时同步，失败只记日志）。"""
    if not is_enabled():
        return
    cfg = get_cfg()
    if cfg is None:
        return
    try:
        s3.delete(cfg, rel_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OSS 删除失败 %s：%s", rel_url, exc)


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


def to_remote_text(text: str) -> tuple[str, int]:
    """把文本里的站内上传路径换成 OSS 公网地址。"""
    cfg = get_cfg()
    if cfg is None or not text or "/uploads/" not in text:
        return text, 0
    replaced = 0

    def _sub(match: re.Match) -> str:
        nonlocal replaced
        raw = match.group(0)
        rel_path, sep, query = raw.partition("?")
        rel = unquote(rel_path)
        if not _local_exists(rel):
            return raw
        replaced += 1
        url = cfg.url_of(rel)
        return url + (sep + query if sep else "")

    return _REL_RE.sub(_sub, text), replaced


def to_local_text(text: str) -> tuple[str, int]:
    """把文本里的 OSS 公网地址换回站内上传路径（仅当本地文件确实存在）。"""
    if not text:
        return text, 0
    bases = public_bases()
    if not bases:
        return text, 0
    replaced = 0

    def _sub(match: re.Match) -> str:
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

    return _URL_RE.sub(_sub, text), replaced


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
            uploaded += 1
        except Exception as exc:  # noqa: BLE001
            failed.append({"rel": rel, "error": str(exc)[:160]})
    next_offset = max(0, offset) + len(chunk)
    return {
        "total": total,
        "offset": max(0, offset),
        "processed": len(chunk),
        "uploaded": uploaded,
        "skipped": skipped,
        "failed": failed,
        "next": next_offset,
        "done": next_offset >= total,
    }


def mark_migrated() -> None:
    """记录迁移完成时间，后台状态页用。"""
    from datetime import datetime

    from services import plugins as plugins_service

    data = raw_config()
    data["migrated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plugins_service.save_config(KEY, data)
