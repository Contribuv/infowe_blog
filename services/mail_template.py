"""评论通知邮件模板（HTML + 纯文本）。

样式参照主流博客的邮件通知模板，统一 8px 圆角体系：
- 顶部品牌色条圆角 8px 8px 0 0，与卡片顶部圆角严丝合缝；
- 底部页脚圆角 0 0 8px 8px，与卡片底部圆角严丝合缝；
- 正文卡用左侧 3px 色条 + 右下圆角，不用四边描边，避免层层套框的割裂感。
"""

from __future__ import annotations

import functools
import html
import re

from config import THEMES_DIR

DEFAULT_ACCENT = "#2563eb"
_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB',"
    "'Microsoft YaHei','Helvetica Neue',Arial,sans-serif"
)

# 中性色板：与主题强调色搭配，深浅层次固定，避免每处单独写色值
_TEXT = "#1f2a33"
_META = "#5c6b78"
_MUTED = "#8a97a4"
_BORDER = "#e3e9ef"
_QUOTE_BAR = "#d5dee6"
_CARD_BG = "#f6f9fb"
_FOOT_BG = "#fafcfd"
_PAGE_BG = "#eef3f7"

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((/uploads/[^)\s]+)\)")


@functools.lru_cache(maxsize=8)
def _accent_from_css(path: str, mtime: float) -> str:
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


