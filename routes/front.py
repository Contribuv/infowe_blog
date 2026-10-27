"""前台路由。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from flask import (
    abort, flash, jsonify, make_response, redirect, render_template, request,
    Response, url_for,
)
from markupsafe import escape

import db
from models import Category, Comment, Link, Post, Project, Timeline
from services import auth, avatar, comments as comments_service, ip_location
from services import lang, markdown, project_sync, settings, site_url, status, theme, upload
from services import readers as readers_service
from services import sidebar as sidebar_service


def _decorate_categories(posts: list[dict]) -> list[dict]:
    names = Category.name_map()
    for post in posts:
        cid = post.get("category_id")
        post["category_name"] = names.get(int(cid), "") if cid else ""
    return posts


def _group_by_year(posts: list[dict]) -> list[tuple[str, list[dict]]]:
    """按年份分组；posts 已按时间倒序，遇到新年份就开新组。"""
    groups: list[tuple[str, list[dict]]] = []
    for post in posts:
        year = str(post.get("created_at") or "")[:4] or "未标注"
        if not groups or groups[-1][0] != year:
            groups.append((year, []))
        groups[-1][1].append(post)
    return groups


def _sidebar_data() -> dict | None:
    """只有多栏布局才查询侧栏，单栏/双栏不增加额外查询。"""
    if settings.get_str("post_layout", "single") != "multi":
        return None
    return sidebar_service.data()


def _comment_pager(pager: dict) -> dict:
    """把模型层分页信息转成模板可直接渲染的链接结构。"""
    total_pages = int(pager.get("total_pages") or 1)
    page = int(pager.get("page") or 1)
    if total_pages <= 1:
        return {"total_pages": 1, "page": 1, "pages": [], "prev": "", "next": ""}

    def url(target: int) -> str:
        args = request.args.to_dict(flat=True)
        args.pop("cpage", None)
        if target > 1:
            args["cpage"] = str(target)
        query = urlencode(args)
        return request.path + ("?" + query if query else "") + "#comments"

    pages: list[dict] = []
    for item in range(1, total_pages + 1):
        if item == 1 or item == total_pages or abs(item - page) <= 2:
            pages.append({"num": item, "url": url(item), "current": item == page, "ellipsis": False})
        elif abs(item - page) == 3:
            pages.append({"num": 0, "url": "", "current": False, "ellipsis": True})
    return {
        "total_pages": total_pages,
        "page": page,
        "pages": pages,
        "prev": url(page - 1) if page > 1 else "",
        "next": url(page + 1) if page < total_pages else "",
    }


def _load_comments(post_id: int | None, project_id: int | None, include_private: bool, my_comments: dict):
    """按后台「评论每页条数」分页读取评论，返回 (列表, 总数, 分页信息)。"""
    per_page = settings.get_int("comments_per_page", 10)
    page = request.args.get("cpage", 1, type=int) or 1
    comment_list, comment_total, pager = Comment.load(
        post_id, project_id, include_private, my_comments, page, per_page
    )
    return comment_list, comment_total, _comment_pager(pager)


def index():
    tag = (request.args.get("tag") or "").strip()
    if tag:
        # 旧链接 /?tag=x → /tag/x
        page = request.args.get("page", 1, type=int) or 1
        if page > 1:
            return redirect(url_for("tag_page", tag=tag, page=page), code=301)
        return redirect(url_for("tag_page", tag=tag), code=301)
    search = (request.args.get("q") or "").strip()
    if search:
        # 旧链接 /?q=x → /search/x
        return redirect(url_for("search_page", q=search), code=301)
    home_count = settings.get_int("home_posts_count", 6) or 6

    featured = Post.featured(3)
    posts = Post.home_posts(home_count, True)
    _, total = Post.load("published", None, None, None, 1)

    posts = _decorate_categories(posts)
    featured = _decorate_categories(featured)
    home_links = Link.load("approved")
    return render_template(
        "index.html",
        posts=posts,
        featured=featured,
        links=home_links,
        current_tag="",
        search_query="",
        page=1,
        total_pages=1,
        total=total,
        total_categories=int(db.scalar("SELECT COUNT(*) FROM categories", (), 0)),
        sidebar=_sidebar_data(),
    )


def _list_page(page: int, per_page: int):
    page = max(1, int(page or 1))
    _, total = Post.load("published", None, None, None, 1, per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    return page, total_pages


def tag_page(tag: str):
    per_page = settings.get_int("posts_per_page", 20) or 20
    page = request.args.get("page", 1, type=int) or 1
    posts, total = Post.load("published", tag, None, None, page, per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), total_pages)
    posts, total = Post.load("published", tag, None, None, page, per_page)
    posts = _decorate_categories(posts)
    return render_template(
        "index.html",
        posts=posts,
        featured=[],
        links=[],
        current_tag=tag,
        search_query="",
        page=page,
        total_pages=total_pages,
        total=total,
        total_categories=int(db.scalar("SELECT COUNT(*) FROM categories", (), 0)),
    )


def search_page(q: str):
    per_page = settings.get_int("posts_per_page", 20) or 20
    page = request.args.get("page", 1, type=int) or 1
    posts, total = Post.load("published", None, q, None, page, per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), total_pages)
    posts, total = Post.load("published", None, q, None, page, per_page)
    posts = _decorate_categories(posts)
    return render_template(
        "index.html",
        posts=posts,
        featured=[],
        links=[],
        current_tag="",
        search_query=q,
        page=page,
        total_pages=total_pages,
        total=total,
        total_categories=int(db.scalar("SELECT COUNT(*) FROM categories", (), 0)),
    )


def archive_page(year: int):
    per_page = settings.get_int("posts_per_page", 20) or 20
    page = request.args.get("page", 1, type=int) or 1
    posts, total = Post.load("published", None, None, str(year), page, per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), total_pages)
    posts, total = Post.load("published", None, None, str(year), page, per_page)
    posts = _decorate_categories(posts)
    return render_template(
        "posts.html",
        posts=posts,
        groups=None,
        is_miles=False,
        total=total,
        page=page,
        total_pages=total_pages,
        filtered=True,
        all_tags=Post.all_tags(),
        all_years=Post.all_years(),
        active_tag="",
        active_year=str(year),
        sidebar=_sidebar_data(),
    )


def posts_page():
    if not settings.bool_of("nav_posts", True):
        abort(404)
    tag = (request.args.get("tag") or "").strip() or None
    year = (request.args.get("year") or "").strip() or None
    page = request.args.get("page", 1, type=int) or 1
    if tag:
        return redirect(url_for("tag_page", tag=tag, page=page) if page > 1 else url_for("tag_page", tag=tag), code=301)
    if year:
        if year.isdigit():
            return redirect(
                url_for("archive_page", year=int(year), page=page) if page > 1 else url_for("archive_page", year=int(year)),
                code=301,
            )
        year = None
    per_page = settings.get_int("posts_per_page", 20) or 20
    page = max(1, page)

    _, total = Post.load("published", tag, None, year, 1, per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    posts, _ = Post.load("published", tag, None, year, page, per_page)
    posts = _decorate_categories(posts)

    return render_template(
        "posts.html",
        posts=posts,
        groups=_group_by_year(posts),
        is_miles=True,
        year_counts=Post.year_counts(),
        total=total,
        page=page,
        total_pages=total_pages,
        filtered=bool(tag or year),
        all_tags=Post.all_tags(),
        all_years=Post.all_years(),
        active_tag=tag or "",
        active_year=year or "",
        sidebar=_sidebar_data(),
    )


def post_detail(post_id: int):
    post = Post.get(post_id)
    if not post or post["status"] not in {"published", "hidden"}:
        abort(404)
    category = Category.get(int(post["category_id"])) if post.get("category_id") else None
    post["category_name"] = category["name"] if category else ""
    post["word_count"] = len("".join((post.get("content") or "").split()))

    content, toc = markdown.render_post(post.get("content") or "")

    share = (post.get("cover") or "").strip() or upload.first_url(post.get("content") or "")
    if share.startswith("/uploads/"):
        from urllib.parse import quote

        og_path = "/share-thumb/" + quote(share[len("/uploads/"):])
    elif share:
        og_path = share
    else:
        og_path = "/static/images/og-image.png"

    related = Post.related(post_id, post.get("tags") or [])
    enabled = comments_service.open_comments()
    is_admin = auth.is_admin()
    commenter = comments_service.commenter()
    my_comments = commenter.get("my_comments") if isinstance(commenter.get("my_comments"), dict) else {}
    if enabled:
        comment_list, comment_total, comment_pager = _load_comments(
            post_id, None, is_admin, my_comments
        )
    else:
        comment_list, comment_total = [], 0
        comment_pager = _comment_pager({})
    my_pending = 0 if is_admin else Comment.count_pending(comment_list)

    side_posts, _ = Post.load("published", None, None, None, 1, 12)
    return render_template(
        "post.html",
        post=post,
        content=content,
        toc=toc,
        related=related,
        comments=comment_list,
        comment_total=comment_total,
        comment_pager=comment_pager,
        prev_post=Post.adjacent(post["created_at"], True),
        next_post=Post.adjacent(post["created_at"], False),
        comments_enabled=enabled,
        og_image_path=og_path,
        commenter=commenter,
        is_admin=is_admin,
        admin_avatar=avatar.admin_url(40) if is_admin else "",
        my_pending=my_pending,
        side_posts=side_posts,
    )


def post_view(post_id: int):
    if not Post.get(post_id):
        abort(404)
    comments_service.count_view(post_id)
    return ("", 204)


def _apply_commenter_cookie(response, data: dict | None):
    if data:
        response.set_cookie(
            "blog_commenter",
            json.dumps(data, ensure_ascii=False),
            max_age=30 * 24 * 3600,
            path="/",
            httponly=True,
            samesite="Lax",
        )
    return response


def post_comment(post_id: int):
    if not comments_service.open_comments():
        abort(403)
    post = Post.get(post_id)
    if not post or post["status"] not in {"published", "hidden"}:
        abort(404)
    result = comments_service.submit(post=post)
    if result.get("error"):
        flash(result["error"], "error")
    else:
        flash(result.get("message", "评论已提交"), "success")
    return _apply_commenter_cookie(redirect(result["url"]), result.get("commenter"))


def comment_upload():
    if not comments_service.open_comments() or not comments_service.image_upload_on():
        return jsonify({"error": "评论图片上传已关闭"}), 403
    from services import ratelimit

    ip = comments_service.request_ip()
    # 匿名接口：限频 15 秒 1 张、单 IP 每天 30 张，避免被拿来刷磁盘
    if not ratelimit.allow("upload_burst", ip, 15, 1) or not ratelimit.allow("upload_day", ip, 86400, 30):
        return jsonify({"error": "上传太频繁，请稍后再试"}), 429
    file = request.files.get("image")
    url, error = upload.save(
        file,
        {".jpg", ".jpeg", ".png", ".gif", ".webp"},
        max_bytes=8 * 1024 * 1024,
        sub_dir=datetime.now().strftime("comment/%Y/%m"),
        randomize=True,
    )
    if error:
        return jsonify({"error": error}), 400
    ratelimit.touch("upload_burst", ip)
    ratelimit.touch("upload_day", ip)
    return jsonify({"url": url})


def tags():
    posts, total = Post.load("published", None, None, None, 1, 99999)
    names = Category.name_map()
    buckets: dict[str, list[dict]] = {}
    for post in posts:
        post["category_name"] = names.get(int(post["category_id"]), "") if post.get("category_id") else ""
        for tag in post.get("tags") or []:
            buckets.setdefault(str(tag), []).append(post)
    keys = sorted(buckets, key=lambda k: (-len(buckets[k]), k))
    groups = [(k, buckets[k]) for k in keys]
    return render_template("tags.html", tag_groups=groups, post_total=total)


def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return redirect(url_for("index"))
    return redirect(url_for("search_page", q=q), code=301)


def about():
    if not settings.bool_of("nav_about", True):
        abort(404)
    skills = settings.json_list("skills", [])
    _, post_total = Post.load("published", None, None, None, 1, 1)
    expiry, services, _ = status.snapshot()
    return render_template(
        "about.html",
        skills=skills,
        expiry=expiry,
        services=services,
        about_intro=settings.get_str("about_intro", ""),
        author=settings.get_str("author", ""),
        avatar=avatar.admin_url(200),
        github=settings.get_str("github_username", "") or settings.get_str("social_github", ""),
        timeline=Timeline.load(),
        post_total=post_total,
        category_total=int(db.scalar("SELECT COUNT(*) FROM categories", (), 0)),
    )


def circle():
    if not settings.bool_of("nav_circle", True):
        abort(404)
    from services import feeds

    page = max(1, request.args.get("page", 1, type=int) or 1)
    items, total, stats = feeds.aggregate(page)
    total_pages = max(1, (total + feeds.PER_PAGE - 1) // feeds.PER_PAGE)
    page = min(page, total_pages)

    if total_pages <= 7:
        pages = list(range(1, total_pages + 1))
    else:
        marks = sorted({1, total_pages, page, page - 1, page + 1, page - 2, page + 2})
        pages = []
        prev = 0
        for num in marks:
            if not 1 <= num <= total_pages:
                continue
            if prev and num - prev > 1:
                pages.append("...")
            pages.append(num)
            prev = num

    return render_template(
        "circle.html",
        items=items,
        total=total,
        stats=stats,
        page=page,
        total_pages=total_pages,
        pages=pages,
    )


def links_page():
    avatar_cfg = settings.get_str("avatar", "").strip()
    if avatar_cfg and not avatar_cfg.startswith("http"):
        avatar_url = site_url.base() + avatar_cfg
    elif avatar_cfg:
        avatar_url = avatar_cfg
    else:
        avatar_url = site_url.base() + "/static/images/favicon.svg"
    return render_template(
        "links.html",
        links=Link.load("approved"),
        site_url=site_url.base(),
        avatar_url=avatar_url,
    )


def links_apply():
    if not settings.bool_of("nav_links", True):
        abort(404)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        url = (request.form.get("url") or "").strip()
        description = (request.form.get("description") or "").strip()
        avatar_url = (request.form.get("avatar") or "").strip()
        if not name or not url:
            flash("请填写名称和网址", "error")
            return render_template("links_apply.html", form=request.form)
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        email = (request.form.get("email") or "").strip()
        rss = (request.form.get("rss") or "").strip()
        link_id = Link.save(
            {"name": name, "url": url, "description": description, "avatar": avatar_url, "rss": rss, "sort_order": 0},
            None,
            "pending",
        )
        if email:
            db.execute("UPDATE links SET email=? WHERE id=?", (email, link_id))
        try:
            from services import hooks
            hooks.emit("link.applied", {"id": link_id, "name": name, "url": url, "email": email})
        except Exception:
            pass
        return redirect(url_for("links_apply_success"))
    return render_template("links_apply.html", form=None)


def links_apply_success():
    if not settings.bool_of("nav_links", True):
        abort(404)
    reviewer = settings.get_str("author", "").strip() or settings.get_str("blog_name", "").strip() or "博主"
    return render_template("links_apply_success.html", reviewer=reviewer)


def status_page():
    # 状态内容已并入关于页，保留旧地址做 301，避免外部链接 404
    return redirect(url_for("about") + "#status", code=301)


def projects_page():
    if not settings.bool_of("nav_projects", True):
        abort(404)
    project_sync.auto_sync()
    projects = [lang.decorate(p) for p in Project.load()]
    return render_template("projects.html", projects=projects, languages=lang.tally(projects))


def project_detail(project_id: int):
    if not settings.bool_of("nav_projects", True):
        abort(404)
    project = Project.get(project_id)
    if not project:
        abort(404)
    project = lang.decorate(project)

    from services import github

    repo = (project.get("github_repo") or "").strip() or (github.parse_repo(project.get("url", "")) or "")
    cached = github.snapshot(repo) if repo else None
    if cached is not None:
        gh = {**cached, "cached": True}
    else:
        gh = {"gh": None, "readme": "", "branch": "", "ts": 0, "error": "", "cached": False}
    gh["age_text"] = _age_text(float(gh.get("ts") or 0))
    toc = markdown.toc_from_html(str(gh.get("readme") or ""))

    enabled = comments_service.open_comments()
    is_admin = auth.is_admin()
    commenter = comments_service.commenter()
    my_comments = commenter.get("my_comments") if isinstance(commenter.get("my_comments"), dict) else {}
    if enabled:
        comment_list, comment_total, comment_pager = _load_comments(
            None, project_id, is_admin, my_comments
        )
    else:
        comment_list, comment_total = [], 0
        comment_pager = _comment_pager({})
    return render_template(
        "project_detail.html",
        project=project,
        gh=gh,
        toc=toc,
        comments=comment_list,
        comment_total=comment_total,
        comment_pager=comment_pager,
        comments_enabled=enabled,
        commenter=commenter,
        is_admin=is_admin,
        admin_avatar=avatar.admin_url(40) if is_admin else "",
        my_pending=0 if is_admin else Comment.count_pending(comment_list),
    )


def project_comment(project_id: int):
    if not comments_service.open_comments():
        abort(403)
    project = Project.get(project_id)
    if not project:
        abort(404)
    result = comments_service.submit(project=project)
    if result.get("error"):
        flash(result["error"], "error")
    else:
        flash(result.get("message", "评论已提交"), "success")
    return _apply_commenter_cookie(redirect(result["url"]), result.get("commenter"))


def _age_text(ts: float) -> str:
    if ts <= 0:
        return ""
    diff = max(0, int(datetime.now().timestamp() - ts))
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{diff // 60} 分钟前"
    if diff < 86400:
        return f"{diff // 3600} 小时前"
    if diff < 86400 * 30:
        return f"{diff // 86400} 天前"
    if diff < 86400 * 365:
        return f"{diff // (86400 * 30)} 个月前"
    return f"{diff // (86400 * 365)} 年前"


def rss_feed():
    from datetime import timedelta, timezone
    from email.utils import format_datetime

    from models.base import strip_markdown

    cst = timezone(timedelta(hours=8))

    def rss_date(value: str) -> str:
        try:
            return format_datetime(
                datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=cst)
            )
        except (ValueError, TypeError):
            return format_datetime(datetime.now(cst))

    posts, _ = Post.load("published", None, None, None, 1, 20)
    base = site_url.base()
    items = []
    for post in posts:
        link = f"{base}/post/{post['id']}"
        description = post.get("excerpt") or strip_markdown(post.get("content") or "")[:200]
        items.append(
            "<item>"
            f"<title>{escape(post['title'])}</title>"
            f"<link>{escape(link)}</link>"
            f"<guid isPermaLink=\"true\">{escape(link)}</guid>"
            f"<description>{escape(description)}</description>"
            f"<pubDate>{rss_date(post.get('created_at') or '')}</pubDate>"
            "</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{escape(settings.get_str('blog_name', '博客'))}</title>"
        f"<link>{escape(base)}</link>"
        f"<description>{escape(settings.get_str('blog_subtitle', ''))}</description>"
        f"<language>zh-CN</language>"
        f"<lastBuildDate>{format_datetime(datetime.now(cst))}</lastBuildDate>"
        f'<atom:link href="{escape(base)}/feed.xml" rel="self" type="application/rss+xml"/>'
        + "".join(items)
        + "</channel></rss>"
    )
    return Response(xml, mimetype="application/rss+xml")


def readers_page():
    data = readers_service.rank(request.args.get("page", 1, type=int) or 1)
    picked = readers_service.picked(1, per_page=6)
    data["picked_items"] = picked["items"]
    data["picked_total"] = picked["total"]
    data["stats"]["picked"] = picked["total"]
    return render_template("readers.html", **data)


def interactions_page():
    # 「互动」已并入留言榜单，旧地址保留跳转
    return redirect(url_for("readers_page") + "#picked", code=301)


def register(app) -> None:
    rules = [
        ("/", "index", index, ["GET"]),
        ("/tag/<tag>", "tag_page", tag_page, ["GET"]),
        ("/search/<path:q>", "search_page", search_page, ["GET"]),
        ("/archive/<int:year>", "archive_page", archive_page, ["GET"]),
        ("/posts", "posts_page", posts_page, ["GET"]),
        ("/post/<int:post_id>", "post_detail", post_detail, ["GET"]),
        ("/post/<int:post_id>/view", "post_view", post_view, ["POST"]),
        ("/post/<int:post_id>/comment", "post_comment", post_comment, ["POST"]),
        ("/comment/upload", "comment_upload", comment_upload, ["POST"]),
        ("/tags", "tags", tags, ["GET"]),
        ("/search", "search", search, ["GET"]),
        ("/about", "about", about, ["GET"]),
        ("/circle", "circle", circle, ["GET"]),
        ("/readers", "readers_page", readers_page, ["GET"]),
        ("/interactions", "interactions_page", interactions_page, ["GET"]),
        ("/links", "links_page", links_page, ["GET"]),
        ("/links/apply", "links_apply", links_apply, ["GET", "POST"]),
        ("/links/apply/success", "links_apply_success", links_apply_success, ["GET"]),
        ("/status", "status_page", status_page, ["GET"]),
        ("/projects", "projects_page", projects_page, ["GET"]),
        ("/projects/<int:project_id>", "project_detail", project_detail, ["GET"]),
        ("/projects/<int:project_id>/comment", "project_comment", project_comment, ["POST"]),
        ("/feed.xml", "rss_feed", rss_feed, ["GET"]),
    ]
    for rule, endpoint, view, methods in rules:
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)
