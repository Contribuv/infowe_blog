"""批量改 app.py 里的 INSERT/UPDATE 语句：
把依赖 CURRENT_TIMESTAMP 的改成显式 _now()。
"""
with open('app.py', 'r', encoding='utf-8') as f:
    src = f.read()

# 1. INSERT INTO users — 加 created_at
src = src.replace(
    '''        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                   ('admin', hash_password('admin123')))''',
    '''        db.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                   ('admin', hash_password('admin123'), _now()))'''
)

# 2. UPDATE posts — updated_at=CURRENT_TIMESTAMP → 参数
src = src.replace(
    '               created_at=COALESCE(?, created_at), updated_at=CURRENT_TIMESTAMP WHERE id=?""",',
    '               created_at=COALESCE(?, created_at), updated_at=? WHERE id=?""",'
)
src = src.replace(
    '             created_at, post_id)',
    '             created_at, _now(), post_id)'
)

# 3. INSERT INTO posts — COALESCE(?, CURRENT_TIMESTAMP) 改 + 加 updated_at
src = src.replace(
    '''            """INSERT INTO posts (title, slug, content, excerpt, tags, is_featured, read_time, status, category_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            (form_data.get('title', ''), slug, content, excerpt,
             tags, is_featured, read_time, form_data.get('status', 'published'), category_id,
             created_at)''',
    '''            """INSERT INTO posts (title, slug, content, excerpt, tags, is_featured, read_time, status, category_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, ?), ?)""",
            (form_data.get('title', ''), slug, content, excerpt,
             tags, is_featured, read_time, form_data.get('status', 'published'), category_id,
             created_at, _now(), _now())'''
)

# 4. INSERT INTO categories — 加 created_at
src = src.replace(
    '''    db.execute("INSERT INTO categories (name, slug, sort_order) VALUES (?,?,?)",
               (name, slug, sort_order))''',
    '''    db.execute("INSERT INTO categories (name, slug, sort_order, created_at) VALUES (?,?,?,?)",
               (name, slug, sort_order, _now()))'''
)

# 5. UPDATE categories — 加 updated_at
src = src.replace(
    '''    db.execute("UPDATE categories SET name=?, slug=?, sort_order=? WHERE id=?",
               (name, slug, sort_order, cat_id))''',
    '''    db.execute("UPDATE categories SET name=?, slug=?, sort_order=?, updated_at=? WHERE id=?",
               (name, slug, sort_order, _now(), cat_id))'''
)

# 6. INSERT INTO projects — 加 created_at, updated_at
src = src.replace(
    '''            "INSERT INTO projects (name, description, url, stars, language, languages, topics, sort_order, featured, github_repo, custom_name) VALUES (?,?,?,?,?,?,?,?,?,?,?)",''',
    '''            "INSERT INTO projects (name, description, url, stars, language, languages, topics, sort_order, featured, github_repo, custom_name, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",'''
)
src = src.replace(
    "             (name, description, url, stars, language, languages, topics, sort_order, featured, github_repo, custom_name))",
    "             (name, description, url, stars, language, languages, topics, sort_order, featured, github_repo, custom_name, _now(), _now()))"
)

# 7. UPDATE projects — 加 updated_at（先读一下实际内容）

# 8. INSERT INTO links — 加 created_at
src = src.replace(
    '''        db.execute("INSERT INTO links (name, url, description, avatar, sort_order, status) VALUES (?,?,?,?,?,?)",
                   (name, url, description, avatar, sort_order, status))''',
    '''        db.execute("INSERT INTO links (name, url, description, avatar, sort_order, status, created_at) VALUES (?,?,?,?,?,?,?)",
                   (name, url, description, avatar, sort_order, status, _now()))'''
)

# 9. UPDATE links — 加 updated_at
src = src.replace(
    '''        db.execute("UPDATE links SET name=?, url=?, description=?, avatar=?, sort_order=? WHERE id=?",
                   (name, url, description, avatar, sort_order, link_id))''',
    '''        db.execute("UPDATE links SET name=?, url=?, description=?, avatar=?, sort_order=?, updated_at=? WHERE id=?",
                   (name, url, description, avatar, sort_order, _now(), link_id))'''
)

# 10. INSERT INTO timeline — 加 created_at
src = src.replace(
    '''            "INSERT INTO timeline (date, content, sort_order) VALUES (?, ?, ?)",''',
    '''            "INSERT INTO timeline (date, content, sort_order, created_at) VALUES (?, ?, ?, ?)",'''
)
src = src.replace(
    "            (date, content, sort_order))",
    "            (date, content, sort_order, _now()))"
)

# 11. UPDATE timeline — 加 updated_at
src = src.replace(
    '''        db.execute("UPDATE timeline SET date=?, content=?, sort_order=? WHERE id=?",
                   (date_str, content, sort_order, t_id))''',
    '''        db.execute("UPDATE timeline SET date=?, content=?, sort_order=?, updated_at=? WHERE id=?",
                   (date_str, content, sort_order, _now(), t_id))'''
)

# 验证：不应该再有 CURRENT_TIMESTAMP 出现在 SQL 里（除了可能的注释）
import re
remaining = re.findall(r'"[^"]*CURRENT_TIMESTAMP[^"]*"', src)
print("=== 剩余 CURRENT_TIMESTAMP SQL ===")
for m in remaining:
    print(f"  {m[:80]}...")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(src)
print(f"\n写完，文件大小: {len(src)} 字")
