"""后台管理路由。"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import (
    abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for,
)

import db
from config import BACKUPS_DIR, DATA_DIR, UPLOADS_DIR, VERSION, ADMIN_PATH_RESERVED
from models import Category, Comment, Link, Post, Project, Timeline, User
from services import auth, avatar, backup, github, lang, markdown, notify, otp, project_sync
from services import settings, status, theme, upload

LOGIN = auth.admin_required


def _ids(name: str) -> list[int]:
    values = request.form.getlist(name) or request.form.getlist(name + "[]")
    return [int(v) for v in values if str(v).isdigit()]


# ── 仪表盘 ─────────────────────────────────────────────
@LOGIN
def admin_dashboard():
    stats = Post.stats()
    link_stats = Link.stats()
    rows = db.query("SELECT * FROM posts ORDER BY updated_at DESC, id DESC LIMIT 5")
    recent = [Post.hydrate(r) for r in rows]
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent=recent,
        pending_comments=Comment.pending_count(),
        pending_links=link_stats["pending"],
        upgrade_stale=True,
    )


# ── 文章 ──────────────────────────────────────────────
@LOGIN
def admin_posts():
    status_filter = request.args.get("status", "all")
    search = request.args.get("q", "")
    page = max(1, request.args.get("page", 1, type=int) or 1)
    if status_filter == "all":
        posts, total = Post.load(None, None, search or None, None, page)
    else:
        posts, total = Post.load(status_filter, None, search or None, None, page)
    total_pages = max(1, (total + Post.PAGE_SIZE - 1) // Post.PAGE_SIZE)
    page = min(page, total_pages)
    names = Category.name_map()
    for post in posts:
        post["category_name"] = names.get(int(post["category_id"]), "") if post.get("category_id") else ""
    return render_template(
        "admin/posts.html",
        posts=posts,
        status_filter=status_filter,
        search_query=search,
        page=page,
        total_pages=total_pages,
        total=total,
        args=request.args,
    )


@LOGIN
def admin_posts_bulk():
    action = request.form.get("action", "")
    ids = _ids("post_ids")
    if action not in {"publish", "unpublish", "hide", "delete"}:
        flash("无效的批量操作", "error")
        return redirect(url_for("admin_posts"))
    if not ids:
        flash("未选择任何文章", "error")
        return redirect(url_for("admin_posts"))
    if action == "delete":
        for pid in ids:
            Post.delete_with_uploads(pid)
        flash(f"已删除 {len(ids)} 篇文章", "success")
    else:
        mapping = {"publish": ("published", "已发布"), "unpublish": ("draft", "草稿"), "hide": ("hidden", "隐藏")}
        state, label = mapping[action]
        Post.bulk_set_status(ids, state)
        flash(f"已将 {len(ids)} 篇文章设为「{label}」", "success")
    return redirect(url_for("admin_posts"))


def _upload_cfg() -> dict:
    image = upload.image_exts()
    media = upload.media_exts()
    file_ext = upload.file_exts()
    return {
        "image": sorted(image),
        "media": sorted(media),
        "file": sorted(file_ext),
        "max": upload.max_size(),
        "accept": ",".join(sorted(image | media | file_ext)),
    }


@LOGIN
def admin_post_new():
    categories = Category.load()
    all_tags = Post.all_tags()
    if request.method == "POST":
        if not str(request.form.get("category_id", "")).isdigit():
            flash("请选择文章分类", "error")
            return render_template(
                "admin/post_edit.html", post=None, categories=categories,
                all_tags=all_tags, upload_cfg=_upload_cfg(),
            )
        Post.save(request.form)
        flash("文章已创建", "success")
        return redirect(url_for("admin_posts"))
    return render_template(
        "admin/post_edit.html", post=None, categories=categories,
        all_tags=all_tags, upload_cfg=_upload_cfg(),
    )


@LOGIN
def admin_post_edit(post_id: int):
    post = Post.get(post_id)
    if not post:
        flash("文章不存在", "error")
        return redirect(url_for("admin_posts"))
    if request.method == "POST":
        Post.save(request.form, post_id)
        flash("文章已更新", "success")
        return redirect(url_for("admin_posts"))
    post["content"] = re.sub(r"<(https?://[^>\s]+)>", r"[\1](\1)", post.get("content") or "")
    return render_template(
        "admin/post_edit.html", post=post, categories=Category.load(),
        all_tags=Post.all_tags(), upload_cfg=_upload_cfg(),
    )


@LOGIN
def admin_post_delete(post_id: int):
    removed = Post.delete_with_uploads(post_id)
    if removed:
        flash(f"文章已删除，并清理 {removed} 个不再被引用的上传文件", "success")
    else:
        flash("文章已删除", "success")
    return redirect(url_for("admin_posts"))


@LOGIN
def admin_post_preview(post_id: int):
    post = Post.get(post_id)
    html, _ = markdown.render_post(post.get("content") or "") if post else ("", "")
    return jsonify({"html": html})


@LOGIN
def admin_preview_content():
    html, _ = markdown.render_post(request.form.get("content", ""))
    return jsonify({"html": html})


# ── 分类 ──────────────────────────────────────────────
@LOGIN
def admin_categories():
    return render_template("admin/categories.html", categories=Category.stats())


@LOGIN
def admin_category_new():
    if request.method == "POST":
        Category.save(request.form)
        flash("分类已创建", "success")
        return redirect(url_for("admin_categories"))
    return render_template("admin/category_edit.html", category=None)


@LOGIN
def admin_category_edit(cat_id: int):
    category = Category.get(cat_id)
    if not category:
        abort(404)
    if request.method == "POST":
        Category.save(request.form, cat_id)
        flash("分类已更新", "success")
        return redirect(url_for("admin_categories"))
    return render_template("admin/category_edit.html", category=category)


@LOGIN
def admin_category_delete(cat_id: int):
    Category.delete(cat_id)
    flash("分类已删除", "success")
    return redirect(url_for("admin_categories"))


@LOGIN
def admin_categories_bulk():
    if request.form.get("action") != "delete":
        flash("无效的批量操作", "error")
        return redirect(url_for("admin_categories"))
    ids = _ids("cat_ids")
    if not ids:
        flash("未选择任何分类", "error")
        return redirect(url_for("admin_categories"))
    Category.bulk_delete(ids)
    flash(f"已删除 {len(ids)} 个分类（该分类下文章已变为未分类）", "success")
    return redirect(url_for("admin_categories"))


# ── 项目 ──────────────────────────────────────────────
@LOGIN
def admin_projects():
    projects = [lang.decorate(p) for p in Project.load()]
    return render_template("admin/projects.html", projects=projects)


@LOGIN
def admin_project_new():
    if request.method == "POST":
        repo = github.parse_repo(request.form.get("url", ""))
        if repo and Project.repo_exists(repo):
            flash(f"该项目已存在，不能重复添加（{repo}）", "error")
            return render_template("admin/project_edit.html", project=None)
        payload = {}
        if repo:
            payload = github.fetch_and_cache(repo)
        gh = payload.get("gh") or {}
        Project.save(
            {
                **request.form.to_dict(),
                "github_repo": repo or "",
                "stars": gh.get("stars") or request.form.get("stars") or 0,
                "language": gh.get("language") or request.form.get("language") or "",
                "topics": gh.get("topics") or request.form.get("topics") or "",
                "languages": gh.get("languages") or [],
                "description": request.form.get("description") or gh.get("description") or "",
            }
        )
        flash("项目已添加（已尝试同步 GitHub 数据）", "success")
        return redirect(url_for("admin_projects"))
    return render_template("admin/project_edit.html", project=None)


@LOGIN
def admin_project_edit(project_id: int):
    project = Project.get(project_id)
    if not project:
        flash("项目不存在", "error")
        return redirect(url_for("admin_projects"))
    if request.method == "POST":
        Project.save(request.form, project_id)
        flash("项目已更新", "success")
        return redirect(url_for("admin_projects"))
    return render_template("admin/project_edit.html", project=project)


@LOGIN
def admin_project_delete(project_id: int):
    Project.delete(project_id)
    flash("项目已删除", "success")
    return redirect(url_for("admin_projects"))


@LOGIN
def admin_projects_bulk():
    if request.form.get("action") != "delete":
        flash("无效的批量操作", "error")
        return redirect(url_for("admin_projects"))
    ids = _ids("project_ids")
    if not ids:
        flash("未选择任何项目", "error")
        return redirect(url_for("admin_projects"))
    Project.bulk(ids, "delete")
    flash(f"已删除 {len(ids)} 个项目", "success")
    return redirect(url_for("admin_projects"))


@LOGIN
def admin_project_sync(project_id: int):
    project = Project.get(project_id)
    if not project:
        return jsonify({"started": False, "error": "项目不存在"})
    project_sync.sync_one_background(project_id)
    return jsonify({"started": True, "total": 1})


@LOGIN
def admin_projects_sync_all():
    if not Project.load():
        return jsonify({"started": False, "error": "没有可同步的项目"})
    project_sync.sync_all_background()
    return jsonify({"started": True, "total": len(Project.load())})


@LOGIN
def admin_projects_sync_status():
    return jsonify(project_sync.state())


# ── 友链 ──────────────────────────────────────────────
@LOGIN
def admin_links():
    return render_template(
        "admin/links.html", links=Link.load("approved"), pending=Link.load("pending")
    )


@LOGIN
def admin_link_approve(link_id: int):
    Link.set_status(link_id, "approved")
    flash("友链已通过审核", "success")
    return redirect(url_for("admin_links"))


@LOGIN
def admin_link_reject(link_id: int):
    Link.set_status(link_id, "rejected")
    flash("友链已拒绝", "success")
    return redirect(url_for("admin_links"))


@LOGIN
def admin_link_new():
    if request.method == "POST":
        Link.save(request.form)
        flash("链接已添加", "success")
        return redirect(url_for("admin_links"))
    return render_template("admin/link_edit.html", link=None)


@LOGIN
def admin_link_edit(link_id: int):
    link = Link.get(link_id)
    if not link:
        flash("链接不存在", "error")
        return redirect(url_for("admin_links"))
    if request.method == "POST":
        Link.save(request.form, link_id)
        flash("链接已更新", "success")
        return redirect(url_for("admin_links"))
    return render_template("admin/link_edit.html", link=link)


@LOGIN
def admin_link_delete(link_id: int):
    Link.delete(link_id)
    flash("链接已删除", "success")
    return redirect(url_for("admin_links"))


@LOGIN
def admin_links_bulk():
    action = request.form.get("action", "")
    ids = _ids("link_ids")
    if action not in {"approve", "reject", "delete"}:
        flash("无效的批量操作", "error")
        return redirect(url_for("admin_links"))
    if not ids:
        flash("未选择任何链接", "error")
        return redirect(url_for("admin_links"))
    if action == "delete":
        for lid in ids:
            Link.delete(lid)
        flash(f"已删除 {len(ids)} 条链接", "success")
    else:
        state = "approved" if action == "approve" else "rejected"
        for lid in ids:
            Link.set_status(lid, state)
        flash(f"已将 {len(ids)} 条链接设为「{'已通过' if action == 'approve' else '已拒绝'}」", "success")
    return redirect(url_for("admin_links"))


# ── 时间线 ────────────────────────────────────────────
@LOGIN
def admin_timeline():
    return render_template("admin/timeline.html", items=Timeline.load())


@LOGIN
def admin_timeline_new():
    if request.method == "POST":
        if not (request.form.get("date") or "").strip() or not (request.form.get("content") or "").strip():
            flash("日期和内容不能为空", "error")
            return render_template("admin/timeline_edit.html", item=None)
        Timeline.save(request.form)
        flash("历程已添加", "success")
        return redirect(url_for("admin_timeline"))
    return render_template("admin/timeline_edit.html", item=None)


@LOGIN
def admin_timeline_edit(item_id: int):
    item = Timeline.get(item_id)
    if not item:
        flash("历程不存在", "error")
        return redirect(url_for("admin_timeline"))
    if request.method == "POST":
        if not (request.form.get("date") or "").strip() or not (request.form.get("content") or "").strip():
            flash("日期和内容不能为空", "error")
            return render_template("admin/timeline_edit.html", item=item)
        Timeline.save(request.form, item_id)
        flash("历程已更新", "success")
        return redirect(url_for("admin_timeline"))
    return render_template("admin/timeline_edit.html", item=item)


@LOGIN
def admin_timeline_delete(item_id: int):
    Timeline.delete(item_id)
    flash("历程已删除", "success")
    return redirect(url_for("admin_timeline"))


@LOGIN
def admin_timeline_bulk():
    if request.form.get("action") != "delete":
        flash("无效的批量操作", "error")
        return redirect(url_for("admin_timeline"))
    ids = _ids("timeline_ids")
    if not ids:
        flash("未选择任何历程", "error")
        return redirect(url_for("admin_timeline"))
    Timeline.bulk(ids, "delete")
    flash(f"已删除 {len(ids)} 条历程", "success")
    return redirect(url_for("admin_timeline"))


# ── 评论 ──────────────────────────────────────────────
@LOGIN
def admin_comments():
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = max(1, min(100, settings.get_int("admin_comments_per_page", Comment.ADMIN_PAGE_SIZE)))
    items, total = Comment.admin_list(page, per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
        items, total = Comment.admin_list(page, per_page)
    author_name = settings.get_str("author", "")
    cfg_avatar = settings.get_str("avatar", "").strip()
    cfg_ok = avatar.configured_avatar_exists()
    default_url = avatar.default_url()
    for item in items:
        is_author = bool(author_name) and item.get("author") == author_name
        if is_author and cfg_avatar and cfg_ok:
            item["admin_avatar"] = cfg_avatar
        else:
            item["admin_avatar"] = avatar.urls(
                str(item.get("email_hash") or ""), str(item.get("qq") or "")
            )[0]
        if not item["admin_avatar"]:
            item["admin_avatar"] = default_url
        item["admin_avatar_default"] = default_url
    return render_template(
        "admin/comments.html",
        comments=items,
        page=page,
        total_pages=total_pages,
        total=total,
    )


def _comments_back():
    """评论操作结束后回到原分页：页码由表单里的 page 字段带回。"""
    page = (request.form.get("page") or "").strip()
    if page.isdigit() and int(page) > 1:
        return redirect(url_for("admin_comments", page=int(page)))
    return redirect(url_for("admin_comments"))


@LOGIN
def admin_comment_approve(comment_id: int):
    previous = Comment.get(comment_id)
    Comment.set_status(comment_id, "approved")
    # 待审核 -> 通过时，补发「收到回复」邮件给被回复的访客
    if previous and previous.get("status") != "approved":
        notify.notify_approved_reply(comment_id)
    flash("评论已通过", "success")
    return _comments_back()


@LOGIN
def admin_comment_delete(comment_id: int):
    Comment.delete(comment_id)
    flash("评论及其回复已删除", "success")
    return _comments_back()


@LOGIN
def admin_comments_bulk():
    action = request.form.get("action", "")
    ids = _ids("comment_ids")
    if action not in {"approve", "delete"}:
        flash("无效的批量操作", "error")
        return _comments_back()
    if not ids:
        flash("未选择任何评论", "error")
        return _comments_back()
    if action == "approve":
        marks = ",".join("?" * len(ids))
        fresh = [
            int(row["id"])
            for row in db.query(
                f"SELECT id FROM comments WHERE id IN ({marks}) AND status != 'approved'",
                ids,
            )
        ]
        Comment.bulk(ids, "approve")
        for cid in fresh:
            notify.notify_approved_reply(cid)
        flash(f"已通过 {len(ids)} 条评论", "success")
    else:
        for cid in ids:
            Comment.delete(cid)
        flash(f"已删除 {len(ids)} 条评论及其回复", "success")
    return _comments_back()


# ── 上传 ──────────────────────────────────────────────
@LOGIN
def admin_upload_image():
    url, error = upload.save(request.files.get("image") or request.files.get("file"), upload.image_exts())
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"url": url})


@LOGIN
def admin_upload_media():
    file = request.files.get("file") or request.files.get("media")
    url, error = upload.save(file, upload.media_exts())
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"url": url, "name": Path(url).name})


@LOGIN
def admin_upload_file():
    url, error = upload.save(request.files.get("file"), upload.file_exts())
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"url": url, "name": Path(url).name})


@LOGIN
def admin_orphans():
    items = upload.orphans()
    total = sum(item["size_bytes"] for item in items)
    return render_template("admin/orphans.html", orphans=items, total_size=upload.fmt_size(total))


@LOGIN
def admin_orphan_clean():
    # 前端批量删除使用 path[]；兼容旧表单的 path
    selected = request.form.getlist("path") + request.form.getlist("path[]")
    selected = list(dict.fromkeys(selected))
    results = []
    deleted = failed = 0
    for rel in selected:
        reason = upload.delete_rel(rel)
        if reason:
            failed += 1
            results.append({"rel": rel, "ok": False, "reason": reason})
        else:
            deleted += 1
            results.append({"rel": rel, "ok": True})
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"deleted": deleted, "failed": failed, "results": results})
    if deleted:
        flash(f"已清理 {deleted} 个孤儿文件" + (f"，{failed} 个删除失败" if failed else ""), "success" if not failed else "error")
    elif failed:
        flash(f"{failed} 个文件删除失败", "error")
    else:
        flash("没有可清理的文件", "success")
    return redirect(url_for("admin_orphans"))


# ── 服务时效 ──────────────────────────────────────────
@LOGIN
def admin_status():
    if request.method == "POST":
        return _save_status()
    return render_template(
        "admin/status.html",
        expiry=status.expiry_info(),
        services=status.parse_services(),
        status_items=status.snapshot()[1],
        upgrade_stale=False,
    )


def _save_status():
    texts = [
        "aliyun_access_key", "aliyun_server_type", "aliyun_access_secret", "aliyun_region",
        "aliyun_instance_id", "tencent_secret_id", "tencent_secret_key", "tencent_domain",
        "expiry_aliyun", "expiry_tencent", "aliyun_expiry_api", "tencent_expiry_api",
    ]
    for key in texts:
        if key in request.form:
            settings.set_value(key, request.form.get(key, "").strip())

    names = request.form.getlist("svc_name") or request.form.getlist("svc_name[]")
    urls = request.form.getlist("svc_url") or request.form.getlist("svc_url[]")
    services = []
    for name, url in zip(names, urls):
        name, url = name.strip(), url.strip()
        if not name or not url:
            continue
        if not re.match(r"^https?://", url):
            url = "https://" + url
        services.append({"name": name, "url": url})
    settings.set_value("monitor_services", json.dumps(services, ensure_ascii=False))

    try:
        status.probe_all(True)
    except Exception:
        pass
    flash("服务时效配置已保存", "success")
    return redirect(url_for("admin_status"))


@LOGIN
def admin_status_probe():
    status.probe_all(True)
    return jsonify({"ok": True, "services": status.snapshot()[1]})


@LOGIN
def admin_status_test_cloud():
    return jsonify({"ok": True, "expiry": status.expiry_info()})


# ── 主题 ──────────────────────────────────────────────
@LOGIN
def admin_themes():
    if request.method == "POST":
        return _activate_theme()
    return render_template("admin/themes.html")


def _activate_theme():
    new_theme = request.form.get("active_theme", "").strip()
    valid = {item["key"] for item in theme.list_themes()}
    if new_theme and new_theme in valid:
        settings.set_value("active_theme", new_theme)
        from flask import current_app

        loader = current_app.extensions.get("theme_loader")
        if loader is not None:
            loader.searchpath = [str(theme.active_template_dir())]
        # 主题模板同名，必须清空 Jinja 模板缓存才会立即生效
        current_app.jinja_env.cache.clear()
        flash(f"主题已切换为：{new_theme}", "success")
    else:
        flash(f"无效的主题：{new_theme}", "error")

    # 主题页的「页面背景装饰」跟随主题一起保存
    if "pattern_enabled" in request.form or "pattern_opacity" in request.form:
        settings.set_value(
            "pattern_enabled", "1" if request.form.get("pattern_enabled") else "0"
        )
        try:
            opacity = int(request.form.get("pattern_opacity") or "20")
        except ValueError:
            opacity = 20
        settings.set_value("pattern_opacity", str(max(0, min(30, opacity))))

    if "pattern_image" in request.form:
        image = request.form.get("pattern_image", "3").strip()
        if image not in {"1", "2", "3"}:
            image = "3"
        settings.set_value("pattern_image", image)

    # 左右固定模式的左右两张图：各自独立选择，允许相同
    if "pattern_left_image" in request.form:
        left = request.form.get("pattern_left_image", "1").strip()
        if left not in {"1", "2", "3"}:
            left = "1"
        settings.set_value("pattern_left_image", left)

    if "pattern_right_image" in request.form:
        right = request.form.get("pattern_right_image", "").strip()
        if right not in {"1", "2", "3"}:
            right = ""
        settings.set_value("pattern_right_image", right)

    if "pattern_position" in request.form:
        position = request.form.get("pattern_position", "cover").strip()
        if position not in {"cover", "left", "right", "both"}:
            position = "cover"
        settings.set_value("pattern_position", position)

    return redirect(url_for("admin_themes"))


# ── 设置 ──────────────────────────────────────────────
TEXT_KEYS = [
    "blog_name", "blog_subtitle", "author", "author_bio", "about_intro", "skills",
    "avatar", "github_username", "social_github", "github_token", "contact_email",
    "home_title", "home_quotes", "icp_beian", "police_beian", "home_posts_count", "posts_per_page",
    "smtp_host", "smtp_sender_name", "smtp_port", "smtp_user", "smtp_pass",
    "notify_email", "footer_copyright_year", "footer_copyright_owner",
    "footer_powered_by", "stats_code", "sensitive_words",
]


def _settings_view() -> dict:
    from app import _sanitize_stats
    from services.site_url import base

    return {
        "admin_username": (auth.current_user() or {}).get("username", "admin"),
        "admin_path": settings.get_str("admin_path", "admin"),
        "admin_avatar": settings.get_str("avatar", ""),
        "avatar_exists": avatar.configured_avatar_exists(),
        "site_url": settings.get_str("site_url", ""),
        "current_url": base(),
        "force_https": "1" if settings.bool_of("force_https") else "0",
        "unify_www": "1" if settings.bool_of("unify_www") else "0",
        "home_quotes": settings.get_str("home_quotes", ""),
        "smtp_host": settings.get_str("smtp_host", ""),
        "smtp_port": settings.get_str("smtp_port", "465"),
        "smtp_user": settings.get_str("smtp_user", ""),
        "smtp_pass": settings.get_str("smtp_pass", ""),
        "notify_email": settings.get_str("notify_email", ""),
        "smtp_sender_name": settings.get_str("smtp_sender_name", ""),
        "comment_notify": settings.get_str("comment_notify", "0"),
        "comment_image_upload": settings.get_str("comment_image_upload", "1"),
        "sensitive_filter_enabled": settings.get_str("sensitive_filter_enabled", "0"),
        "sensitive_words": settings.get_str("sensitive_words", ""),
        "watermark_enabled": settings.get_str("watermark_enabled", "1"),
        "watermark_text": settings.get_str("watermark_text", ""),
        "watermark_position": settings.get_str("watermark_position", "br"),
        "watermark_size": settings.get_str("watermark_size", "m"),
        "upload_image_ext": ", ".join(sorted(upload.image_exts())),
        "upload_media_ext": ", ".join(sorted(upload.media_exts())),
        "upload_file_ext": ", ".join(sorted(upload.file_exts())),
        "upload_max_size": str(max(1, round(upload.max_size() / 1048576))),
        "wm_refresh": {"state": "idle"},
        "otp_enabled": otp.configured(),
        "otp_secret_set": bool(otp.secret()),
        "otp_emergency": (Path(DATA_DIR) / ".otp_disable").is_file(),
        "otp_recovery_left": otp.recovery_remaining(),
        "otp_new_codes": session.pop("_otp_new_codes", None),
        "otp_mail_ok": bool(settings.get_str("smtp_host", "")),
        "comments_enabled": settings.get_str("comments_enabled", "1"),
        "comments_per_page": settings.get_str("comments_per_page", "10"),
        "admin_comments_per_page": settings.get_str("admin_comments_per_page", "20"),
        "nav_posts": settings.get_str("nav_posts", "1"),
        "nav_tags": settings.get_str("nav_tags", "1"),
        "nav_projects": settings.get_str("nav_projects", "1"),
        "nav_links": settings.get_str("nav_links", "1"),
        "nav_status": settings.get_str("nav_status", "1"),
        "nav_about": settings.get_str("nav_about", "1"),
        "stats_code": settings.get_str("stats_code", ""),
    }


@LOGIN
def admin_settings():
    if request.method == "POST":
        return _save_settings()
    return render_template("admin/settings.html", **_settings_view())


def _save_settings():
    from app import _sanitize_stats

    full_form = str(request.form.get("_settings_form") or "") == "1"

    for key in TEXT_KEYS:
        if key not in request.form:
            continue
        value = request.form.get(key, "")
        if key == "stats_code":
            value = _sanitize_stats(value)
        settings.set_value(key, value)

    if "comments_per_page" in request.form:
        try:
            per_page = int((request.form.get("comments_per_page") or "10").strip())
        except ValueError:
            per_page = 10
        settings.set_value("comments_per_page", str(max(0, min(100, per_page))))

    if "admin_comments_per_page" in request.form:
        try:
            admin_per_page = int((request.form.get("admin_comments_per_page") or "20").strip())
        except ValueError:
            admin_per_page = 20
        settings.set_value("admin_comments_per_page", str(max(1, min(100, admin_per_page))))

    if full_form or "site_url" in request.form:
        raw_site = (request.form.get("site_url") or "").strip().rstrip("/")
        if raw_site:
            if re.match(r"^https?://[^/\s]+$", raw_site):
                settings.set_value("site_url", raw_site)
            else:
                flash("站点地址格式不正确，已保留原值；请填写 https://example.com 这样的站点根地址", "error")
        else:
            settings.set_value("site_url", "")

    for key in (
        "force_https", "unify_www", "comments_enabled", "comment_notify",
        "comment_image_upload", "sensitive_filter_enabled", "watermark_enabled",
    ):
        if full_form or key in request.form:
            settings.set_value(key, "1" if request.form.get(key) else "0")
    for key in ("watermark_text", "watermark_position", "watermark_size"):
        if key in request.form:
            settings.set_value(key, request.form.get(key, ""))
    for key, label in (
        ("upload_image_ext", upload.IMAGE_EXTS), ("upload_media_ext", upload.MEDIA_EXTS),
        ("upload_file_ext", upload.FILE_EXTS),
    ):
        if key in request.form:
            exts = upload.normalize_ext_input(request.form.get(key, ""), label)
            settings.set_value(key, ",".join(sorted(c.lstrip(".") for c in exts)))
    if "upload_max_size" in request.form:
        try:
            mb = int(request.form.get("upload_max_size", "20"))
        except ValueError:
            mb = 20
        settings.set_value("upload_max_size", str(min(max(mb, 1), 512)))

    for key in ("posts", "tags", "projects", "links", "status", "about"):
        field = f"nav_{key}"
        if full_form or field in request.form:
            settings.set_value(field, "1" if str(request.form.get(field, "")) == "1" else "0")

    # 后台入口路径（需重启生效）
    new_admin_path = (request.form.get("admin_path") or "").strip().strip("/")
    if full_form and new_admin_path:
        current_path = settings.get_str("admin_path", "admin")
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", new_admin_path):
            flash("后台入口路径不合法（仅支持字母、数字、下划线、连字符，2-32 位）", "error")
        elif new_admin_path.lower() in ADMIN_PATH_RESERVED and new_admin_path.lower() != "admin":
            flash("该路径为系统保留路径，请换一个", "error")
        elif new_admin_path != current_path:
            settings.set_value("admin_path", new_admin_path)
            flash(f"后台入口已修改为 /{new_admin_path}，请重启服务后使用新入口登录", "success")

    # 账号名
    new_username = (request.form.get("admin_username") or "").strip()
    user = auth.current_user()
    if user and new_username and new_username != user["username"]:
        if not re.fullmatch(r"[\w\u4e00-\u9fff\-]{2,30}", new_username):
            flash("账号名格式不合法（2-30 字符）", "error")
        elif User.get_by_username(new_username):
            flash("账号名已存在，未修改", "error")
        else:
            User.update_username(int(user["id"]), new_username)
            flash(f"管理员账号名已修改为：{new_username}", "success")

    # 密码（模板未提供旧密码字段，已登录会话内直接更新）
    new_password = request.form.get("new_password", "")
    if new_password and len(new_password) >= 6 and user:
        User.update_password(int(user["id"]), new_password)
        (Path(DATA_DIR) / ".initial_admin_password").unlink(missing_ok=True)
        flash("密码已修改", "success")

    # 头像上传
    file = request.files.get("avatar_file")
    if file and file.filename:
        _save_avatar(file)

    # OTP：只有完整设置表单或提交了 OTP 相关字段时才处理，避免局部表单误关
    otp_form = full_form or any(
        key in request.form for key in ("otp_enabled", "otp_secret", "otp_confirm_code", "otp_rotate")
    )
    want = str(request.form.get("otp_enabled", "")).strip().lower() in {"1", "on", "true", "yes"}
    current = otp.enabled()
    new_secret = (request.form.get("otp_secret") or "").strip().upper()
    confirm = (request.form.get("otp_confirm_code") or "").strip()
    if otp_form and want and not current:
        if new_secret and otp.verify(new_secret, confirm):
            codes, hashes = otp.gen_recovery_codes()
            settings.set_many({
                "otp_enabled": "1", "otp_secret": new_secret,
                "otp_recovery_codes": json.dumps(hashes),
            })
            session["_otp_new_codes"] = codes
            flash("OTP 双重验证已启用，请立即保存恢复码", "success")
        else:
            flash("OTP 启用失败：请先生成二维码扫码，再输入验证码确认", "error")
    elif otp_form and not want and otp.configured():
        otp.reset()
        flash("OTP 双重验证已关闭", "success")
    elif otp_form and want and current and request.form.get("otp_rotate") and new_secret:
        if otp.verify(new_secret, confirm):
            codes, hashes = otp.gen_recovery_codes()
            settings.set_many({"otp_secret": new_secret, "otp_recovery_codes": json.dumps(hashes)})
            session["_otp_new_codes"] = codes
            flash("OTP 已重新绑定，恢复码已更新", "success")
        else:
            flash("重新绑定失败：验证码不正确", "error")

    if request.form.get("test_email"):
        target = (request.form.get("notify_email") or "").strip() or (request.form.get("contact_email") or "").strip()
        ok, message = notify.send(
            target,
            f"[{settings.get_str('blog_name', 'Blog')}] SMTP 测试邮件",
            f"SMTP 配置测试\n服务器：{request.form.get('smtp_host', '')}:{request.form.get('smtp_port', '')}\n"
            f"发件账号：{request.form.get('smtp_user', '')}\n收件人：{target}",
        )
        if ok:
            flash(f"测试邮件已发送（{target}）", "success")
        else:
            flash(message, "error")

    flash("设置已保存", "success")
    # 设置可能影响前台 HTML（首页一言、导航、统计代码等），统一清页面缓存
    from services import page_cache
    page_cache.clear_all()
    return redirect(url_for("admin_settings"))


@LOGIN
def admin_settings_save():
    return _save_settings()


def _save_avatar(file) -> None:
    from PIL import Image

    try:
        img = Image.open(file.stream)
        img = img.convert("RGB")
        w, h = img.size
        size = max(1, min(w, h))
        left, top = (w - size) // 2, (h - size) // 2
        img = img.crop((left, top, left + size, top + size)).resize((144, 144), Image.LANCZOS)
        folder = Path(UPLOADS_DIR) / "avatar"
        folder.mkdir(parents=True, exist_ok=True)
        img.save(folder / "avatar.jpg", "JPEG", quality=85)
        settings.set_value("avatar", "/uploads/avatar/avatar.jpg")
        flash("头像已更新", "success")
    except Exception:
        flash("头像不是有效的图片", "error")


@LOGIN
def admin_settings_wm_refresh():
    return jsonify({"state": "idle"})


@LOGIN
def admin_settings_test_email():
    target = (request.form.get("notify_email") or "").strip() or (request.form.get("contact_email") or "").strip()
    ok, message = notify.send(
        target,
        f"[{settings.get_str('blog_name', 'Blog')}] SMTP 测试邮件",
        "收到本邮件说明 SMTP 配置可用。",
    )
    return jsonify({"ok": ok, "msg": message})


# ── 数据管理 ──────────────────────────────────────────
@LOGIN
def admin_export():
    stats = {}
    for table in ("posts", "projects", "links", "comments", "timeline", "categories", "settings"):
        stats[table] = int(db.scalar(f"SELECT COUNT(*) FROM {table}", (), 0))
    return render_template("admin/export.html", backups=backup.list_backups(), stats=stats)


@LOGIN
def admin_cache_clear():
    from services import page_cache

    page_cache.clear_all()
    flash("页面缓存已清除", "success")
    return redirect(url_for("admin_export"))


@LOGIN
def admin_export_db_backup():
    name = backup.create_db_backup()
    flash(f"数据库备份成功：{name}", "success")
    return redirect(url_for("admin_export"))


@LOGIN
def admin_export_download(filename: str):
    path = backup.resolve_backup(filename)
    if path is None:
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)


@LOGIN
def admin_export_delete(filename: str):
    if backup.delete_backup(filename):
        flash("备份已删除", "success")
    else:
        flash("备份不存在或无法删除", "error")
    return redirect(url_for("admin_export"))


@LOGIN
def admin_export_json():
    data = backup.export_json()
    return send_file(
        __import__("io").BytesIO(data),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"blog_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )


@LOGIN
def admin_export_markdown():
    data = backup.export_markdown()
    return send_file(
        __import__("io").BytesIO(data),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"blog_markdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
    )


@LOGIN
def admin_export_import_sqlite():
    file = request.files.get("db_file")
    if not file or not file.filename:
        flash("请选择要导入的 SQLite 数据库文件", "error")
        return redirect(url_for("admin_export"))
    if not request.form.get("confirm"):
        flash("请勾选确认后再导入", "error")
        return redirect(url_for("admin_export"))
    tmp = Path(DATA_DIR) / "_import.db"
    file.save(tmp)
    try:
        ok, message = backup.import_sqlite(tmp, keep_users=bool(request.form.get("keep_users")))
    finally:
        tmp.unlink(missing_ok=True)
    flash(message, "success" if ok else "error")
    return redirect(url_for("admin_export"))


@LOGIN
def admin_export_import_sql():
    flash("当前版本请使用 SQLite 备份导入；如需从 MySQL 迁移，可先在旧站导出 JSON 后按文章导入。", "error")
    return redirect(url_for("admin_export"))


# ── 升级 ──────────────────────────────────────────────
@LOGIN
def admin_upgrade():
    from services import upgrade as upgrade_service

    if request.method == "POST":
        ok, message = upgrade_service.start()
        return jsonify({"ok": ok, "message": message})
    return render_template(
        "admin/upgrade.html",
        current_version=VERSION,
        upgrade_check=None,
        upgrade_available=False,
    )


@LOGIN
def admin_upgrade_check():
    from services import upgrade as upgrade_service

    force = request.args.get("force") == "1"
    return jsonify(upgrade_service.check(force=force))


@LOGIN
def admin_upgrade_progress():
    from services import upgrade as upgrade_service

    return jsonify(upgrade_service.status())


@LOGIN
def admin_upgrade_cancel():
    from services import upgrade as upgrade_service

    return jsonify(upgrade_service.cancel())


@LOGIN
def admin_upgrade_reset():
    from services import upgrade as upgrade_service

    return jsonify(upgrade_service.reset())


# ── 注册 ──────────────────────────────────────────────
def register(app) -> None:
    prefix = app.config.get("ADMIN_PREFIX", "/admin")
    rules = [
        ("/admin/dashboard", "admin_dashboard", admin_dashboard, ["GET"]),
        ("/admin/posts", "admin_posts", admin_posts, ["GET"]),
        ("/admin/posts/bulk", "admin_posts_bulk", admin_posts_bulk, ["POST"]),
        ("/admin/posts/new", "admin_post_new", admin_post_new, ["GET", "POST"]),
        ("/admin/posts/<int:post_id>/edit", "admin_post_edit", admin_post_edit, ["GET", "POST"]),
        ("/admin/posts/<int:post_id>/delete", "admin_post_delete", admin_post_delete, ["POST"]),
        ("/admin/posts/<int:post_id>/preview", "admin_post_preview", admin_post_preview, ["GET"]),
        ("/admin/posts/preview-content", "admin_preview_content", admin_preview_content, ["POST"]),
        ("/admin/categories", "admin_categories", admin_categories, ["GET"]),
        ("/admin/categories/new", "admin_category_new", admin_category_new, ["GET", "POST"]),
        ("/admin/categories/<int:cat_id>/edit", "admin_category_edit", admin_category_edit, ["GET", "POST"]),
        ("/admin/categories/<int:cat_id>/delete", "admin_category_delete", admin_category_delete, ["POST"]),
        ("/admin/categories/bulk", "admin_categories_bulk", admin_categories_bulk, ["POST"]),
        ("/admin/projects", "admin_projects", admin_projects, ["GET"]),
        ("/admin/projects/new", "admin_project_new", admin_project_new, ["GET", "POST"]),
        ("/admin/projects/<int:project_id>/edit", "admin_project_edit", admin_project_edit, ["GET", "POST"]),
        ("/admin/projects/<int:project_id>/delete", "admin_project_delete", admin_project_delete, ["POST"]),
        ("/admin/projects/bulk", "admin_projects_bulk", admin_projects_bulk, ["POST"]),
        ("/admin/projects/<int:project_id>/sync", "admin_project_sync", admin_project_sync, ["POST"]),
        ("/admin/projects/sync-all", "admin_projects_sync_all", admin_projects_sync_all, ["POST"]),
        ("/admin/projects/sync-status", "admin_projects_sync_status", admin_projects_sync_status, ["GET"]),
        ("/admin/links", "admin_links", admin_links, ["GET"]),
        ("/admin/links/<int:link_id>/approve", "admin_link_approve", admin_link_approve, ["POST"]),
        ("/admin/links/<int:link_id>/reject", "admin_link_reject", admin_link_reject, ["POST"]),
        ("/admin/links/new", "admin_link_new", admin_link_new, ["GET", "POST"]),
        ("/admin/links/<int:link_id>/edit", "admin_link_edit", admin_link_edit, ["GET", "POST"]),
        ("/admin/links/<int:link_id>/delete", "admin_link_delete", admin_link_delete, ["POST"]),
        ("/admin/links/bulk", "admin_links_bulk", admin_links_bulk, ["POST"]),
        ("/admin/timeline", "admin_timeline", admin_timeline, ["GET"]),
        ("/admin/timeline/new", "admin_timeline_new", admin_timeline_new, ["GET", "POST"]),
        ("/admin/timeline/<int:item_id>/edit", "admin_timeline_edit", admin_timeline_edit, ["GET", "POST"]),
        ("/admin/timeline/<int:item_id>/delete", "admin_timeline_delete", admin_timeline_delete, ["POST"]),
        ("/admin/timeline/bulk", "admin_timeline_bulk", admin_timeline_bulk, ["POST"]),
        ("/admin/comments", "admin_comments", admin_comments, ["GET"]),
        ("/admin/comments/<int:comment_id>/approve", "admin_comment_approve", admin_comment_approve, ["POST"]),
        ("/admin/comments/<int:comment_id>/delete", "admin_comment_delete", admin_comment_delete, ["POST"]),
        ("/admin/comments/bulk", "admin_comments_bulk", admin_comments_bulk, ["POST"]),
        ("/admin/upload/image", "admin_upload_image", admin_upload_image, ["POST"]),
        ("/admin/upload/media", "admin_upload_media", admin_upload_media, ["POST"]),
        ("/admin/upload/file", "admin_upload_file", admin_upload_file, ["POST"]),
        ("/admin/orphans", "admin_orphans", admin_orphans, ["GET"]),
        ("/admin/orphans/clean", "admin_orphan_clean", admin_orphan_clean, ["POST"]),
        ("/admin/status", "admin_status", admin_status, ["GET", "POST"]),
        ("/admin/status/probe", "admin_status_probe", admin_status_probe, ["POST"]),
        ("/admin/status/test-cloud", "admin_status_test_cloud", admin_status_test_cloud, ["POST"]),
        ("/admin/themes", "admin_themes", admin_themes, ["GET", "POST"]),
        ("/admin/settings", "admin_settings", admin_settings, ["GET", "POST"]),
        ("/admin/settings/save", "admin_settings_save", admin_settings_save, ["POST"]),
        ("/admin/settings/wm-refresh", "admin_settings_wm_refresh", admin_settings_wm_refresh, ["GET"]),
        ("/admin/settings/test-email", "admin_settings_test_email", admin_settings_test_email, ["POST"]),
        ("/admin/export", "admin_export", admin_export, ["GET"]),
        ("/admin/cache/clear", "admin_cache_clear", admin_cache_clear, ["POST"]),
        ("/admin/export/db-backup", "admin_export_db_backup", admin_export_db_backup, ["POST"]),
        ("/admin/export/import-sqlite", "admin_export_import_sqlite", admin_export_import_sqlite, ["POST"]),
        ("/admin/export/import-sql", "admin_export_import_sql", admin_export_import_sql, ["POST"]),
        ("/admin/export/download/<filename>", "admin_export_download", admin_export_download, ["GET"]),
        ("/admin/export/delete/<filename>", "admin_export_delete", admin_export_delete, ["POST"]),
        ("/admin/export/json", "admin_export_json", admin_export_json, ["GET"]),
        ("/admin/export/markdown", "admin_export_markdown", admin_export_markdown, ["GET"]),
        ("/admin/upgrade", "admin_upgrade", admin_upgrade, ["GET", "POST"]),
        ("/admin/upgrade/check", "admin_upgrade_check", admin_upgrade_check, ["GET"]),
        ("/admin/upgrade/progress", "admin_upgrade_progress", admin_upgrade_progress, ["GET"]),
        ("/admin/upgrade/cancel", "admin_upgrade_cancel", admin_upgrade_cancel, ["POST"]),
        ("/admin/upgrade/reset", "admin_upgrade_reset", admin_upgrade_reset, ["POST"]),
    ]
    for rule, endpoint, view, methods in rules:
        if prefix != "/admin" and rule.startswith("/admin"):
            rule = prefix + rule[len("/admin"):]
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)
