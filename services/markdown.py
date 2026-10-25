"""Markdown 渲染、目录生成与 HTML 加固。"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

import markdown as md_lib

_EXTENSIONS = [
    "extra", "fenced_code", "tables", "toc", "sane_lists", "nl2br",
    "attr_list", "def_list", "admonition", "footnotes", "md_in_html",
]


def _make() -> md_lib.Markdown:
    return md_lib.Markdown(
        extensions=_EXTENSIONS,
        extension_configs={"toc": {"permalink": False, "slugify": _slugify}},
        output_format="html5",
    )


def _slugify(value: str, separator: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "section"


def _nest_toc(tokens: list[dict], level: int = 2) -> str:
    """把 python-markdown 的 toc_tokens 转成与 PHP 版一致的 ul/li 片段。"""
    if not tokens:
        return ""
    parts = ["<ul>\n"]
    for token in tokens:
        name = token.get("name") or ""
        ident = token.get("id") or ""
        text = html_lib.escape(name)
        parts.append(f'<li><a href="#{ident}">{text}</a>')
        children = token.get("children") or []
        if children:
            parts.append(_nest_toc(children, level + 1))
        parts.append("</li>\n")
    parts.append("</ul>\n")
    return "".join(parts)


def _filter_toc(tokens: list[dict], min_level: int = 2) -> list[dict]:
    """PHP 版目录只收 h2-h6；h1 的子标题上提。"""
    out: list[dict] = []
    for token in tokens or []:
        children = _filter_toc(token.get("children") or [], min_level)
        if int(token.get("level") or 0) >= min_level:
            item = dict(token)
            item["children"] = children
            out.append(item)
        else:
            out.extend(children)
    return out


def render_post(content: str) -> tuple[str, str]:
    if not (content or "").strip():
        return "", ""
    content = re.sub(r"^---.*?---\s*", "", content, count=1, flags=re.S)
    content = re.sub(r"<(https?://[^>\s]+)>", r"[\1](\1)", content)
    content = content.replace("[x]", '<i class="ck ck-done">✓</i> ').replace(
        "[ ]", '<i class="ck ck-todo">☐</i> '
    )
    parser = _make()
    html = parser.convert(content)
    html = _optimize_images(html)
    html = _harden_links(html)
    toc = _nest_toc(_filter_toc(getattr(parser, "toc_tokens", [])))
    return html, toc


def render_page(content: str) -> str:
    """后台预览：不生成额外目录。"""
    html, _ = render_post(content or "")
    return html


def render_readme(text: str, slug: str = "", branch: str = "main") -> str:
    if not (text or "").strip():
        return ""
    parser = _make()
    html = parser.convert(text)
    html = _optimize_images(html)
    html = _harden_links(html)
    return sanitize_external_html(html)

def toc_from_html(html: str) -> str:
    if not html:
        return ""
    items = []
    for match in re.finditer(r"<h([2-6])\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</h\1>", html, re.I | re.S):
        text = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        if text:
            items.append(
                {"level": int(match.group(1)), "id": match.group(2), "name": html_lib.unescape(text)}
            )
    if not items:
        return ""
    # 构造成嵌套结构
    roots: list[dict] = []
    stack: list[dict] = []

    def attach(item: dict) -> None:
        node = {"name": item["name"], "id": item["id"], "children": []}
        while stack and stack[-1]["_level"] >= item["level"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        node["_level"] = item["level"]
        stack.append(node)

    for item in items:
        attach(item)

    def strip_level(nodes: list[dict]) -> list[dict]:
        for n in nodes:
            n.pop("_level", None)
            strip_level(n["children"])
        return nodes

    return _nest_toc(strip_level(roots))


def _optimize_images(html: str) -> str:
    def repl(match: re.Match) -> str:
        tag = match.group(0)
        if "loading=" not in tag:
            tag = tag.replace("<img", '<img loading="lazy"', 1)
        return tag

    return re.sub(r"<img\b[^>]*>", repl, html, flags=re.I)


def _harden_links(html: str) -> str:
    def repl(match: re.Match) -> str:
        tag = match.group(0)
        tag = re.sub(r"""\s+href\s*=\s*(["'])\s*(?:javascript|vbscript|data):[^"']*\1""",
                     ' href="#"', tag, flags=re.I)
        if "rel=" not in tag and re.search(r'href\s*=\s*["\']https?://', tag, re.I):
            tag = tag.replace("<a", '<a rel="noopener noreferrer nofollow"', 1)
        if "target=" not in tag and re.search(r'href\s*=\s*["\']https?://', tag, re.I):
            tag = tag.replace("<a", '<a target="_blank"', 1)
        return tag

    return re.sub(r"<a\b[^>]*>", repl, html, flags=re.I)


_README_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "div", "span",
    "section", "article", "header", "footer", "main", "aside", "nav",
    "ul", "ol", "li", "dl", "dt", "dd", "blockquote", "pre", "code", "kbd", "samp", "var",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "a", "img", "picture", "source", "figure", "figcaption",
    "strong", "b", "em", "i", "u", "s", "del", "ins", "mark", "small", "sub", "sup",
    "details", "summary", "input", "video", "audio",
}
_README_ATTRS = {
    "*": ["class", "id", "align", "title"],
    "a": ["href", "target", "rel", "name"],
    "img": ["src", "alt", "width", "height", "loading"],
    "source": ["src", "srcset", "type", "media"],
    "video": ["src", "poster", "width", "height", "controls"],
    "audio": ["src", "controls"],
    "input": ["type", "checked", "disabled"],
    "th": ["colspan", "rowspan", "scope"],
    "td": ["colspan", "rowspan"],
    "ol": ["start", "reversed", "type"],
    "details": ["open"],
}


def sanitize_external_html(html: str) -> str:
    """README 来自外部仓库：白名单清洗 + 自动修复标签平衡。

    未在白名单内的标签（script/style/iframe/select 等）会被转义为文本，
    既保留 README 中的代码示例文案，又不会吞掉/破坏后续评论区 DOM。
    """
    import bleach

    try:
        return bleach.clean(
            html,
            tags=_README_TAGS,
            attributes=_README_ATTRS,
            protocols={"http", "https", "mailto"},
            strip=False,
            strip_comments=True,
        )
    except Exception:
        # 极端情况下退回正则兜底，至少移除可执行标签
        html = re.sub(r"<(script|style|iframe|object|embed)\b[^>]*>.*?</\1>", "", html, flags=re.I | re.S)
        return re.sub(r"\son\w+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.I)
