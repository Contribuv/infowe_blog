"""项目模型。"""

from __future__ import annotations

import db
from models.base import json_dump, json_list, row_to_dict


def hydrate(row) -> dict:
    data = row_to_dict(row) or {}
    data["topics"] = json_list(data.get("topics"))
    data["languages"] = json_list(data.get("languages"))
    data["id"] = int(data.get("id") or 0)
    data["stars"] = int(data.get("stars") or 0)
    data["featured"] = int(data.get("featured") or 0)
    data["custom_name"] = int(data.get("custom_name") or 0)
    data["sort_order"] = int(data.get("sort_order") or 0)
    return data


def load() -> list[dict]:
    rows = db.query("SELECT * FROM projects ORDER BY sort_order ASC, created_at DESC")
    return [hydrate(r) for r in rows]


def get(project_id: int) -> dict | None:
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    return hydrate(row) if row else None


def repo_exists(repo: str, exclude_id: int | None = None) -> bool:
    if exclude_id is not None:
        return db.one(
            "SELECT 1 FROM projects WHERE github_repo = ? AND id != ?", (repo, exclude_id)
        ) is not None
    return db.one("SELECT 1 FROM projects WHERE github_repo = ?", (repo,)) is not None


def save(form: dict, project_id: int | None = None, keep_name: bool = False) -> int:
    name = (form.get("name") or "").strip()
    description = (form.get("description") or "").strip()
    url = (form.get("url") or "").strip()
    github_repo = (form.get("github_repo") or "").strip()
    topics = form.get("topics") or ""
    if isinstance(topics, str):
        topics_list = [t.strip() for t in topics.split(",") if t.strip()]
    else:
        topics_list = list(topics)
    languages = form.get("languages") or []
    if isinstance(languages, str):
        try:
            import json
            languages = json.loads(languages)
        except ValueError:
            languages = []
    sort_order = int(form.get("sort_order") or 0)
    featured = 1 if str(form.get("featured", "")) == "1" else 0
    custom_name = 1 if keep_name or str(form.get("custom_name", "")) == "1" else 0
    stars = int(form.get("stars") or 0)
    language = (form.get("language") or "").strip()

    if project_id is not None:
        db.execute(
            "UPDATE projects SET name=?, description=?, url=?, stars=?, language=?, "
            "topics=?, sort_order=?, featured=?, github_repo=?, custom_name=?, languages=? "
            "WHERE id=?",
            (name, description, url, stars, language, json_dump(topics_list), sort_order,
             featured, github_repo, custom_name, json_dump(languages), project_id),
        )
        return project_id
    return db.insert(
        "INSERT INTO projects (name, description, url, stars, language, topics, sort_order, "
        "featured, github_repo, custom_name, languages) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (name, description, url, stars, language, json_dump(topics_list), sort_order,
         featured, github_repo, custom_name, json_dump(languages)),
    )


def update_github(project_id: int, data: dict) -> None:
    db.execute(
        "UPDATE projects SET stars=?, language=?, topics=?, languages=?, description=?, "
        "github_repo=? WHERE id=?",
        (
            int(data.get("stars") or 0),
            data.get("language") or "",
            json_dump(data.get("topics") or []),
            json_dump(data.get("languages") or []),
            data.get("description") or "",
            data.get("github_repo") or "",
            project_id,
        ),
    )


def delete(project_id: int) -> None:
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def bulk(ids: list[int], action: str) -> int:
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    if action in {"delete", "remove"}:
        return db.execute(f"DELETE FROM projects WHERE id IN ({marks})", ids).rowcount
    if action in {"feature", "featured"}:
        return db.execute(f"UPDATE projects SET featured=1 WHERE id IN ({marks})", ids).rowcount
    if action in {"unfeature"}:
        return db.execute(f"UPDATE projects SET featured=0 WHERE id IN ({marks})", ids).rowcount
    return 0
