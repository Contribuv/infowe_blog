## 2026年了，我该选哪个？

Python Web 框架的战争从未停止。从最早的 Zope，到称霸多年的 Django，再到近年崛起的 FastAPI，选择似乎越来越难。

我在这两个框架上都有超过两年的生产经验，今天从四个维度做个全面对比。

### 性能对比

```python
# FastAPI - 异步非阻塞
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    result = await db.fetch_one(
        "SELECT * FROM items WHERE id = $1", item_id
    )
    return result
```

```python
# Django - 同步（也可用 async views）
def read_item(request, item_id):
    item = Item.objects.get(id=item_id)
    return JsonResponse({"name": item.name})
```

**基准测试**（100 并发，简单 JSON 响应）：
- FastAPI: ~30,000 req/s
- Django (WSGI): ~8,000 req/s
- Django (ASGI): ~18,000 req/s

FastAPI 的性能优势确实明显，但不是所有场景都需要这么高的吞吐。

### 开发体验

| 维度 | Django | FastAPI |
|------|--------|---------|
| 学习曲线 | 陡峭但值得 | 平缓 |
| 自动文档 | 需插件 | Swagger 原生集成 |
| 类型检查 | - | Pydantic 自动验证 |
| ORM | 强大的 Django ORM | SQLAlchemy（灵活） |
| Admin 后台 | 开箱即用 | 需要自己搭 |

### Django 的优势

1. **"全套方案"**：ORM、Admin、Auth、Session、模板引擎... 一条龙服务
2. **成熟生态**：15+ 年积累，插件应有尽有
3. **Django Admin**：CRUD 界面的王者，半小时搞定管理后台
4. **安全**：默认防御 XSS、CSRF、SQL 注入

```python
# Django Admin 只需几行配置
@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'created_at']
    search_fields = ['title', 'content']
```

### FastAPI 的优势

1. **极致的性能**：接近 Node.js 和 Go 的水平
2. **自动 API 文档**：Swagger UI + ReDoc 原生集成
3. **类型安全**：Pydantic 模型让数据验证变得优雅
4. **WebSocket 一等公民**：实时应用的首选

```python
from pydantic import BaseModel

class ItemCreate(BaseModel):
    name: str
    price: float
    tags: list[str] = []

@app.post("/items", response_model=ItemResponse)
async def create_item(item: ItemCreate):
    # 自动验证 + 自动文档 + 自动序列化
    ...
```

### 我的选择建议

- **内容网站 / CMS / 企业后台** → Django
- **API 服务 / 微服务 / 实时应用** → FastAPI
- **全栈应用** → Django + DRF 或 FastAPI + Jinja2（像这个博客）
- **数据科学 API** → FastAPI（配合 Pydantic 无敌）

### 最后

> 没有最好的框架，只有最适合的框架。

我个人的技术栈是：FastAPI 做 API 服务 + Django 做管理后台 + Jinja2 做页面渲染。三者各取所长，相得益彰。

你用什么？欢迎在评论区聊聊。
