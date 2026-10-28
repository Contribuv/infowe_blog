"""评论通知邮件模板（HTML + 纯文本）。"""

from __future__ import annotations

import functools
import html
import re

from config import THEMES_DIR

DEFAULT_ACCENT = "#2563eb"
_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',"
    "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',Arial,sans-serif"
)

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


def display_name(blog_name: str) -> str:
    from services import settings

    return settings.get_str("home_title", "").strip() or blog_name


def blogger_name() -> str:
    from services import settings

    return settings.get_str("author", "").strip() or display_name(settings.get_str("blog_name", "博客"))


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _content_html(text: str, site: str) -> str:
    safe = _esc(text)

    def repl(match: re.Match) -> str:
        src = match.group(1)
        return (
            f'<img src="{site}{src}" alt="" '
            'style="display:block;max-width:100%;height:auto;border-radius:10px;margin:10px 0 6px;">'
        )

    html_text = _IMAGE_RE.sub(repl, safe).replace("\r\n", "\n").replace("\n", "<br>")
    return html_text


def _initials(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "U"
    return name[0].upper()


def _avatar(name: str, accent: str, avatar_url: str = "") -> str:
    init = _initials(name)
    if avatar_url:
        return (
            '<td style="width:36px;vertical-align:top;">'
            '<img src="%s" width="36" height="36" style="width:36px;height:36px;border-radius:50%%;display:block;object-fit:cover;" alt="">'
            '</td>'
        ) % _esc(avatar_url)
    # 用 table 单元格居中：flex 在 Outlook 等客户端里不生效，文字会贴左上角
    return (
        '<td style="width:36px;vertical-align:top;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="width:36px;height:36px;background:%s;border-radius:18px;">'
        '<tr><td align="center" valign="middle" '
        'style="width:36px;height:36px;color:#ffffff;font-size:14px;font-weight:600;text-align:center;line-height:36px;">%s</td></tr>'
        '</table>'
        '</td>'
    ) % (accent, init)


def _page(*, headline: str, body: str, blog_name: str = "") -> str:
    """统一邮件外壳：品牌条 + 站点名页头 + 正文卡片 + 页脚。

    早前只有一个白卡，正文短时整封邮件在客户端里很矮、像半截通知；
    补上页头/页脚并加大留白后视觉完整，也更像「一封信」。
    页头小字保持站点名（blog_name），和邮件主题/页脚的统一品牌一致。
    """
    site_name = _esc(blog_name or headline)
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<title>%(headline)s</title>
</head>
<body style="margin:0;padding:0;background:#f6f7f9;">
<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" style="background:#f6f7f9;">
  <tr><td align="center" style="padding:32px 12px 36px;">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" style="width:100%%;max-width:560px;">
      <tr><td>
        <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;border-radius:12px;border:1px solid #e7e9ee;">
          <tr><td style="height:4px;background:%(accent)s;font-size:0;line-height:4px;">&nbsp;</td></tr>
          <tr><td style="padding:30px 30px 26px;font-family:%(font)s;color:#1f2328;font-size:15px;line-height:1.9;">
            <div style="font-size:12px;letter-spacing:1px;color:#98a0ab;margin-bottom:8px;">%(blog)s</div>
            <div style="font-size:18px;font-weight:600;line-height:1.6;margin-bottom:20px;">%(headline)s</div>
            %(body)s
          </td></tr>
          <tr><td style="padding:14px 30px;background:#fafbfc;border-top:1px solid #eff1f4;font-family:%(font)s;font-size:12px;line-height:1.7;color:#9aa0a6;">
            此邮件由 %(blog)s 自动发送，请勿直接回复。
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
        "accent": accent_color(),
        "blog": site_name,
        "body": body,
    }


def _context_line(label: str, title: str, url: str, accent: str) -> str:
    return (
        '<div style="font-size:13px;color:#6b6f76;margin-bottom:18px;">%s：'
        '<a href="%s" style="color:%s;text-decoration:none;">《%s》</a></div>'
    ) % (_esc(label), _esc(url), accent, _esc(title))


def _bubble(author: str, when: str, content_html: str, accent: str, is_reply: bool = False, avatar_url: str = "") -> str:
    bg = "#f8f9fb" if not is_reply else "#f7f9ff"
    border = "#e7e9ee" if not is_reply else "rgba(37,99,235,0.25)"
    return (
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 12px;"><tr>'
        '%s'
        '<td style="padding-left:10px;vertical-align:top;">'
        '<div style="margin-bottom:4px;"><span style="font-size:14px;font-weight:600;color:#1f2328;">%s</span>'
        '<span style="font-size:12px;color:#9aa0a6;margin-left:8px;">%s</span></div>'
        '<div style="border:1px solid %s;background:%s;border-radius:10px;padding:10px 14px;">'
        '<div style="color:#2f343c;font-size:14px;line-height:1.9;word-break:break-word;">%s</div>'
        '</div>'
        '</td>'
        '</tr></table>'
    ) % (_avatar(author, accent, avatar_url), _esc(author), _esc(when), border, bg, content_html)


def _action(url: str, accent: str, text: str = "查看对话") -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:16px 0 2px;"><tr>'
        '<td style="border-radius:6px;background:%s;">'
        '<a href="%s" style="display:inline-block;padding:7px 16px;color:#ffffff;text-decoration:none;font-size:13px;">%s</a>'
        '</td></tr></table>'
    ) % (accent, _esc(url), _esc(text))


def comment_notice(*, blog_name: str, site: str, label: str, title: str, url: str, author: str, content: str, when: str, status: str, parent_author: str = "", parent_content: str = "", author_avatar: str = "") -> tuple[str, str]:
    accent = accent_color()
    pending = status != "approved"
    headline = f"{label}收到了新回复" if parent_author else f"{label}收到了新评论"
    state = "（待审核）" if pending else ""
    body_parts = [_context_line(label, title, url, accent)]
    if parent_author:
        # 之前这里传的是字面「原评论」占位，访客看到的是一张写着「原评论」的气泡；
        # 有父评论正文时才渲染，没有就省略，避免假内容
        if parent_content:
            body_parts.append(_bubble(parent_author, "", _content_html(parent_content, site), accent, is_reply=False))
        body_parts.append(_bubble(author, when, _content_html(content, site), accent, is_reply=True, avatar_url=author_avatar))
    else:
        body_parts.append(_bubble(author, when, _content_html(content, site), accent, is_reply=False, avatar_url=author_avatar))
    body_parts.append(_action(url, accent, "前往查看" + state))
    body = "".join(body_parts)
    text = (
        f"{headline}\n\n{label}：《{title}》\n"
        f"{author} · {when}\n\n{content}\n\n查看对话：{url}\n"
    )
    page = _page(headline=headline, body=body, blog_name=blog_name)
    return text, page


def reply_notice(*, blog_name: str, site: str, label: str, title: str, url: str, author: str, content: str, when: str, parent_author: str = "", author_avatar: str = "") -> tuple[str, str]:
    accent = accent_color()
    headline = "收到新回复"
    body_parts = [_context_line(label, title, url, accent)]
    body_parts.append(_bubble(author, when, _content_html(content, site), accent, is_reply=True, avatar_url=author_avatar))
    body_parts.append(_action(url, accent, "前往查看"))
    body = "".join(body_parts)
    text = (
        f"{headline}\n\n你在{label}《{title}》的评论收到了回复\n\n"
        f"{author} · {when}\n\n{content}\n\n查看对话：{url}\n"
    )
    page = _page(headline=headline, body=body, blog_name=blog_name)
    return text, page
