"""把标题衬线字体做子集化，输出到主题静态目录。

用法（在项目根目录执行）：
    .venv\\Scripts\\python.exe tools\\subset_title_font.py            # 默认 wide
    .venv\\Scripts\\python.exe tools\\subset_title_font.py core       # 只保留现有标题用字

两种口径：
  core —— 只保留「现有文章标题 + 正文 h1~h4 标题行 + 页面固定标题」用到的字（约 170KB）。
          最小，但以后新标题出现没收录的字时会回退到系统宋体。
  wide —— 在 core 之上再加上全站正文出现过的所有汉字（约 340KB）。
          覆盖作者的写作词汇，新标题基本不会缺字，推荐日常使用。

源文件放在 tools/fonts/（不对外提供），产物写进 themes/tech/static/fonts/NotoSerifSC/。
产物文件名与源文件不同，天然绕开浏览器对旧字体的强缓存。

什么时候要重跑：
  新增文章后如果想 100% 命中，重跑一次即可（约 10 秒）。
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

SRC = ROOT / "tools" / "fonts" / "noto-serif-sc-900.woff2"
OUT_DIR = ROOT / "themes" / "tech" / "static" / "fonts" / "NotoSerifSC"
OUT = OUT_DIR / "noto-serif-sc-900.subset.woff2"

# 页面标题是写在模板里的固定文案，数据库取不到，这里显式列出
PAGE_TITLES = [
    "关于我", "文章归档", "开源项目", "友链", "圈子", "读者", "标签", "搜索",
    "全部文章", "页面不存在", "服务器错误", "无权限访问", "内部错误",
    "评论", "精选推荐", "最新文章", "相关推荐",
]

# ASCII 可打印字符 + 中文全角标点 + 常用符号 + 全角数字
EXTRA = (
    "".join(chr(c) for c in range(0x20, 0x7F))
    + "，。、；：？！“”‘’「」『』（）《》〈〉【】〔〕—…·～％＋－＝／＼｜＃＆＊＠＜＞　０１２３４５６７８９"
)


def collect(mode: str) -> set[str]:
    conn = sqlite3.connect(config.DATABASE)
    try:
        rows = conn.execute(
            "SELECT title, content FROM posts WHERE deleted_at IS NULL"
        ).fetchall()
    finally:
        conn.close()

    chars: set[str] = set(EXTRA)
    for title, content in rows:
        chars.update(str(title or ""))
        for line in str(content or "").split("\n"):
            m = re.match(r"^\s{0,3}(#{1,4})\s+(.*)$", line)
            if m:
                chars.update(m.group(2))
        if mode == "wide":
            chars.update(str(content or ""))
    for t in PAGE_TITLES:
        chars.update(t)

    return {ch for ch in chars if ch.isprintable() and not ch.isspace()}


def main() -> None:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    mode = (sys.argv[1] if len(sys.argv) > 1 else "wide").strip().lower()
    if mode not in {"core", "wide"}:
        print("用法: python tools/subset_title_font.py [core|wide]")
        raise SystemExit(2)

    if not SRC.exists():
        print(f"找不到源字体：{SRC}")
        print("请把完整的 noto-serif-sc-900.woff2 放到 tools/fonts/ 下再运行。")
        raise SystemExit(1)

    chars = collect(mode)
    font = TTFont(SRC)
    cmap = font.getBestCmap()
    keep = sorted(ch for ch in chars if ord(ch) in cmap)
    missing = sorted(ch for ch in chars if ord(ch) not in cmap)
    print(f"[{mode}] 需要 {len(chars)} 字，字体覆盖 {len(keep)} 字，缺 {len(missing)} 字")
    if missing:
        print("  缺失（这些字在任何字体下都会回退，多为 emoji/符号）：", "".join(missing[:60]))

    opts = subset.Options()
    opts.flavor = "woff2"
    opts.desubroutinize = True
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_legacy = True
    opts.notdef_outline = True
    opts.recalc_bounds = True
    # 竖排/基线表对横向标题无用，去掉能再省一点
    opts.drop_tables += ["BASE", "vhea", "vmtx", "STAT"]

    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(unicodes=[ord(ch) for ch in keep])
    subsetter.subset(font)
    font.flavor = "woff2"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font.save(OUT)

    before = SRC.stat().st_size
    after = os.path.getsize(OUT)
    print(f"输出：{OUT.relative_to(ROOT)}")
    print(f"体积：{before/1024:.0f} KB -> {after/1024:.0f} KB（缩小 {(1-after/before)*100:.0f}%）")


if __name__ == "__main__":
    main()
