"""项目语言展示辅助。"""

from __future__ import annotations

_LANG_COLORS = {
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Python": "#3572A5",
    "Go": "#00ADD8", "Rust": "#dea584", "Java": "#b07219", "C": "#555555",
    "C++": "#f34b7d", "C#": "#178600", "HTML": "#e34c26", "CSS": "#563d7c",
    "Shell": "#89e051", "PowerShell": "#012A60", "Vue": "#41b883", "Ruby": "#701516",
    "PHP": "#4F5D95", "Swift": "#F05138", "Kotlin": "#A97BFF", "Dart": "#00B4AB",
    "Lua": "#000080", "Dockerfile": "#384d54", "Makefile": "#427819", "R": "#198CE7",
    "Objective-C": "#438eff", "Scala": "#c22d40", "Perl": "#0298c3", "Haskell": "#5e5086",
    "Elixir": "#6e4a7e", "Clojure": "#db5855", "Racket": "#3c5caa", "Assembly": "#6E4C13",
    "Zig": "#ec915c", "Nix": "#7e7eff", "YAML": "#cb171e", "JSON": "#292929",
    "MATLAB": "#e16737", "SQL": "#e38c00", "TeX": "#3D6117", "Vim Script": "#199f4b",
    "Batchfile": "#C1F12E", "Groovy": "#4298b8", "Julia": "#a270ba", "OCaml": "#ef7a08",
}


def normalize_languages(raw: list[dict]) -> list[dict]:
    """按 GitHub 侧边栏规则归一化语言列表。

    GitHub 会隐藏四舍五入后为 0.0% 的极小语言，并用剩余语言重新计算
    百分比。因此 file-collector 的 JavaScript 是 90.5%，而不是按全量
    字节直接算出的 90.4%；Go / PowerShell 也不会出现。
    """
    parsed: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            bytes_ = int(item.get("bytes") or 0)
        except (TypeError, ValueError):
            bytes_ = 0
        try:
            percent = float(item.get("percent") or 0)
        except (TypeError, ValueError):
            percent = 0.0
        parsed.append({"name": name, "bytes": bytes_, "percent": percent})

    total_bytes = sum(item["bytes"] for item in parsed)
    if total_bytes > 0:
        visible: list[dict] = []
        for item in parsed:
            raw_percent = item["bytes"] / total_bytes * 100 if item["bytes"] else item["percent"]
            if round(raw_percent, 1) >= 0.1:
                visible.append(item)
        visible_bytes = sum(item["bytes"] for item in visible)
        for item in visible:
            if item["bytes"] and visible_bytes:
                item["percent"] = round(item["bytes"] / visible_bytes * 100, 1)
            else:
                item["percent"] = round(item["percent"], 1)
    else:
        visible = [item for item in parsed if round(item["percent"], 1) >= 0.1]

    visible.sort(key=lambda item: (-item["bytes"], -item["percent"], item["name"].lower()))
    return visible


def _project_languages(project: dict) -> list[dict]:
    """兼容数据库中的 dict / 旧版 list 语言结构。"""
    raw: list[dict] = []
    languages = project.get("languages") or []
    if not isinstance(languages, list):
        return raw
    for item in languages:
        if isinstance(item, dict):
            raw.append(item)
        elif isinstance(item, (list, tuple)) and item:
            raw.append({
                "name": str(item[0]),
                "bytes": 0,
                "percent": float(item[1]) if len(item) > 1 else 100.0,
            })
        elif item:
            raw.append({"name": str(item), "bytes": 0, "percent": 100.0})
    return raw


def color(name: str) -> str:
    return _LANG_COLORS.get(name or "", "#8b949e")


def decorate(project: dict) -> dict:
    normalized = normalize_languages(_project_languages(project))
    items = [[item["name"], item["percent"], color(item["name"])] for item in normalized]
    if not items and project.get("language"):
        items = [[project["language"], 100.0, color(project["language"])]]
    project["lang_list"] = items
    project["lang_names"] = ",".join(item[0] for item in items)
    return project


def tally(projects: list[dict]) -> dict[str, int]:
    """与 PHP Lang::tally 一致：统计全部语言出现次数，保持首次出现顺序。"""
    counts: dict[str, int] = {}
    for project in projects:
        for item in project.get("lang_list") or []:
            name = item[0]
            counts[name] = counts.get(name, 0) + 1
    return counts
