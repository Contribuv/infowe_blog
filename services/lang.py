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


def color(name: str) -> str:
    return _LANG_COLORS.get(name or "", "#8b949e")


def decorate(project: dict) -> dict:
    languages = project.get("languages") or []
    items: list[list] = []
    if isinstance(languages, list):
        for item in languages:
            if isinstance(item, dict):
                name = str(item.get("name") or "")
                percent = float(item.get("percent") or 0)
            elif isinstance(item, (list, tuple)):
                name = str(item[0]) if item else ""
                percent = float(item[1]) if len(item) > 1 else 100.0
            else:
                name, percent = str(item or ""), 100.0
            if name:
                items.append([name, round(percent, 1), color(name)])
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
