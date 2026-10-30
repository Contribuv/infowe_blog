"""留存记录插件路由：操作审计 / AI 审计 / 评论留存三合一查看与导出。"""

from __future__ import annotations

import csv
import io
import json

import db
from flask import render_template, request, send_file

from services import auth

PAGE_SIZE = 30

# 三个数据源的列定义：(表, 查询字段, CSV 表头)
TABS = {
    "ops": {
        "label": "操作记录",
        "sql": "SELECT id, action, target, detail, operator, ip, created_at FROM op_logs",
        "headers": ["ID", "操作", "对象", "详情", "操作人", "IP", "时间"],
        "time_col": "created_at",
        "keyword_cols": "action, target, detail, operator, ip",
    },
    "ai": {
        "label": "AI 审计",
        "sql": "SELECT id, action, args, result, ok, created_at FROM ai_audit",
        "headers": ["ID", "动作", "参数", "结果", "成功", "时间"],
        "time_col": "created_at",
        "keyword_cols": "action, args, result",
    },
    "comments": {
        "label": "评论留存",
        # 不过滤 deleted_at：软删除的评论正是本 tab 的核心价值——正文永久可查
        "sql": (
            "SELECT id, author, email, website, ip_text, ip_location, content, status, "
            "deleted_at, created_at"
            " FROM comments WHERE is_ai = 0"
        ),
        "headers": ["ID", "昵称", "邮箱", "主页", "IP", "归属地", "内容", "状态", "删除时间", "评论时间"],
        "time_col": "created_at",
        "keyword_cols": "author, email, website, ip_text, content",
    },
}

STATUS_LABELS = {"approved": "已通过", "pending": "待审核", "rejected": "已拒绝", "spam": "垃圾"}

# 操作记录动作码 → 中文（未收录的原样显示，CSV 导出仍保留英文原码便于检索）
OPS_LABELS = {
    "login.success": "登录成功",
    "login.fail": "登录失败",
    "login.logout": "退出登录",
    "post.edit": "编辑文章",
    "post.trash": "移入回收站",
    "post.restore": "恢复文章",
    "post.purge": "彻底删除",
    "link.delete": "删除友链",
    "comment.approve": "通过评论",
    "comment.delete": "删除评论",
    "settings.save": "保存设置",
}

# AI 审计动作码（即白名单工具名）→ 中文
AI_ACTION_LABELS = {
    "list_posts": "列出文章",
    "search_posts": "搜索文章",
    "get_post": "读取文章",
    "list_comments": "列出评论",
    "list_links": "列出友链",
    "list_categories": "列出分类",
    "list_projects": "列出项目",
    "get_project": "读取项目",
    "get_stats": "站点统计",
    "create_post": "创建文章",
    "update_post": "修改文章",
    "delete_post": "删除文章",
    "create_category": "新建分类",
    "update_category": "修改分类",
    "delete_category": "删除分类",
    "approve_comment": "通过评论",
    "reject_comment": "拒绝评论",
    "delete_comment": "删除评论",
    "reply_comment": "回复评论",
    "add_link": "新增友链",
    "approve_link": "通过友链",
    "reject_link": "拒绝友链",
    "delete_link": "删除友链",
    "create_project": "新建项目",
    "update_project": "修改项目",
    "delete_project": "删除项目",
    "sync_project": "同步项目",
}


def _tab_key() -> str:
    key = request.args.get("tab", "ops")
    return key if key in TABS else "ops"


def _human_summary(obj) -> str:
    """把 JSON 对象压成「键: 值, 键: 值」的人话摘要，比原样 JSON 更好扫读。"""
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            parts.append(f"{k}: {v}")
        text = ", ".join(parts)
    else:
        text = json.dumps(obj, ensure_ascii=False)
    return text if len(text) <= 60 else text[:60] + "…"


def _fmt_ai_row(row: dict) -> dict:
    """AI 审计的 args/result 是 JSON 字符串：解析成缩进文本供折叠展示，并给单行摘要。

    解析失败（非 JSON 的历史脏数据）时保持原样，由模板直出兜底。
    """
    for col in ("args", "result"):
        raw = row.get(col)
        pretty, summary = "", ""
        if raw:
            try:
                obj = json.loads(raw)
            except Exception:
                obj = None
            if obj is not None:
                pretty = json.dumps(obj, ensure_ascii=False, indent=2)
                summary = _human_summary(obj)
        row[col + "_fmt"] = pretty
        row[col + "_summary"] = summary
    return row


