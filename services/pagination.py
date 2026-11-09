"""统一的分页窗口。

前台所有翻页（列表页 / 圈子 / 评论）共用同一个页码上限，
避免总页数变多后页码按钮越铺越长、破坏排版。
"""
from __future__ import annotations

# 最多显示的页码按钮数量（不含上一页/下一页、省略号）。
# 移动端另有 .tech-page-num--m 规则，只保留 4 个页码。
MAX_LINKS = 5


def window(page: int, total_pages: int, max_links: int = MAX_LINKS) -> list[dict]:
    """返回可直接渲染的分页项列表。

    每项：num（页码；省略号为 None）/ current / ellipsis / mobile。
    首末页恒定可见，中间取围绕当前页的连续区间，缺口用省略号占位；
    总页数不超过上限时全部显示，不做无谓裁剪。
    """
    total_pages = max(1, int(total_pages or 1))
    page = min(max(1, int(page or 1)), total_pages)
    max_links = max(3, int(max_links or MAX_LINKS))

    def item(num, current=False, ellipsis=False):
        return {
            "num": num,
            "current": current,
            "ellipsis": ellipsis,
            # 移动端可见标记：首 / 末 / 当前 / 当前+1
            "mobile": bool(num) and (num in (1, total_pages, page, page + 1)),
        }

    if total_pages <= max_links:
        return [item(p, current=(p == page)) for p in range(1, total_pages + 1)]

    inner = max_links - 2
    start = min(max(page - inner // 2, 2), total_pages - inner)
    nums = sorted({1, total_pages, *range(start, start + inner)})

    out: list[dict] = []
    prev = 0
    for num in nums:
        if prev and num - prev > 1:
            out.append(item(None, ellipsis=True))
        out.append(item(num, current=(num == page)))
        prev = num
    return out
