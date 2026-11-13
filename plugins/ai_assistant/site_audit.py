"""友链站点体检：内容合规识别 + 访问速度测量。

设计原则：
1. **不依赖 AI**——纯本地规则，AI 没配模型时也能跑；
2. **只看客观信号**——域名后缀、成人分级标签、内容词命中数、外链密度、
   跳转行为、TTFB / 总耗时，全部可复现、可解释；
3. **宁可转人工，不自动放行**——自动审核只负责「排除」，
   把可疑站点挡在自动通过之外，由后台一键拒绝。

返回级别：
    blocked  明确违规或完全不可用，直接拒绝
    review   可疑或质量不达标，转人工确认
    ok       未发现风险
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

# ── 域名层：成人 / 赌博专用顶级域 ─────────────────────────
# 这类后缀本身就是内容分级声明，正常个人博客不会使用。
ADULT_TLDS = {"xxx", "porn", "sex", "adult", "sexy", "cam", "pornstar"}
GAMBLING_TLDS = {"bet", "casino", "poker", "bingo", "lotto"}

# 域名主体里的明确违规词（用 - . 分词后逐段比对，避免误伤含子串的正常域名）
ADULT_DOMAIN_WORDS = {
    "porn", "xxx", "sex", "adult", "nude", "hentai", "milf", "camgirl",
    "onlyfans", "jav",
}
GAMBLING_DOMAIN_WORDS = {
    "casino", "bet", "betting", "poker", "gamble", "slots", "baccarat",
}

# ── 内容层：中文词（整站页面文本命中）────────────────────
# 只收「站点性质」词，不收单个泛词，降低正常文章的误伤。
ADULT_WORDS = (
    "色情", "成人网站", "成人影片", "成人视频", "成人小说", "成人影视",
    "情色", "裸聊", "约炮", "一夜情", "性服务", "楼凤", "福利姬", "里番",
    "无码", "av女优", "淫秽", "嫖娼", "卖淫", "援交", "外围女",
    "黄片", "黄网", "成人片", "裸照",
)
GAMBLING_WORDS = (
    "赌博", "博彩", "六合彩", "时时彩", "棋牌", "赌场", "真人荷官",
    "百家乐", "老虎机", "体育投注", "押注", "洗码", "菠菜网", "网上赌",
)
FRAUD_WORDS = (
    "诈骗", "洗钱", "刷单", "套现", "代开发票", "办证", "无抵押贷款",
    "高利贷", "资金盘", "杀猪盘", "传销", "庞氏", "跑分",
)
# 引流类只作弱信号：正常博客也可能提到，不单独判违规
SPAM_WORDS = ("加微信", "加v", "日赚", "兼职赚钱", "引流", "刷量", "买粉", "点赞任务")

# ── 内容层：英文词（按词边界匹配）────────────────────────
# 注意：不单独匹配 xxx / nude / sex —— 技术博客里的占位符和正常词太多，
# 必须带上下文才计入（free xxx / xxx video 这类才是站点性质）。
ADULT_EN = re.compile(
    r"\b(porn|hentai|nsfw|milf|camgirl|onlyfans|erotic|escort\s+girl)\b"
    r"|\b(free\s+xxx|xxx\s+(?:video|tube|movie|porn|sex))\b",
    re.I,
)
GAMBLING_EN = re.compile(
    r"\b(casino|sportsbook|roulette|baccarat|slot\s+machine|gambling|bookmaker)\b", re.I
)

# 成人站点必须声明的分级标签（RTA / meta rating）
RTA_MARK = re.compile(r"RTA-5042|content\s*=\s*[\"']?\s*adult", re.I)

# meta refresh 跳转
META_REFRESH = re.compile(
    r"<meta[^>]+http-equiv\s*=\s*[\"']?refresh[\"']?[^>]*content\s*=\s*[\"'][^\"']*url\s*=\s*([^\"'>]+)",
    re.I,
)


class _PageParser(HTMLParser):
    """提取标题、正文、链接、iframe 数与 meta 信息。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.text: list[str] = []
        self.links: list[str] = []
        self.iframes = 0
        self.metas: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = attr.get("href") or ""
            if href:
                self.links.append(href)
        elif tag == "iframe":
            self.iframes += 1
        elif tag == "meta":
            self.metas.append(
                " ".join(f"{k}={v}" for k, v in attrs if v is not None)
            )

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title += text
        self.text.append(text)


