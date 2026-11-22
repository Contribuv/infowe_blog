"""「我的概览」个人中心数据：统计格子 / 活跃度热力图 / 一周分布 / 最近发言 / 我的回复 / 我的@。

按 email_hash 归集（读者登录或评论 Cookie 同一哈希口径），博主视角按 is_owner 归集。
只取本人数据：私密评论不进统计。待审核评论仅在「最近发言」里给本人露出并标注状态
（与前台靠 my_comments Cookie 显示自己待审核评论的口径一致），统计数字仍只算已通过。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

import db
from services import avatar

WEEKS = 26          # 热力图跨 26 周（约半年，与截图一致）
RECENT_LIMIT = 8


def _public_rows(email_hash: str, include_owner: bool = False, owner_only: bool = False,
                 include_pending: bool = False) -> list[dict]:
    """公开评论行。

    owner_only 为博主视角：按 is_owner 归集，不依赖某个邮箱哈希——
    博主换过邮箱 / notify_email 与历史评论邮箱不一致时，按哈希统计会全是 0，
    看起来就像「没识别到身份」。

    include_pending 只用于「我自己」的归集（调用方必须已经限定成本人哈希 /
    is_owner），这样刚提交、还没过审的评论能在抽屉里看到并标「待审核」，
    与前台靠 my_comments Cookie 露出自己待审核评论的口径一致；
    统计数字仍只算 approved，不会把待审核算进「评论数」。
    """
    if owner_only:
        who = "c.is_owner = 1"
        params: tuple = ()
    elif include_owner:
        if not email_hash:
            return []
        who = "c.email_hash = ?"
        params = (email_hash,)
    else:
        if not email_hash:
            return []
        who = "c.email_hash = ? AND c.is_owner = 0"
        params = (email_hash,)
    status_clause = "c.status IN ('approved','pending')" if include_pending else "c.status = 'approved'"
    rows = db.query(
        "SELECT c.id, c.author, c.email_hash, c.qq, c.website, c.content, c.status, c.created_at, "
        "c.post_id, c.project_id, c.parent_id, "
        "p.title AS post_title, pj.name AS project_name "
        "FROM comments c "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        "WHERE " + who + " AND " + status_clause + " AND c.is_private = 0 "
        "AND c.is_ai = 0 AND c.deleted_at IS NULL "
        "ORDER BY c.created_at DESC, c.id DESC",
        params,
    )
    return [dict(r) for r in rows]


def _parse_day(value: str) -> str:
    """'YYYY-MM-DD HH:MM:SS' -> 'YYYY-MM-DD'，解析失败返回空串。"""
    text = str(value or "")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "")).date().isoformat()
    except (ValueError, TypeError):
        return ""


def _plain(text: str, limit: int = 100) -> str:
    import re
    value = str(text or "")
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"```.*?```", " ", value, flags=re.S)
    value = re.sub(r"[`*_>#~]", "", value)
    value = " ".join(value.split())
    if limit and len(value) > limit:
        return value[:limit].rstrip() + "…"
    return value


def _source(row: dict) -> tuple[str, str]:
    if row.get("post_id"):
        return str(row.get("post_title") or "文章"), f"/post/{row['post_id']}#comment-{row['id']}"
    if row.get("project_id"):
        return str(row.get("project_name") or "项目"), f"/projects/{row['project_id']}#comment-{row['id']}"
    return "", ""


def _streak(days: set[str]) -> int:
    """连续发言天数：从今天或昨天往前数。"""
    if not days:
        return 0
    today = datetime.now().date()
    cursor = today if today.isoformat() in days else today - timedelta(days=1)
    count = 0
    while cursor.isoformat() in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def _like_count(email_hash: str, comment_ids: list[int]) -> int:
    """我收到的点赞数：我的评论被点赞的总次数（不含「不喜欢」）。"""
    if not email_hash or not comment_ids:
        return 0
    marks = ",".join("?" * len(comment_ids))
    return int(db.scalar(
        f"SELECT COUNT(*) FROM comment_likes WHERE comment_id IN ({marks}) AND kind = 1",
        tuple(comment_ids), 0) or 0)


def liked_comment_ids(voter_hash: str, comment_ids: list[int], kind: int = 1) -> set[int]:
    """我投过票的评论 id 集合（kind=1 点赞 / -1 不喜欢），供前端渲染已选态。"""
    if not voter_hash or not comment_ids:
        return set()
    marks = ",".join("?" * len(comment_ids))
    rows = db.query(
        f"SELECT comment_id FROM comment_likes WHERE voter_hash=? AND kind=? "
        f"AND comment_id IN ({marks})",
        (voter_hash, int(kind), *comment_ids),
    )
    return {int(r["comment_id"]) for r in rows}


def likes_map(comment_ids: list[int], kind: int = 1) -> dict[int, int]:
    """批量取评论票数 {comment_id: count}。kind=1 点赞 / -1 不喜欢。"""
    if not comment_ids:
        return {}
    marks = ",".join("?" * len(comment_ids))
    rows = db.query(
        f"SELECT comment_id, COUNT(*) AS n FROM comment_likes "
        f"WHERE comment_id IN ({marks}) AND kind = ? GROUP BY comment_id",
        (*comment_ids, int(kind)),
    )
    return {int(r["comment_id"]): int(r["n"]) for r in rows}


def toggle_vote(comment_id: int, voter_hash: str, kind: int = 1) -> dict:
    """点赞 / 不喜欢 / 取消，返回 {liked, disliked, likes, dislikes}。

    同一身份对同一条评论只能有一票：再点同一边是取消，点另一边是改票。
    """
    kind = -1 if int(kind) < 0 else 1
    if not comment_id or not voter_hash:
        return {"liked": False, "disliked": False, "likes": 0, "dislikes": 0,
                "error": "无法识别身份"}
    row = db.one(
        "SELECT id, kind FROM comment_likes WHERE comment_id=? AND voter_hash=?",
        (comment_id, voter_hash),
    )
    voted = 0
    if row:
        if int(row["kind"] or 1) == kind:
            db.execute("DELETE FROM comment_likes WHERE id=?", (row["id"],))
        else:
            db.execute("UPDATE comment_likes SET kind=? WHERE id=?", (kind, row["id"]))
            voted = kind
    else:
        db.execute(
            "INSERT INTO comment_likes (comment_id, voter_hash, kind, created_at) VALUES (?,?,?,?)",
            (comment_id, voter_hash, kind, db.now()),
        )
        voted = kind
    likes = int(db.scalar(
        "SELECT COUNT(*) FROM comment_likes WHERE comment_id=? AND kind = 1",
        (comment_id,), 0) or 0)
    dislikes = int(db.scalar(
        "SELECT COUNT(*) FROM comment_likes WHERE comment_id=? AND kind = -1",
        (comment_id,), 0) or 0)
    return {"liked": voted == 1, "disliked": voted == -1,
            "likes": likes, "dislikes": dislikes}


def overview(email_hash: str, voter_hash: str = "", include_owner: bool = False,
             custom_avatar: str = "", recent_offset: int = 0, owner_only: bool = False,
             include_pending: bool = False) -> dict:
    rows = _public_rows(email_hash, include_owner, owner_only, include_pending)
    # 统计 / 热力图 / 一周分布只算已通过：待审核还没公开，算进去会让数字和前台对不上；
    # 但「最近发言」按 rows 全量渲染（含自己待审核的），并带 status 供前端标注。
    approved_rows = [r for r in rows if str(r.get("status") or "") == "approved"]
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    recent_cutoff = (today - timedelta(days=30)).isoformat()

    days = Counter()
    weekly = Counter()
    for row in approved_rows:
        day = _parse_day(row.get("created_at"))
        if not day:
            continue
        days[day] += 1
        try:
            dt = datetime.fromisoformat(day).date()
            weekly[dt.weekday()] += 1
        except (ValueError, TypeError):
            pass

    # 热力图：从本周一往前 WEEKS-1 周，共 WEEKS*7 天，按 [周][星期] 排列
    start = monday - timedelta(weeks=WEEKS - 1)
    heatmap = []
    for w in range(WEEKS):
        week = []
        for d in range(7):
            date = start + timedelta(weeks=w, days=d)
            iso = date.isoformat()
            week.append({"d": iso, "c": int(days.get(iso, 0)), "f": date > today})
        heatmap.append(week)

    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekly_list = [{"day": weekday_names[i], "count": int(weekly.get(i, 0))} for i in range(7)]

    comment_ids = [int(r["id"]) for r in approved_rows if r.get("id")]
    recent = []
    offset = max(0, int(recent_offset or 0))
    for row in rows[offset:offset + RECENT_LIMIT]:
        title, url = _source(row)
        recent.append({
            "id": int(row["id"]),
            "text": _plain(str(row.get("content") or "")),
            "source_title": title,
            "url": url,
            "status": str(row.get("status") or ""),
            "created_at": str(row.get("created_at") or ""),
        })

    # 待审核：概览里单独列出来（数量 + 最近几条），已通过的在「我的评论」tab 里看
    pending_rows = [r for r in rows if str(r.get("status") or "") == "pending"]
    pending = []
    for row in pending_rows[:RECENT_LIMIT]:
        title, url = _source(row)
        pending.append({
            "id": int(row["id"]),
            "text": _plain(str(row.get("content") or "")),
            "source_title": title,
            "url": url,
            "created_at": str(row.get("created_at") or ""),
        })

    latest = rows[0] if rows else {}
    first = approved_rows[-1] if approved_rows else {}
    stats = {
        "total": len(approved_rows),
        "active_30d": sum(1 for r in approved_rows if str(r.get("created_at") or "")[:10] >= recent_cutoff),
        "likes": _like_count(email_hash, comment_ids),
        "streak": _streak(set(days.keys())),
    }
    user = {
        "name": str(latest.get("author") or "匿名读者"),
        "website": str(latest.get("website") or "") if str(latest.get("website") or "").startswith(("http://", "https://")) else "",
        "avatar": (custom_avatar or "") or (avatar.urls(str(latest.get("email_hash") or ""), str(latest.get("qq") or ""), 80)[0] or avatar.default_url()),
        "first_at": str(first.get("created_at") or ""),
        "last_at": str(latest.get("created_at") or ""),
        "sources": len({(r.get("post_id"), r.get("project_id")) for r in approved_rows}),
    }
    return {
        "user": user,
        "stats": stats,
        "heatmap": heatmap,
        "weekly": weekly_list,
        "recent": recent,
        "recent_has_more": (offset + RECENT_LIMIT) < len(rows),
        "recent_next_offset": offset + len(recent),
        "pending": pending,
        "pending_count": len(pending_rows),
        "liked_ids": sorted(liked_comment_ids(voter_hash or email_hash, comment_ids)),
    }


def my_replies(email_hash: str, offset: int = 0, limit: int = 10, include_owner: bool = False,
               owner_only: bool = False) -> tuple[list[dict], bool]:
    """我回复别人的评论（我发出的、parent_id 指向他人评论）。返回 (列表, 是否还有更多)。"""
    if owner_only:
        who = "c.is_owner = 1"
        params: tuple = ()
    else:
        if not email_hash:
            return [], False
        who = "c.email_hash = ?" + ("" if include_owner else " AND c.is_owner = 0")
        params = (email_hash,)
    rows = db.query(
        "SELECT c.id, c.content, c.created_at, c.post_id, c.project_id, c.parent_id, "
        "p.title AS post_title, pj.name AS project_name, pa.author AS parent_author "
        "FROM comments c "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        "LEFT JOIN comments pa ON c.parent_id = pa.id "
        "WHERE " + who + " AND c.parent_id IS NOT NULL AND c.parent_id > 0 "
        "AND c.status = 'approved' AND c.is_private = 0 AND c.is_ai = 0 "
        "AND c.deleted_at IS NULL ORDER BY c.created_at DESC, c.id DESC LIMIT ? OFFSET ?",
        (*params, limit + 1, max(0, int(offset))),
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for row in rows:
        item = dict(row)
        title, url = _source(item)
        items.append({
            "id": int(item["id"]),
            "text": _plain(str(item.get("content") or "")),
            "reply_to": str(item.get("parent_author") or ""),
            "source_title": title,
            "url": url,
            "created_at": str(item.get("created_at") or ""),
        })
    return items, has_more


def mentions(email_hash: str, offset: int = 0, limit: int = 10,
             owner_only: bool = False) -> tuple[list[dict], bool]:
    """别人回复我的评论（我的@）：parent 是我的评论，回复者不是我。返回 (列表, 是否还有更多)。"""
    if owner_only:
        parent_match = "p0.is_owner = 1"
        not_mine = "c.is_owner = 0"
        params: tuple = ()
    else:
        if not email_hash:
            return [], False
        parent_match = "p0.email_hash = ?"
        not_mine = "c.email_hash != ?"
        params = (email_hash, email_hash)
    rows = db.query(
        "SELECT c.id, c.author, c.content, c.created_at, c.post_id, c.project_id, c.parent_id, "
        "p.title AS post_title, pj.name AS project_name "
        "FROM comments c "
        "JOIN comments p0 ON c.parent_id = p0.id AND " + parent_match + " "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        "WHERE " + not_mine + " AND c.status = 'approved' AND c.is_private = 0 "
        "AND c.deleted_at IS NULL "
        "ORDER BY c.created_at DESC, c.id DESC LIMIT ? OFFSET ?",
        (*params, limit + 1, max(0, int(offset))),
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for row in rows:
        item = dict(row)
        title, url = _source(item)
        items.append({
            "id": int(item["id"]),
            "from_author": str(item.get("author") or "匿名"),
            "text": _plain(str(item.get("content") or "")),
            "source_title": title,
            "url": url,
            "created_at": str(item.get("created_at") or ""),
        })
    return items, has_more


def my_comments(email_hash: str, offset: int = 0, limit: int = 10,
                owner_only: bool = False) -> tuple[list[dict], bool]:
    """我已通过的评论，按时间倒序。返回 (列表, 是否还有更多)。

    待审核由概览里的「待审核」区块单独展示，这里只放已公开的；
    被拒（rejected）与私密评论不列出，和前台可见口径保持一致。
    """
    if owner_only:
        who = "c.is_owner = 1"
        params: tuple = ()
    else:
        if not email_hash:
            return [], False
        who = "c.email_hash = ?"
        params = (email_hash,)
    rows = db.query(
        "SELECT c.id, c.content, c.status, c.created_at, c.post_id, c.project_id, c.parent_id, "
        "p.title AS post_title, pj.name AS project_name "
        "FROM comments c "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        "WHERE " + who + " AND c.status = 'approved' AND c.is_private = 0 "
        "AND c.is_ai = 0 AND c.deleted_at IS NULL "
        "ORDER BY c.created_at DESC, c.id DESC LIMIT ? OFFSET ?",
        (*params, limit + 1, max(0, int(offset))),
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for row in rows:
        item = dict(row)
        title, url = _source(item)
        items.append({
            "id": int(item["id"]),
            "text": _plain(str(item.get("content") or "")),
            "status": str(item.get("status") or ""),
            "source_title": title,
            "url": url,
            "created_at": str(item.get("created_at") or ""),
        })
    return items, has_more
