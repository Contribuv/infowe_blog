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


def _make(breaks: bool = True) -> md_lib.Markdown:
    # 文章正文保留单行换行；GitHub README 的软换行按空格处理，
    # 关闭 nl2br，否则多行徽章（badge）会被渲染成竖排。
    extensions = _EXTENSIONS if breaks else [e for e in _EXTENSIONS if e != "nl2br"]
    return md_lib.Markdown(
        extensions=extensions,
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
        # title 兜底：宽屏右侧 180px 悬浮目录会把长标题单行截断，悬停可看全
        parts.append(f'<li><a href="#{ident}" title="{text}">{text}</a>')
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


# ── Docusaurus / MkDocs 的 ::: 提示框兼容 ──
# 本站渲染器是 Python-Markdown，原生只认 !!! type "标题" 语法；
# 这里在解析前把 :::type[标题] ... ::: 转成 !!! 形式，方便直接粘贴外部文档。
_ADMONITION_ALIASES = {
    # 映射到现有的 4 套配色，避免出现没有样式的类型
    "note": "note", "info": "note", "abstract": "note", "summary": "note",
    "tldr": "note", "question": "note", "help": "note", "example": "note",
    "quote": "note", "cite": "note", "secondary": "note",
    "tip": "tip", "hint": "tip", "success": "tip", "check": "tip", "done": "tip",
    "warning": "warning", "caution": "warning", "attention": "warning", "important": "warning",
    "danger": "danger", "error": "danger", "failure": "danger", "fail": "danger",
    "missing": "danger", "bug": "danger",
}
_ADMONITION_OPEN_RE = re.compile(
    r"^[ \t]{0,3}:::[ \t]*([A-Za-z][\w-]*)(?:\[(.*?)\])?[ \t]*$"
)
_ADMONITION_CLOSE_RE = re.compile(r"^[ \t]{0,3}:::[ \t]*$")
_FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def _convert_colon_admonitions(text: str) -> str:
    """把 ::: 提示框转成 Python-Markdown 的 !!! 语法。

    逐行状态机，而不是简单正则替换，确保：
    - 围栏代码块（``` / ~~~）里的 ::: 原样保留，不会被误转；
    - 支持嵌套（每层内容多缩进 4 空格）；
    - 未知类型保留原名（结构正确，只是复用不到配色）。
    """
    if ":::" not in text:
        return text
    out: list[str] = []
    stack: list[str] = []   # 当前打开的提示框类型，length 即嵌套层数
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        fence_match = _FENCE_OPEN_RE.match(line)
        # 围栏代码块内：只补缩进，并检测闭合（同字符且长度不短于开启者）
        if fence is not None:
            out.append(("    " * len(stack) + line) if line.strip() else "")
            if (
                fence_match
                and fence_match.group(1)[0] == fence[0]
                and len(fence_match.group(1)) >= fence[1]
            ):
                fence = None
            continue
        if fence_match:
            fence = (fence_match.group(1)[0], len(fence_match.group(1)))
            out.append("    " * len(stack) + line)
            continue
        open_match = _ADMONITION_OPEN_RE.match(line)
        if open_match:
            kind = open_match.group(1).lower()
            title = (open_match.group(2) or "").strip()
            head = "    " * len(stack) + "!!! " + _ADMONITION_ALIASES.get(kind, kind)
            if title:
                # 标题用双引号包裹，内部引号转义成实体，避免提前闭合
                head += ' "' + title.replace('"', "&quot;") + '"'
            out.append(head)
            stack.append(kind)
            continue
        if _ADMONITION_CLOSE_RE.match(line) and stack:
            stack.pop()
            out.append("")   # 与后文留空行，避免块粘连
            continue
        if stack:
            out.append(("    " * len(stack) + line) if line.strip() else "")
        else:
            out.append(line)
    return "\n".join(out)


_DANGEROUS_TAGS = re.compile(
    r"<\s*(script|style|object|embed|form|iframe)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.I | re.S,
)

# 图片备注：alt 为空或用户常用的占位词时不显示
_IMG_ALT_RE = re.compile(r"""(?<![-\w])alt\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_CAPTION_EMPTY = {"", "null", "none", "undefined", "false", "为空", "为空null", "空"}
# 只处理「整段就是一张图（可带链接）」的段落，连续多图仍交给前端的画廊逻辑
_FIGURE_BLOCK_RE = re.compile(
    r"<p>\s*(?P<open><a\b[^>]*>\s*)?(?P<img><img\b[^>]*>)\s*(?P<close></a>)?\s*</p>",
    re.I | re.S,
)


def _image_caption(img_tag: str) -> str:
    """从 <img> 的 alt 里取备注；空值 / 占位词返回空字符串。"""
    match = _IMG_ALT_RE.search(img_tag or "")
    if not match:
        return ""
    raw = match.group(1) if match.group(1) is not None else match.group(2)
    text = html_lib.unescape(raw or "")
    text = re.sub(r"<[^>]+>", "", text).strip()
    if text.lower() in _CAPTION_EMPTY:
        return ""
    return text


def _decorate_figures(html: str) -> str:
    """把独立图片段落包成 figure，并在下方输出居中的图注（alt）。"""
    def repl(match: re.Match) -> str:
        img_tag = match.group("img")
        caption = _image_caption(img_tag)
        if not caption:
            return match.group(0)
        media = (match.group("open") or "") + img_tag + (match.group("close") or "")
        return (
            f'<figure class="md-figure">{media}'
            f'<figcaption class="md-figure-caption">{html_lib.escape(caption)}</figcaption>'
            "</figure>"
        )

    return _FIGURE_BLOCK_RE.sub(repl, html)


def _sanitize_post_html(html: str) -> str:
    """文章正文的危险标签兜底。

    管理员写的 HTML 默认信任，但导入外部文章/数据库被污染时，
    `<script>`、`onerror=`、`javascript:` 就会变成存储型 XSS。
    这里只删危险项，保留布局用的 div/span/details 等。
    """
    if not html:
        return html
    html = _DANGEROUS_TAGS.sub("", html)
    html = re.sub(r"<\s*(script|style|object|embed|form|iframe)\b[^>]*/?>", "", html, flags=re.I)
    html = re.sub(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.I)
    html = re.sub(
        r"""\b(href|src)\s*=\s*(["'])\s*(?:javascript|vbscript|data:text/html)[^"']*\2""",
        r'\1="#"',
        html,
        flags=re.I,
    )
    return html


def render_post(content: str) -> tuple[str, str]:
    if not (content or "").strip():
        return "", ""
    content = re.sub(r"^---.*?---\s*", "", content, count=1, flags=re.S)
    content = _convert_colon_admonitions(content)
    content = re.sub(r"<(https?://[^>\s]+)>", r"[\1](\1)", content)
    content = content.replace("[x]", '<i class="ck ck-done">✓</i> ').replace(
        "[ ]", '<i class="ck ck-todo">☐</i> '
    )
    parser = _make()
    html = parser.convert(content)
    html = _optimize_images(html)
    html = _harden_links(html)
    html = _sanitize_post_html(html)
    html = _decorate_figures(html)
    toc = _nest_toc(_filter_toc(getattr(parser, "toc_tokens", [])))
    return html, toc


def render_page(content: str) -> str:
    """后台预览：不生成额外目录。"""
    html, _ = render_post(content or "")
    return html


def render_readme(text: str, slug: str = "", branch: str = "main") -> str:
    if not (text or "").strip():
        return ""
    text = _convert_colon_admonitions(text)
    # GitHub README 常在 <details> 内写 Markdown；Python-Markdown 默认把块内当原始 HTML，
    # 显式加 markdown="1" 让 md_in_html 递归解析（与 GitHub / PHP 版一致）。
    text = re.sub(
        r"<details(?![^>]*\bmarkdown=)([^>]*)>",
        r'<details\1 markdown="1">',
        text,
        flags=re.I,
    )
    parser = _make(breaks=False)
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
        # 占位 alt（null / 为空null 等）清成空，灯箱与正文都不会把它当备注
        if _IMG_ALT_RE.search(tag) and not _image_caption(tag):
            tag = _IMG_ALT_RE.sub('alt=""', tag, count=1)
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
