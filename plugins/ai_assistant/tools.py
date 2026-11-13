"""AI 助手可调用的白名单工具。

模型只能通过这些函数操作博客，不能拼 SQL、读文件或执行命令。
写操作由路由层二次确认后再调用 `execute`。
"""

from __future__ import annotations

import json
import re

import db
from models import Category, Comment, Link, Post, Project

READ_TOOLS = {
    "list_posts": "列出文章。参数：limit（默认 10，最大 50）、status（published/draft/hidden/all）、order（latest/oldest）",
    "search_posts": "按关键词搜索文章。参数：q、limit（默认 5）",
    "get_post": "读取一篇文章全文。参数：id",
    "list_comments": "列出评论。参数：limit（默认 10）、status（pending/approved/rejected/all）、email、author、post_id",
    "list_links": "列出友链。参数：limit（默认 10）、status、q（名称或地址关键词）",
    "list_categories": "列出文章分类（id/name/slug）",
    "list_projects": "列出项目。参数：limit（默认 10）、q（名称或仓库关键词）",
    "get_project": "读取项目详情。参数：id",
    "get_stats": "读取站点统计（文章/评论/友链数量）",
}

WRITE_TOOLS = {
    "create_post": "创建文章。参数：title、content（Markdown，只写正文不要重复标题）、tags（数组或逗号分隔）、status（published/draft）、category（分类名称）",
    "update_post": "修改文章。参数：id、title、content、tags（数组或逗号分隔，省略则保持原标签）、status、category（分类名称）",
    "delete_post": "删除文章（连带清理未被引用的上传图）。参数：id",
    "create_category": "新建文章分类。参数：name、slug（可选）",
    "update_category": "修改文章分类。参数：id、name、slug（可选）",
    "delete_category": "删除文章分类（该分类下的文章会变成未分类）。参数：id",
    "approve_comment": "通过一条评论。参数：id",
    "reject_comment": "拒绝一条评论。参数：id",
    "delete_comment": "删除一条评论及其子回复。参数：id",
    "reply_comment": "以 AI 助手身份回复评论。参数：id（被回复评论）、content",
    "add_link": "新增友链。参数：name、url、description、avatar",
    "approve_link": "通过一条友链。参数：id",
    "reject_link": "拒绝一条友链。参数：id",
    "delete_link": "删除一条友链。参数：id",
    "create_project": "新建项目。参数：name、description、url、github_repo、topics（数组）",
    "update_project": "修改项目。参数：id、name、description、url、github_repo、topics",
    "delete_project": "删除项目。参数：id",
    "sync_project": "同步 GitHub 项目信息（星标/语言/README）。参数：id（0 表示全部）",
}

# 这些操作即使开启「写操作自动执行」也必须人工确认
FORCE_CONFIRM = {
    "create_post", "update_post", "create_category", "update_category",
    "delete_post", "delete_category", "delete_comment", "delete_link",
    "delete_project",
}

ALL_TOOLS = {**READ_TOOLS, **WRITE_TOOLS}

_POST_STATUSES = {"published", "draft", "hidden"}


def _clip_json(value: dict, limit: int = 4000) -> str:
    """审计列超长时的存储：硬截断会把 JSON 切成非法残片（尾部不闭合），
    留存页解析失败只能直出长串、撑坏表格排版；改为存带截断标记的合法 JSON。"""
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= limit:
        return text
    head = text[: limit - 80].rstrip()
    return json.dumps({"truncated": True, "preview": head + "…"}, ensure_ascii=False)


def _audit(action: str, args: dict, result: dict, ok: bool) -> None:
    try:
        db.execute(
            "INSERT INTO ai_audit (action, args, result, ok, created_at) VALUES (?,?,?,?,datetime('now','localtime'))",
            (action, _clip_json(args), _clip_json(result), 1 if ok else 0),
        )
    except Exception:
        pass


def _limit(value, default=10, maximum=50) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _mask_email(email: str) -> str:
    email = str(email or "").strip()
    if "@" not in email:
        return email
    name, domain = email.split("@", 1)
    if not name:
        return "***@" + domain
    return name[0] + "***@" + domain