def _shade(hex_color: str, factor: float) -> str:
    """把强调色按比例调暗，用于按钮底色（色条太浅时按钮会发飘）。"""
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return hex_color
    try:
        rgb = [int(value[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return hex_color
    rgb = [max(0, min(255, round(ch * factor))) for ch in rgb]
    return "#%02x%02x%02x" % tuple(rgb)


def display_name(blog_name: str) -> str:
    from services import settings

    return settings.get_str("home_title", "").strip() or blog_name


def blogger_name() -> str:
    from services import settings

    return settings.get_str("author", "").strip() or display_name(settings.get_str("blog_name", "博客"))


def esc(value: object) -> str:
    """HTML 转义，供外部模块构造邮件内容时使用。"""
    return html.escape(str(value or ""), quote=True)


def _esc(value: object) -> str:
    return esc(value)


def _content_html(text: str, site: str) -> str:
    safe = _esc(text)

    def repl(match: re.Match) -> str:
        src = match.group(1)
        return (
            f'<img src="{site}{src}" alt="" '
            'style="display:block;max-width:100%;height:auto;border-radius:8px;margin:10px 0 6px;">'
        )

    html_text = _IMAGE_RE.sub(repl, safe).replace("\r\n", "\n").replace("\n", "<br>")
    return html_text


def _initials(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "U"
    return name[0].upper()


def _avatar(name: str, accent: str, avatar_url: str = "") -> str:
    """32px 圆形头像：有 gravatar/qq 头像用真实图，没有用首字母色块兜底。"""
    size = 32
    if avatar_url:
        return (
            '<td style="width:%dpx;vertical-align:top;" valign="top">'
            '<img src="%s" width="%d" height="%d" '
            'style="width:%dpx;height:%dpx;border-radius:50%%;display:block;object-fit:cover;" alt="">'
            '</td><td style="width:10px;font-size:0;line-height:0;">&nbsp;</td>'
        ) % (size, _esc(avatar_url), size, size, size, size)
    return (
        '<td style="width:%dpx;vertical-align:top;" valign="top">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="width:%dpx;height:%dpx;background:%s;border-radius:50%%;">'
        '<tr><td align="center" valign="middle" '
        'style="width:%dpx;height:%dpx;color:#ffffff;font-size:13px;font-weight:700;'
        'text-align:center;line-height:%dpx;">%s</td></tr></table>'
        '</td><td style="width:10px;font-size:0;line-height:0;">&nbsp;</td>'
    ) % (size, size, size, accent, size, size, size, _initials(name))


def _shell(*, tag: str, headline: str, meta_html: str, body: str, blog_name: str,
           site: str, accent: str, foot_note: str) -> str:
    """邮件外壳：品牌条 + 品牌行 + 标题 + 分割线 + 正文 + 页脚说明。

    圆角全部按 8px 体系对齐：品牌条顶部圆角 = 卡片顶部圆角，
    页脚底部圆角 = 卡片底部圆角，中途不留直角断口。
    """
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<title>%(headline)s</title>
</head>
<body style="margin:0;padding:0;background:%(page_bg)s;">
<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" style="background:%(page_bg)s;">
  <tr><td align="center" style="padding:26px 12px 32px;font-family:%(font)s;">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%%;max-width:600px;">
      <tr><td>
        <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;border-radius:8px;border:1px solid %(border)s;">
          <tr><td style="height:3px;line-height:3px;font-size:0;background:%(accent)s;border-radius:8px 8px 0 0;">&nbsp;</td></tr>
          <tr><td style="padding:16px 30px 0 30px;">
            <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-size:15px;font-weight:700;color:%(text)s;letter-spacing:0;">
                  <a href="%(site)s" style="font-size:15px;font-weight:700;color:%(text)s;text-decoration:none;">%(blog)s</a>
                </td>
                <td style="font-size:12px;line-height:20px;color:%(muted)s;text-align:right;white-space:nowrap;">%(tag)s</td>
              </tr>
            </table>
          </td></tr>
          <tr><td style="padding:0 30px;">
            <h1 style="margin:12px 0 4px 0;font-size:19px;line-height:1.5;font-weight:700;color:%(text)s;">%(headline)s</h1>
            <p style="margin:0 0 16px 0;font-size:13px;line-height:1.7;color:%(meta)s;">%(meta_html)s</p>
          </td></tr>
          <tr><td style="padding:0 30px;">
            <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0">
              <tr><td style="height:1px;line-height:1px;font-size:0;background:%(border)s;">&nbsp;</td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:18px 30px 0 30px;">
            %(body)s
          </td></tr>
          <tr><td style="padding:22px 30px 26px 30px;background:%(foot_bg)s;border-top:1px solid %(border)s;border-radius:0 0 8px 8px;font-family:%(font)s;font-size:12px;line-height:1.9;color:%(muted)s;">
            %(foot_note)s
          </td></tr>
        </table>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>""" % {
        "headline": _esc(headline),
        "font": _FONT,
        "accent": accent,
        "border": _BORDER,
        "text": _TEXT,
        "meta": _META,
        "muted": _MUTED,
        "page_bg": _PAGE_BG,
        "foot_bg": _FOOT_BG,
        "blog": _esc(blog_name),
        "site": _esc(site),
        "tag": _esc(tag),
        "meta_html": meta_html,
        "body": body,
        "foot_note": foot_note,
    }


def _meta_line(when: str, title: str, url: str, accent: str) -> str:
    """标题下方的时间 + 文章链接。"""
    link = (
        '<a href="%s" style="color:%s;text-decoration:underline;">《%s》</a>'
        % (_esc(url), accent, _esc(title))
    )
    return "%s · %s" % (_esc(when), link)


def _card(author: str, content_html: str, accent: str, avatar_url: str = "") -> str:
    """正文内容卡：浅底 + 左侧 3px 强调色条，不用四边描边。

    头像+作者名是 meta 层级（小号灰字），与正文（大号深色）拉开层次，
    避免作者名和评论内容糊成一片。
    """
    return (
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" '
        'style="background:%s;border-left:3px solid %s;border-radius:0 6px 6px 0;">'
        '<tr><td style="padding:14px 18px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        '%s'
        '<td style="font-size:12px;line-height:32px;font-weight:600;color:%s;vertical-align:middle;">%s</td>'
        '</tr></table>'
        '<div style="padding:8px 0 0 0;font-size:16px;line-height:1.75;color:%s;word-break:break-word;overflow-wrap:anywhere;">%s</div>'
        '</td></tr></table>'
    ) % (_CARD_BG, accent, _avatar(author, accent, avatar_url), _META, _esc(author), _TEXT, content_html)


def _quote(text_html: str) -> str:
    """「你之前说」引用块：左侧浅色竖线 + 次级文字。"""
    return (
        '<div style="padding:16px 0 0 0;">'
        '<div style="padding:0 0 4px 0;font-size:12px;line-height:1.6;color:%s;">你之前说</div>'
        '<div style="padding:2px 0 2px 12px;border-left:3px solid %s;font-size:14px;line-height:1.75;color:%s;">%s</div>'
        '</div>'
    ) % (_MUTED, _QUOTE_BAR, _META, text_html)


def _cta(url: str, accent: str, button_text: str, action_html: str = "") -> str:
    """主按钮 + 纯文本兜底链接（部分客户端不渲染按钮）。"""
    btn_bg = _shade(accent, 0.78)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0 0 0;"><tr>'
        '<td style="background:%s;border-radius:6px;mso-padding-alt:9px 20px;">'
        '<a href="%s" style="display:inline-block;padding:9px 20px;font-size:14px;line-height:20px;'
        'font-weight:600;color:#ffffff;text-decoration:none;border-radius:6px;">%s</a>'
        '</td></tr></table>'
        '<div style="padding:10px 0 0 0;font-size:12px;line-height:1.7;color:%s;word-break:break-all;">'
        '按钮点不动？复制链接到浏览器：<br>'
        '<a href="%s" style="color:%s;text-decoration:underline;">%s</a></div>'
        '%s'
    ) % (
        btn_bg, _esc(url), _esc(button_text), _MUTED,
        _esc(url), accent, _esc(url), action_html,
    )


def _action_row(items: list[tuple[str, str]]) -> str:
    """底部次级链接行（打开文章、返回首页等）。"""
    if not items:
        return ""
    parts = []
    for index, (text, url) in enumerate(items):
        if index:
            parts.append('<span style="padding:0 6px;color:#b9c5cf;">·</span>')
        parts.append(
            '<a href="%s" style="color:#2470a8;text-decoration:underline;">%s</a>'
            % (_esc(url), _esc(text))
        )
    return '<div style="padding:12px 0 0 0;font-size:13px;line-height:1.8;color:%s;">%s</div>' % (
        _META, "".join(parts),
    )


def generic_notice(*, blog_name: str, site: str, tag: str, headline: str, body_html: str,
                   button_text: str = "", button_url: str = "", foot_note: str = "") -> tuple[str, str]:
    """通用通知邮件（友链申请、审核通过等），与评论通知共用同一套视觉外壳。"""
    accent = accent_color()
    parts = [body_html]
    if button_text and button_url:
        parts.append(_cta(button_url, accent, button_text))
        parts.append(_action_row([("返回首页", site)]))
    body = "".join(parts)
    text = "%s\n\n%s" % (headline, _strip_tags(body_html))
    page = _shell(
        tag=tag,
        headline=headline,
        meta_html=_esc(blog_name),
        body=body,
        blog_name=blog_name,
        site=site,
        accent=accent,
        foot_note=foot_note or (
            '<p style="margin:0;">此邮件由 %s 自动发送，请勿直接回复。</p>'
            '<p style="margin:0;"><a href="%s" style="color:#6b7a88;text-decoration:underline;">%s</a></p>'
            % (_esc(blog_name), _esc(site), _esc(blog_name))
        ),
    )
    return text, page


def _strip_tags(html_text: str) -> str:
    return re.sub(r"<[^>]+>", "", html_text).strip()


def comment_notice(*, blog_name: str, site: str, label: str, title: str, url: str, author: str, content: str, when: str, status: str, parent_author: str = "", parent_content: str = "", author_avatar: str = "") -> tuple[str, str]:
    """博主提醒：访客新评论 / 访客回复访客。"""
    accent = accent_color()
    pending = status != "approved"
    if parent_author:
        headline = "%s 回复了%s的评论" % (author, parent_author)
        tag = "新回复"
    else:
        headline = "%s 发表了新评论" % author
        tag = "待审核" if pending else "新评论"

    body_parts = [_card(author, _content_html(content, site), accent, author_avatar)]
    if parent_author and parent_content:
        # 原评论用引用块展示，位置在下方，字号更小，不喧宾夺主
        body_parts.append(_quote(_content_html(parent_content, site)))
    body_parts.append(_cta(url, accent, "前往查看" + ("（待审核）" if pending else "")))
    body_parts.append(_action_row([("打开文章", url), ("返回首页", site)]))
    body = "".join(body_parts)

    text = (
        f"{headline}\n\n{label}：《{title}》\n"
        f"{author} · {when}\n\n{content}\n\n查看对话：{url}\n"
    )
    page = _shell(
        tag=tag,
        headline=headline,
        meta_html=_meta_line(when, title, url, accent),
        body=body,
        blog_name=blog_name,
        site=site,
        accent=accent,
        foot_note=(
            '<p style="margin:0;">你收到这封邮件，是因为有人在《%s》下发表了评论，'
            '博主需要及时处理。</p>'
            '<p style="margin:0;">直接回复本邮件，即可回给 %s。</p>'
            '<p style="margin:0;"><a href="%s" style="color:#6b7a88;text-decoration:underline;">%s</a></p>'
        ) % (_esc(title), _esc(author), _esc(site), _esc(blog_name)),
    )
    return text, page


def reply_notice(*, blog_name: str, site: str, label: str, title: str, url: str, author: str, content: str, when: str, parent_author: str = "", parent_content: str = "", author_avatar: str = "") -> tuple[str, str]:
    """被回复者提醒：你的评论收到了回复。"""
    accent = accent_color()
    headline = "%s 回复了你的评论" % author
    tag = "新回复"

    body_parts = [_card(author, _content_html(content, site), accent, author_avatar)]
    if parent_content:
        body_parts.append(_quote(_content_html(parent_content, site)))
    body_parts.append(_cta(url, accent, "查看并回复"))
    body_parts.append(_action_row([("打开文章", url), ("返回首页", site)]))
    body = "".join(body_parts)

    text = (
        f"{headline}\n\n你在{label}《{title}》的评论收到了回复\n\n"
        f"{author} · {when}\n\n{content}\n\n查看对话：{url}\n"
    )
    page = _shell(
        tag=tag,
        headline=headline,
        meta_html=_meta_line(when, title, url, accent),
        body=body,
        blog_name=blog_name,
        site=site,
        accent=accent,
        foot_note=(
            '<p style="margin:0;">你收到这封邮件，是因为你在《%s》下的评论收到了回复。</p>'
            '<p style="margin:0;">直接回复本邮件，即可回给 %s。</p>'
            '<p style="margin:0;"><a href="%s" style="color:#6b7a88;text-decoration:underline;">%s</a></p>'
        ) % (_esc(title), _esc(author), _esc(site), _esc(blog_name)),
    )
    return text, page