def parse_page(html: str) -> dict:
    parser = _PageParser()
    try:
        parser.feed(html)
    except Exception:
        return {"title": "", "text": "", "links": [], "iframes": 0, "metas": []}
    return {
        "title": parser.title[:200],
        "text": " ".join(parser.text)[:20000],
        "links": parser.links,
        "iframes": parser.iframes,
        "metas": parser.metas,
    }


def is_safe_url(url: str) -> bool:
    """拦截内网 / 回环 / 链路本地地址，避免被当成 SSRF 跳板。"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        ip = socket.gethostbyname(parsed.hostname)
        addr = ipaddress.ip_address(ip)
        return not (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except Exception:
        return False


def _decode(raw: bytes) -> str:
    """按页面声明的 charset 解码，国内站点常见 gbk，直接 utf-8 会整页乱码。"""
    enc = "utf-8"
    match = re.search(rb"charset\s*=\s*[\"']?([\w-]+)", raw[:4096], re.I)
    if match:
        enc = match.group(1).decode("ascii", "ignore").lower()
    try:
        return raw.decode(enc, "ignore")
    except LookupError:
        return raw.decode("utf-8", "ignore")


def fetch(url: str, timeout: float = 8.0, max_bytes: int = 2 * 1024 * 1024):
    """抓取站点并计时。返回 (html, error, metrics)。"""
    metrics = {
        "dns_ms": 0, "ttfb_ms": 0, "total_ms": 0, "bytes": 0,
        "status": 0, "final_url": url, "redirect_host": "",
    }
    if not is_safe_url(url):
        return "", "地址不可访问或不合规", metrics

    host = (urlparse(url).hostname or "").lower()
    started = time.perf_counter()
    try:
        dns_start = time.perf_counter()
        socket.gethostbyname(host)
        metrics["dns_ms"] = int((time.perf_counter() - dns_start) * 1000)
    except OSError:
        metrics["dns_ms"] = -1

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            stream=True,
            allow_redirects=True,
            headers={"User-Agent": "infowe-link-check/1.0"},
        )
        metrics["ttfb_ms"] = int((time.perf_counter() - started) * 1000)
        metrics["status"] = resp.status_code
        metrics["final_url"] = resp.url or url
        final_host = (urlparse(resp.url or url).hostname or "").lower()
        if final_host and final_host.removeprefix("www.") != host.removeprefix("www."):
            metrics["redirect_host"] = final_host
        if resp.status_code >= 400:
            return "", f"站点返回 HTTP {resp.status_code}", metrics
        chunk = resp.raw.read(max_bytes + 1, decode_content=True) or b""
        metrics["bytes"] = len(chunk)
        metrics["total_ms"] = int((time.perf_counter() - started) * 1000)
        return _decode(chunk), "", metrics
    except requests.Timeout:
        metrics["total_ms"] = int((time.perf_counter() - started) * 1000)
        return "", "访问超时", metrics
    except requests.RequestException:
        metrics["total_ms"] = int((time.perf_counter() - started) * 1000)
        return "", "站点无法访问", metrics


def _host_verdict(url: str) -> list[str]:
    """域名层判定，返回命中的风险描述。"""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        return []
    tld = host.rsplit(".", 1)[-1]
    risks: list[str] = []
    if tld in ADULT_TLDS:
        risks.append(f"成人专用域名后缀 .{tld}")
    if tld in GAMBLING_TLDS:
        risks.append(f"博彩专用域名后缀 .{tld}")
    labels = set(re.split(r"[.\-]", host))
    if labels & ADULT_DOMAIN_WORDS:
        risks.append("域名含成人关键词")
    if labels & GAMBLING_DOMAIN_WORDS:
        risks.append("域名含博彩关键词")
    return risks


def _content_verdict(page: dict) -> tuple[list[str], int]:
    """内容层判定，返回 (风险描述列表, 强违规词命中数)。"""
    text = page.get("text") or ""
    title = page.get("title") or ""
    body = f"{title} {text}"
    risks: list[str] = []
    hard_hits = 0

    def collect(words, label: str) -> int:
        hits = [w for w in words if w in body]
        if hits:
            risks.append(f"内容命中{label}：{'、'.join(hits[:3])}")
        return len(hits)

    hard_hits += collect(ADULT_WORDS, "成人词")
    hard_hits += collect(GAMBLING_WORDS, "赌博词")
    hard_hits += collect(FRAUD_WORDS, "诈骗黑产词")
    spam_hits = collect(SPAM_WORDS, "引流词")
    if spam_hits and not risks:
        risks.append(f"内容疑似引流广告（{spam_hits} 处）")

    adult_en = [m.group(0) for m in ADULT_EN.finditer(body)]
    if adult_en:
        risks.append(f"内容命中英文成人词：{', '.join(sorted(set(adult_en))[:3])}")
        hard_hits += len(set(adult_en))
    gamble_en = [m.group(0) for m in GAMBLING_EN.finditer(body)]
    if gamble_en:
        risks.append(f"内容命中英文博彩词：{', '.join(sorted(set(gamble_en))[:3])}")
        hard_hits += len(set(gamble_en))

    metas = " ".join(page.get("metas") or [])
    if RTA_MARK.search(metas):
        risks.append("页面声明了成人分级标签（RTA / meta rating=adult）")
        hard_hits += 3
    return risks, hard_hits


def _structure_verdict(page: dict, html: str, metrics: dict) -> list[str]:
    risks: list[str] = []
    links = page.get("links") or []
    if len(links) > 300:
        risks.append(f"页面外链过多（{len(links)} 个），疑似链接农场")
    if (page.get("iframes") or 0) > 10:
        risks.append(f"页面 iframe 过多（{page['iframes']} 个）")
    if META_REFRESH.search(html):
        risks.append("页面使用 meta refresh 自动跳转")
    redirected = metrics.get("redirect_host") or ""
    if redirected and not re.search(r"(www\.)?(infowe|qq\.com|github)", redirected):
        risks.append(f"提交地址跳转到其它域名：{redirected}")
    if not (page.get("text") or "").strip() and len(html) > 3000:
        risks.append("页面几乎没有可读正文，疑似空壳站")
    return risks


def _speed_verdict(metrics: dict, cfg: dict) -> list[str]:
    risks: list[str] = []
    max_ttfb = int(cfg.get("link_max_ttfb_ms") or 4000)
    max_total = int(cfg.get("link_max_total_ms") or 10000)
    max_bytes = int(cfg.get("link_max_bytes") or 5 * 1024 * 1024)

    ttfb = metrics.get("ttfb_ms") or 0
    total = metrics.get("total_ms") or 0
    size = metrics.get("bytes") or 0
    if ttfb > max_ttfb:
        risks.append(f"响应偏慢：首字节 {ttfb / 1000:.1f}s（上限 {max_ttfb / 1000:.0f}s）")
    if total > max_total:
        risks.append(f"加载偏慢：总耗时 {total / 1000:.1f}s（上限 {max_total / 1000:.0f}s）")
    if size > max_bytes:
        risks.append(f"页面体积过大：{size / 1024 / 1024:.1f}MB")
    return risks


def audit(url: str, cfg: dict | None = None, timeout: float = 8.0) -> dict:
    """对一个站点做完整体检。

    返回 dict：
        level   blocked / review / ok
        reasons 人类可读的原因列表
        metrics 速度指标
        page    解析结果（title/text/links）
        error   抓取错误（若有）
    """
    cfg = cfg or {}
    host_risks = _host_verdict(url)
    max_bytes = int(cfg.get("link_max_bytes") or 5 * 1024 * 1024)
    if not is_safe_url(url):
        return {
            "level": "blocked",
            "reasons": host_risks + ["地址非法、无法解析或指向内网"],
            "metrics": {"dns_ms": 0, "ttfb_ms": 0, "total_ms": 0, "bytes": 0,
                        "status": 0, "final_url": url, "redirect_host": ""},
            "page": {"title": "", "text": "", "links": []},
            "error": "地址不可访问或不合规",
        }
    html, error, metrics = fetch(url, timeout=timeout, max_bytes=max_bytes)
    result = {
        "level": "ok",
        "reasons": [],
        "metrics": metrics,
        "page": {"title": "", "text": "", "links": []},
        "error": error,
    }
    if error:
        # 打不开的站点：违规后缀仍判违规，其余转人工（可能是临时故障）
        result["level"] = "blocked" if host_risks else "review"
        result["reasons"] = host_risks + [error]
        return result

    page = parse_page(html)
    result["page"] = page
    # 保留原始 HTML 供回链检测复用，避免再请求一次首页
    result["html"] = html
    content_risks, hard_hits = _content_verdict(page)
    structure_risks = _structure_verdict(page, html, metrics)
    speed_risks = _speed_verdict(metrics, cfg)
    reasons = host_risks + content_risks + structure_risks + speed_risks
    result["reasons"] = reasons

    # 明确违规：专用后缀 / 成人分级标签 / 多个强违规词同时命中
    hard = bool(host_risks) or hard_hits >= 3
    if hard:
        result["level"] = "blocked"
    elif reasons:
        result["level"] = "review"
    return result