def _resolve_category(args: dict) -> tuple[int | None, str]:
    raw_id = args.get("category_id")
    if raw_id:
        try:
            return int(raw_id), ""
        except (TypeError, ValueError):
            pass
    name = str(args.get("category") or "").strip()
    if not name:
        return None, ""
    categories = Category.load()
    for cat in categories:
        if str(cat.get("name")) == name:
            return int(cat["id"]), ""
    names = "、".join(str(c.get("name")) for c in categories)
    return None, f"分类「{name}」不存在，现有分类：{names}"


# 标签分隔符：中英文逗号、顿号、分号、竖线、换行
_TAG_SPLIT = re.compile(r"[,，、;；|\r\n]+")
# 行首一级标题：正文里再写一次标题会导致页面出现两个 H1
_LEADING_H1 = re.compile(r"\A\s*#\s+(.+?)\s*(?:\r?\n|\Z)")
# YAML front matter（有些模型习惯把 title/tags 塞进正文开头）
_FRONT_MATTER = re.compile(r"\A\s*---\s*\r?\n.*?\r?\n---\s*(?:\r?\n|\Z)", re.S)
# 正文开头的元信息行：**标签**：xxx / 作者：xxx / tags: xxx
_META_LINE = re.compile(
    r"\A\s*(?:[-*]\s*)?(?:\*\*)?\s*"
    r"(?:标签|作者|分类|日期|tags?|author|category|date)\s*(?:\*\*)?\s*[:：].*(?:\r?\n|\Z)",
    re.I,
)
# front matter 里的 tags 行：模型有时把标签写在这里而不是 args
_FM_TAGS = re.compile(r"^\s*tags?\s*[:：]\s*(.+)$", re.I | re.M)


def _front_matter_tags(content: str) -> str:
    """从 YAML 头里取 tags，模型忘传 args.tags 时兜底。"""
    text = (content or "").lstrip("\ufeff \t\r\n")
    fm = _FRONT_MATTER.match(text)
    if not fm:
        return ""
    match = _FM_TAGS.search(fm.group(0))
    if not match:
        return ""
    return match.group(1).strip().strip("[]")


def _normalize_tags(raw) -> str:
    """把模型传来的标签收拾成 Post.save 需要的逗号串。

    模型常见写法：数组、`["a", "b"]` 字符串、`#a #b`、中文逗号分隔、
    甚至整段话。这里统一拆开、去 # 和引号、去重，最多保留 8 个。
    """
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple, set)):
        parts: list = list(raw)
    else:
        text = str(raw).strip()
        text = re.sub(r"^(?:标签|tags?)\s*[:：]\s*", "", text, flags=re.I)
        # JSON 数组字符串优先按 JSON 解析，失败再退回普通拆分
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                parts = parsed if isinstance(parsed, list) else [parsed]
            except (TypeError, ValueError):
                parts = _TAG_SPLIT.split(text[1:-1])
        else:
            # #标签 写法统一转成逗号，避免整个 #a #b 成为一个标签
            parts = _TAG_SPLIT.split(text.replace("#", ","))
            # 纯中文空格分隔（“生活 随笔”）也拆开；含英文的「AI 助手」保持原样
            if len(parts) == 1 and re.search(r"[\u4e00-\u9fa5]\s+[\u4e00-\u9fa5]", text):
                parts = re.split(r"\s+", text)

    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for piece in _TAG_SPLIT.split(str(part)):
            tag = piece.strip().strip("\"'“”‘’`").lstrip("#").strip()
            tag = re.sub(r"\s+", " ", tag)
            if not tag or len(tag) > 20 or re.search(r"[。！？!?]", tag):
                continue
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            tags.append(tag)
            if len(tags) >= 8:
                return ",".join(tags)
    return ",".join(tags)