def _where(key: str) -> tuple[list[str], list]:
    """按日期范围与关键词生成筛选条件列表（不含 WHERE 关键字）与参数。"""
    spec = TABS[key]
    clauses: list[str] = []
    params: list = []
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    tcol = spec["time_col"]
    if start:
        clauses.append(f"{tcol} >= ?")
        params.append(start + " 00:00:00")
    if end:
        clauses.append(f"{tcol} <= ?")
        params.append(end + " 23:59:59")
    q = (request.args.get("q") or "").strip()
    if q:
        likes = " OR ".join(f"{c} LIKE ?" for c in spec["keyword_cols"].split(", "))
        clauses.append(f"({likes})")
        params.extend([f"%{q}%"] * len(spec["keyword_cols"].split(", ")))
    return clauses, params


def _from_where(key: str) -> tuple[str, str, list]:
    """拆出 SELECT 列与 FROM 片段（含基础条件 + 筛选 WHERE），并返回参数。

    comments 的 SQL 自带 WHERE is_ai = 0，筛选条件必须以 AND 接续；
    op_logs / ai_audit 无基础条件，直接 WHERE 起头。此前统一拼 WHERE
    会在评论 tab 出现双 WHERE 语法错误，被误判成「表不存在」。
    """
    spec = TABS[key]
    select_cols, frm = spec["sql"].split(" FROM ", 1)
    clauses, params = _where(key)
    if clauses:
        frm += (" AND " if " WHERE " in frm else " WHERE ") + " AND ".join(clauses)
    return select_cols, frm, params


def register(app) -> None:
    prefix = app.config.get("ADMIN_PREFIX", "/admin")

    @auth.admin_required
    def retention_index():
        key = _tab_key()
        spec = TABS[key]
        select_cols, frm, params = _from_where(key)
        page = max(1, request.args.get("page", 1, type=int) or 1)
        rows: list = []
        total = 0
        # ai_audit 是 AI 助手插件的表，该插件从未启用时表不存在，兜底显示空列表
        exists = True
        try:
            total = int(db.scalar(f"SELECT COUNT(*) FROM {frm}", params, 0) or 0)
        except Exception:
            exists = False
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)
        if exists:
            rows = db.query(
                f"{select_cols} FROM {frm} ORDER BY {spec['time_col']} DESC, id DESC LIMIT ? OFFSET ?",
                params + [PAGE_SIZE, (page - 1) * PAGE_SIZE],
            )
        rows = [dict(r) for r in rows]
        if key == "ai":
            rows = [_fmt_ai_row(r) for r in rows]
        # 动作码转中文展示（未收录的原样显示）
        labels = OPS_LABELS if key == "ops" else AI_ACTION_LABELS if key == "ai" else {}
        for r in rows:
            code = r.get("action") or ""
            r["action_label"] = labels.get(code, code)
        return render_template(
            "retention/index.html",
            tabs=TABS,
            active=key,
            rows=rows,
            page=page,
            total_pages=total_pages,
            total=total,
            args=request.args,
            status_labels=STATUS_LABELS,
            exists=exists,
        )

    @auth.admin_required
    def retention_export():
        key = _tab_key()
        spec = TABS[key]
        select_cols, frm, params = _from_where(key)
        rows = db.query(f"{select_cols} FROM {frm} ORDER BY {spec['time_col']} DESC, id DESC LIMIT 50000", params)
        buf = io.StringIO()
        # utf-8-sig 带 BOM，Excel 打开中文不乱码
        writer = csv.writer(buf)
        writer.writerow(spec["headers"])
        for row in rows:
            writer.writerow([_cell(key, col, row[col]) for col in row.keys()])
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            io.BytesIO(buf.getvalue().encode("utf-8-sig")),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"retention_{key}_{stamp}.csv",
        )

    app.add_url_rule(prefix + "/plugins/retention", "admin_plugin_retention", retention_index, methods=["GET"])
    app.add_url_rule(
        prefix + "/plugins/retention/export", "admin_plugin_retention_export", retention_export, methods=["GET"]
    )


def _cell(key: str, col: str, value) -> str:
    """CSV/展示用的取值：状态转中文、成功标志转文字。"""
    if value is None:
        return ""
    if key == "comments" and col == "status":
        return STATUS_LABELS.get(str(value), str(value))
    if key == "ai" and col == "ok":
        return "是" if value else "否"
    return str(value)
