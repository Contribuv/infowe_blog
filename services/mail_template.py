"""评论通知邮件模板（HTML + 纯文本）。

版式参考常见博客通知邮件：顶部栏目小字、大标题、强调色短条、文章链接、
评论卡片、操作链接与页脚。强调色默认读取当前主题 theme.css 的 --accent，
主题切换或改色后自动跟随；读取失败时回退到 #0969da。
"""

from __future__ import annotations

import functools
import html
import re

from config import THEMES_DIR

DEFAULT_ACCENT = "#0969da"
_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',"
    "'Microsoft YaHei',Arial,sans-serif"
)

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((/uploads/[^)\s]+)\)")


@functools.lru_cache(maxsize=8)
def _accent_from_css(path: str, mtime: float) -> str:
    """按文件 mtime 缓存，改了主题色不用重启也能生效。"""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return DEFAULT_ACCENT
    match = re.search(r"--accent:\s*(#[0-9a-fA-F]{3,8})", text)
    return match.group(1) if match else DEFAULT_ACCENT


def accent_color() -> str:
    from services import theme

    path = THEMES_DIR / theme.active_key() / "theme.css"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return DEFAULT_ACCENT
    return _accent_from_css(str(path), mtime)


def display_name(blog_name: str) -> str:
    """页脚站点名：首页标题优先，留空回退站点名。"""
    from services import settings

    return settings.get_str("home_title", "").strip() or blog_name


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _content_html(text: str, site: str) -> str:
    """评论正文：转义后仅放行站内图片，换行转 <br>。"""
    safe = _esc(text)

    def repl(match: re.Match) -> str:
        src = match.group(1)
        return (
            f'<img src="{site}{src}" alt="" '
            'style="display:block;max-width:100%;height:auto;border-radius:8px;margin:8px 0">'
        )

    return _IMAGE_RE.sub(repl, safe).replace("\r\n", "\n").replace("\n", "<br>")


def _card(inner: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse:separate;border:1px solid #e6e6ea;border-radius:12px;'
        'background:#fcfcfd;margin:0 0 22px;">'
        '<tr><td style="padding:16px 18px;color:#3f4247;font-size:15px;line-height:1.75;'
        f'word-break:break-word;">{inner}</td></tr></table>'
    )


def _meta(author: str, when: str, accent: str, extra: str = "") -> str:
    extra_html = (
        f'<span style="color:#b0b0ba;"> · </span>{_esc(extra)}' if extra else ""
    )
    return (
        '<div style="color:#8a8a95;font-size:13px;line-height:20px;margin-bottom:10px;">'
        f'<strong style="color:#4a4a55;">{_esc(author)}</strong>'
        f'<span style="color:#c4c4cc;"> · </span>{_esc(when)}{extra_html}</div>'
    )


def _page(
    *,
    kicker: str,
    headline: str,
    body: str,
    blog_name: str,
    site: str,
    accent: str,
) -> str:
    footer_name = display_name(blog_name)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{_esc(headline)}</title>
</head>
<body style="margin:0;padding:0;background:#f4f5f7;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#f4f5f7;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
       style="width:100%;max-width:600px;background:#ffffff;border-radius:16px;border:1px solid #ebebef;">
<tr><td style="padding:40px 40px 32px;font-family:{_FONT};color:#333333;font-size:15px;line-height:28px;">

<div style="color:#a8a8b3;font-size:12px;letter-spacing:1px;margin-bottom:18px;">{_esc(kicker)}</div>

<div style="font-size:24px;line-height:36px;margin-bottom:10px;color:#1f2328;">{_esc(headline)}</div>

<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 26px;">
<tr><td width="96" height="8" bgcolor="{accent}"
        style="border-radius:6px;font-size:0;line-height:0;">&nbsp;</td></tr>
</table>

{body}

<div style="height:1px;background:#ebebeb;margin:32px 0 18px;"></div>
<div style="color:#9a9aa5;font-size:12px;line-height:20px;">
{_esc(footer_name)}<br>
<a href="{_esc(site)}" style="color:#9a9aa5;text-decoration:none;">{_esc(site)}</a>
</div>

</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _article(label: str, title: str, url: str, accent: str) -> str:
    return (
        '<div style="color:#666666;margin-bottom:18px;">'
        f'{_esc(label)}：'
        f'<a href="{_esc(url)}" style="color:{accent};text-decoration:none;">'
        f'《{_esc(title)}》</a></div>'
    )


def _action(url: str, accent: str, text: str = "查看完整对话 →") -> str:
    return (
        '<div style="margin-bottom:8px;">'
        f'<a href="{_esc(url)}" style="color:{accent};text-decoration:none;font-weight:600;">'
        f"{_esc(text)}</a></div>"
    )


def comment_notice(
    *,
    blog_name: str,
    site: str,
    label: str,
    title: str,
    url: str,
    author: str,
    content: str,
    when: str,
    status: str,
    parent_author: str = "",
) -> tuple[str, str]:
    """博主视角：收到新评论 / 新回复。返回 (纯文本, HTML)。"""
    accent = accent_color()
    pending = status != "approved"
    headline = "你的评论收到了新回复" if parent_author else f"你的{label}收到了新评论"
    kicker = f"{blog_name} · {'新回复' if parent_author else '新评论'}"
    reply_meta = f"回复 @{parent_author}" if parent_author else ""

    body = "".join(
        [
            _article(label, title, url, accent),
            _meta(author, when, accent, reply_meta),
            _card(_content_html(content, site)),
            _action(url, accent),
        ]
    )

    state = "待审核（通过后才会公开）" if pending else "已通过审核"
    text = (
        f"{blog_name} · {'新回复' if parent_author else '新评论'}\n\n"
        f"{headline}\n\n"
        f"{label}：《{title}》\n"
        f"作者：{author}\n"
        f"时间：{when}\n"
        f"状态：{state}\n"
        f"{'回复对象：' + parent_author + chr(10) if parent_author else ''}"
        f"\n{content}\n\n"
        f"查看完整对话：{url}\n\n"
        f"— {display_name(blog_name)}\n{site}\n"
    )
    page = _page(
        kicker=kicker, headline=headline, body=body, blog_name=blog_name, site=site, accent=accent
    )
    return text, page


def reply_notice(
    *,
    blog_name: str,
    site: str,
    label: str,
    title: str,
    url: str,
    author: str,
    content: str,
    when: str,
    parent_author: str = "",
) -> tuple[str, str]:
    """访客视角：你的评论收到了回复。返回 (纯文本, HTML)。"""
    accent = accent_color()
    headline = "你收到了新的回复"
    kicker = f"{blog_name} · 新回复"
    reply_meta = f"回复 @{parent_author}" if parent_author else ""

    body = "".join(
        [
            _article(label, title, url, accent),
            _meta(author, when, accent, reply_meta),
            _card(_content_html(content, site)),
            _action(url, accent),
        ]
    )
    text = (
        f"{blog_name} · 新回复\n\n"
        f"你在{label}《{title}》的评论收到了回复\n\n"
        f"{author} · {when}\n"
        f"\n{content}\n\n"
        f"查看完整对话：{url}\n\n"
        f"— {display_name(blog_name)}\n{site}\n"
    )
    page = _page(
        kicker=kicker, headline=headline, body=body, blog_name=blog_name, site=site, accent=accent
    )
    return text, page