def _strip_title_from_content(title: str, content: str) -> str:
    """清掉正文里重复的标题与模型自带的 front matter。

    页面模板已经把 title 渲染成 H1，正文再以 `# 标题` 开头就会出现两个标题；
    部分模型还会在开头写 YAML 头或「**标签**：」元信息，这些都不该进正文。
    """
    text = (content or "").lstrip("\ufeff \t\r\n")
    if not text:
        return text

    # 只删除「看起来像元信息」的头部块，避免把以 --- 分隔线开头的正文误删
    cleaned_head = False
    fm = _FRONT_MATTER.match(text)
    if fm and re.search(r"^[^\r\n]*[:：]", fm.group(0), re.M):
        text = text[fm.end():].lstrip()
        cleaned_head = True

    match = _LEADING_H1.match(text)
    if match:
        heading = match.group(1)
        # 标题相同（忽略空格/标点/大小写）或高度相似时才删，避免误删作者写的小标题
        def squash(value: str) -> str:
            return re.sub(r"[\s:：,，.。!！?？\-—_·|/]+", "", value).lower()

        left, right = squash(heading), squash(title)
        similar = left == right or (
            len(left) >= 6 and (left in right or right in left) and min(len(left), len(right)) / max(len(left), len(right)) >= 0.6
        )
        if similar:
            text = text[match.end():].lstrip()
            cleaned_head = True

    # 去掉紧跟标题的元信息行和分隔线
    while True:
        meta = _META_LINE.match(text)
        if not meta:
            break
        text = text[meta.end():].lstrip()
        cleaned_head = True
    if cleaned_head:
        text = re.sub(r"\A---+\s*(?:\r?\n|\Z)", "", text).lstrip()
    return text


def _brief_post(row) -> dict:
    item = dict(row)
    return {
        "id": int(item["id"]),
        "title": item.get("title", ""),
        "status": item.get("status", ""),
        "tags": json.loads(item.get("tags") or "[]") if isinstance(item.get("tags"), str) else item.get("tags"),
        "created_at": item.get("created_at", ""),
    }


def execute(name: str, args: dict | None = None, *, audit: bool = True) -> dict:
    args = args or {}
    if name not in ALL_TOOLS:
        return {"ok": False, "error": f"未知工具：{name}"}
    try:
        result = _dispatch(name, args)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)[:300]}
    if audit:
        _audit(name, args, result, bool(result.get("ok")))
    return result


def _dispatch(name: str, args: dict) -> dict:
    if name == "list_posts":
        status = str(args.get("status") or "published")
        order = "ASC" if str(args.get("order") or "") == "oldest" else "DESC"
        limit = _limit(args.get("limit"), 10)
        params: list = []
        # 软删（回收站）文章不进入 AI 视野
        where = "WHERE deleted_at IS NULL"
        if status in _POST_STATUSES:
            where += " AND status = ?"
            params.append(status)
        rows = db.query(
            f"SELECT id, title, status, tags, created_at FROM posts {where} "
            f"ORDER BY created_at {order}, id {order} LIMIT ?",
            (*params, limit),
        )
        return {"ok": True, "posts": [_brief_post(r) for r in rows]}

    if name == "search_posts":
        q = str(args.get("q") or "").strip()
        posts, total = Post.load("published", None, q or None, None, 1, _limit(args.get("limit"), 5))
        return {"ok": True, "total": total, "posts": [
            {"id": p["id"], "title": p["title"], "tags": p.get("tags"), "created_at": p["created_at"]}
            for p in posts
        ]}

    if name == "get_post":
        post = Post.get(int(args.get("id") or 0))
        if not post:
            return {"ok": False, "error": "文章不存在"}
        content = str(post.get("content") or "")
        return {"ok": True, "post": {
            "id": post["id"], "title": post["title"], "status": post["status"],
            "tags": post.get("tags"), "excerpt": post.get("excerpt"),
            "content": content[:8000], "truncated": len(content) > 8000,
        }}

    if name == "list_comments":
        # 带邮箱/昵称/文章等具体条件时，用户意图是「找某人的评论」而非看待审列表，
        # 默认查全部状态（否则全是已通过的评论会被 pending 默认值滤成空，看起来像失效）
        has_filter = bool(str(args.get("email") or "").strip()
                          or str(args.get("author") or "").strip()
                          or args.get("post_id"))
        status = str(args.get("status") or ("all" if has_filter else "pending"))
        limit = _limit(args.get("limit"), 10)
        where: list[str] = []
        params: list = []
        # 已软删除的评论不再进入 AI 视野（正文保留在留存插件供人工查阅）
        where.append("deleted_at IS NULL")
        if status in {"pending", "approved", "rejected"}:
            where.append("status = ?")
            params.append(status)
        email = str(args.get("email") or "").strip()
        if email:
            where.append("email = ?")
            params.append(email)
        author = str(args.get("author") or "").strip()
        if author:
            where.append("author LIKE ?")
            params.append(f"%{author}%")
        try:
            post_id = int(args.get("post_id") or 0)
        except (TypeError, ValueError):
            post_id = 0
        if post_id:
            where.append("post_id = ?")
            params.append(post_id)
        sql = "SELECT id, post_id, project_id, author, email, content, status, is_ai, created_at FROM comments"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = db.query(sql, tuple(params))
        comments = []
        for row in rows:
            item = dict(row)
            item["email"] = _mask_email(item.get("email"))
            item["content"] = str(item.get("content") or "")[:600]
            comments.append(item)
        return {"ok": True, "count": len(comments), "comments": comments}

    if name == "list_links":
        status = str(args.get("status") or "pending")
        limit = _limit(args.get("limit"), 10)
        where: list[str] = []
        params: list = []
        if status in {"pending", "approved", "rejected"}:
            where.append("status = ?")
            params.append(status)
        q = str(args.get("q") or "").strip()
        if q:
            where.append("(name LIKE ? OR url LIKE ? OR description LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        sql = "SELECT id, name, url, description, status, ai_state, created_at FROM links"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = db.query(sql, tuple(params))
        return {"ok": True, "links": [dict(r) for r in rows]}

    if name == "list_categories":
        rows = db.query("SELECT id, name, slug FROM categories ORDER BY sort_order ASC, id ASC")
        return {"ok": True, "categories": [dict(r) for r in rows]}

    if name == "list_projects":
        q = str(args.get("q") or "").strip().lower()
        limit = _limit(args.get("limit"), 10)
        projects = Project.load()
        if q:
            projects = [
                p for p in projects
                if q in str(p.get("name") or "").lower()
                or q in str(p.get("github_repo") or "").lower()
                or q in str(p.get("description") or "").lower()
            ]
        return {"ok": True, "projects": [
            {"id": p["id"], "name": p["name"], "github_repo": p.get("github_repo"),
             "stars": p.get("stars"), "language": p.get("language"), "featured": p.get("featured")}
            for p in projects[:limit]
        ]}

    if name == "get_project":
        project = Project.get(int(args.get("id") or 0))
        if not project:
            return {"ok": False, "error": "项目不存在"}
        return {"ok": True, "project": {
            "id": project["id"], "name": project["name"],
            "description": project.get("description"), "url": project.get("url"),
            "github_repo": project.get("github_repo"), "topics": project.get("topics"),
            "stars": project.get("stars"), "language": project.get("language"),
            "featured": project.get("featured"),
        }}

    if name == "get_stats":
        return {"ok": True, "stats": {
            "posts": int(db.scalar("SELECT COUNT(*) FROM posts WHERE deleted_at IS NULL", (), 0)),
            "published": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='published' AND deleted_at IS NULL", (), 0)),
            "drafts": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='draft' AND deleted_at IS NULL", (), 0)),
            "comments": int(
                db.scalar("SELECT COUNT(*) FROM comments WHERE deleted_at IS NULL", (), 0)
            ),
            "pending_comments": int(
                db.scalar(
                    "SELECT COUNT(*) FROM comments WHERE status='pending' AND deleted_at IS NULL", (), 0
                )
            ),
            "links": int(db.scalar("SELECT COUNT(*) FROM links", (), 0)),
            "pending_links": int(db.scalar("SELECT COUNT(*) FROM links WHERE status='pending'", (), 0)),
        }}

    if name == "create_post":
        title = str(args.get("title") or "").strip()
        raw_content = str(args.get("content") or "")
        content = _strip_title_from_content(title, raw_content)
        if not title or not content:
            return {"ok": False, "error": "标题和正文不能为空"}
        category_id, cat_error = _resolve_category(args)
        if cat_error:
            return {"ok": False, "error": cat_error}
        tags = _normalize_tags(args.get("tags") or _front_matter_tags(raw_content))
        status = "draft" if str(args.get("status") or "") == "draft" else "published"
        pid = Post.save({
            "title": title,
            "content": content,
            "tags": tags,
            "status": status,
            "category_id": str(category_id) if category_id else "",
        })
        return {"ok": True, "id": pid, "message": f"已创建文章《{title}》（{status}）"}

    if name == "update_post":
        pid = int(args.get("id") or 0)
        post = Post.get(pid)
        if not post:
            return {"ok": False, "error": "文章不存在"}
        category_id = post.get("category_id")
        if args.get("category") or args.get("category_id"):
            category_id, cat_error = _resolve_category(args)
            if cat_error:
                return {"ok": False, "error": cat_error}
        title = str(args.get("title") or post["title"]).strip()
        content = _strip_title_from_content(
            title, str(args.get("content") or post.get("content") or "")
        )
        form = {
            "title": title,
            "content": content,
            "tags": _normalize_tags(args.get("tags")) or ",".join(post.get("tags") or []),
            "status": str(args.get("status") or post["status"]),
            "category_id": str(category_id) if category_id else "",
            "excerpt": post.get("excerpt") or "",
            "excerpt_manual": "0",
        }
        Post.save(form, pid)
        return {"ok": True, "id": pid, "message": f"已更新文章《{form['title']}》"}

    if name == "create_category":
        name = str(args.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "分类名称不能为空"}
        cid = Category.save({"name": name, "slug": str(args.get("slug") or "").strip(), "sort_order": 0})
        return {"ok": True, "id": cid, "message": f"已创建分类：{name}"}

    if name == "update_category":
        cid = int(args.get("id") or 0)
        cat = Category.get(cid)
        if not cat:
            return {"ok": False, "error": "分类不存在"}
        new_name = str(args.get("name") or cat.get("name") or "").strip()
        Category.save({
            "name": new_name,
            "slug": str(args.get("slug") or cat.get("slug") or "").strip(),
            "sort_order": cat.get("sort_order") or 0,
        }, cid)
        return {"ok": True, "id": cid, "message": f"已更新分类：{new_name}"}

    if name == "delete_post":
        pid = int(args.get("id") or 0)
        if not Post.get(pid):
            return {"ok": False, "error": "文章不存在"}
        # 与后台一致：删除只进回收站，可恢复；彻底删除由博主在后台操作
        Post.trash(pid)
        return {"ok": True, "message": f"文章 #{pid} 已移入回收站（可在后台回收站恢复）"}

    if name == "delete_category":
        cid = int(args.get("id") or 0)
        if not Category.get(cid):
            return {"ok": False, "error": "分类不存在"}
        Category.delete(cid)
        return {"ok": True, "message": f"已删除分类 #{cid}，该分类下的文章已转为未分类"}

    if name == "reject_comment":
        cid = int(args.get("id") or 0)
        if not Comment.get(cid):
            return {"ok": False, "error": "评论不存在"}
        Comment.set_status(cid, "rejected")
        return {"ok": True, "message": f"评论 #{cid} 已拒绝"}

    if name == "delete_comment":
        cid = int(args.get("id") or 0)
        if not Comment.get(cid):
            return {"ok": False, "error": "评论不存在"}
        Comment.delete(cid)
        return {"ok": True, "message": f"评论 #{cid} 及其回复已删除"}

    if name == "reject_link":
        lid = int(args.get("id") or 0)
        if not Link.get(lid):
            return {"ok": False, "error": "友链不存在"}
        Link.set_status(lid, "rejected")
        return {"ok": True, "message": f"友链 #{lid} 已拒绝"}

    if name == "delete_link":
        lid = int(args.get("id") or 0)
        if not Link.get(lid):
            return {"ok": False, "error": "友链不存在"}
        Link.delete(lid)
        return {"ok": True, "message": f"友链 #{lid} 已删除"}

    if name == "create_project":
        pname = str(args.get("name") or "").strip()
        if not pname:
            return {"ok": False, "error": "项目名称不能为空"}
        pid = Project.save({
            "name": pname,
            "description": str(args.get("description") or ""),
            "url": str(args.get("url") or ""),
            "github_repo": str(args.get("github_repo") or ""),
            "topics": args.get("topics") or [],
        })
        return {"ok": True, "id": pid, "message": f"已创建项目：{pname}"}

    if name == "update_project":
        pid = int(args.get("id") or 0)
        project = Project.get(pid)
        if not project:
            return {"ok": False, "error": "项目不存在"}
        Project.save({
            "name": str(args.get("name") or project["name"]),
            "description": str(args.get("description") or project.get("description") or ""),
            "url": str(args.get("url") or project.get("url") or ""),
            "github_repo": str(args.get("github_repo") or project.get("github_repo") or ""),
            "topics": args.get("topics") or project.get("topics") or [],
            "language": project.get("language") or "",
            "stars": project.get("stars") or 0,
            "sort_order": project.get("sort_order") or 0,
            "featured": project.get("featured") or 0,
        }, pid)
        return {"ok": True, "id": pid, "message": f"已更新项目：{args.get('name') or project['name']}"}

    if name == "delete_project":
        pid = int(args.get("id") or 0)
        if not Project.get(pid):
            return {"ok": False, "error": "项目不存在"}
        Project.delete(pid)
        return {"ok": True, "message": f"已删除项目 #{pid}"}

    if name == "sync_project":
        from services import project_sync

        pid = int(args.get("id") or 0)
        if pid:
            if not Project.get(pid):
                return {"ok": False, "error": "项目不存在"}
            project_sync.sync_one_background(pid)
            return {"ok": True, "message": f"已开始同步项目 #{pid}，完成后到项目管理查看"}
        project_sync.sync_all_background()
        return {"ok": True, "message": "已开始同步全部项目，完成后到项目管理查看"}

    if name == "approve_comment":
        cid = int(args.get("id") or 0)
        if not Comment.get(cid):
            return {"ok": False, "error": "评论不存在"}
        Comment.set_status(cid, "approved")
        return {"ok": True, "message": f"评论 #{cid} 已通过"}

    if name == "reply_comment":
        cid = int(args.get("id") or 0)
        content = str(args.get("content") or "").strip()
        parent = Comment.get(cid)
        if not parent or not content:
            return {"ok": False, "error": "评论不存在或回复为空"}
        # 昵称/头像读配置，与评论托管回复保持一致（徽章固定显示「AI 助手」）
        from . import config as ai_config

        ai_name = str(ai_config.get().get("ai_name") or "").strip() or "AI 助手"
        new_id = Comment.save(
            parent.get("post_id"), ai_name, "", "", "", content,
            cid, 0, "", "", "approved", parent.get("project_id"), "",
            is_ai=1,
        )
        db.execute(
            "UPDATE comments SET ai_meta=? WHERE id=?",
            (json.dumps({"avatar": ai_config.ai_avatar_url()}, ensure_ascii=False), new_id),
        )
        return {"ok": True, "id": new_id, "message": f"已回复评论 #{cid}"}

    if name == "add_link":
        name = str(args.get("name") or "").strip()
        url = str(args.get("url") or "").strip()
        if not name or not url:
            return {"ok": False, "error": "名称和地址不能为空"}
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        lid = Link.save({"name": name, "url": url, "description": str(args.get("description") or ""), "avatar": str(args.get("avatar") or ""), "sort_order": 0}, None, "approved")
        return {"ok": True, "id": lid, "message": f"已添加友链：{name}"}

    if name == "approve_link":
        lid = int(args.get("id") or 0)
        if not Link.get(lid):
            return {"ok": False, "error": "友链不存在"}
        Link.set_status(lid, "approved")
        return {"ok": True, "message": f"友链 #{lid} 已通过"}

    return {"ok": False, "error": "工具未实现"}
