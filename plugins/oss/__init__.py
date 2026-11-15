"""对象存储插件入口。

生命周期（对应 services/plugins.py 的约定）：

- ``register(app)``：只注册后台路由，启动时总会执行；
- ``on_enable(app)``：把发布函数挂到 services.upload 的远端钩子上；
- ``on_disable(app)``：先摘钩子（立即恢复本地上传），再把数据库里的
  OSS 地址批量改回 ``/uploads/...``。

「停用即恢复原状」是两个动作共同保证的：
摘钩子保证之后的上传不再走对象存储；回写保证历史内容不再引用 OSS。
"""

from __future__ import annotations


def _publish(local_path, rel_url: str) -> str:
    """模块级函数：注册与注销必须是同一个引用，不能每次新建闭包。"""
    from . import storage

    return storage.publish(local_path, rel_url)


# 让核心的 remote_active() 能判断「已启用但配置不完整」的情况：
# 配置不完整时上传本来就会回退本地，孤儿清理不应被误伤。
def _is_active() -> bool:
    from . import storage

    return storage.is_enabled()


_publish.is_active = _is_active


def _url_for(rel_url: str) -> str:
    """只生成目标 URL，不上传；供核心代码把已存在的文件换成远端地址。"""
    from . import storage

    return storage.url_for(rel_url)


_publish.url_for = _url_for


def _ensure(local_path, rel_url: str) -> str:
    """本地已有文件时，确保远端也有一份（不存在才传）。"""
    from . import storage

    return storage.ensure_remote(local_path, rel_url)


_publish.ensure = _ensure


def _rewrite_html(html: str) -> str:
    """把页面里的 /uploads/... 换成当前策略的最终地址。"""
    from . import storage

    return storage.rewrite_html(html)


_publish.rewrite_html = _rewrite_html


def _normalize_text(text: str) -> str:
    """保存前把 OSS 直链 / 预签名 URL / 代理路径剥回 /uploads/...。"""
    from . import storage

    return storage.normalize_text(text)


_publish.normalize = _normalize_text


def register(app) -> None:
    from . import routes

    routes.register(app)


def _ensure_schema() -> None:
    """建对象清单表（幂等）。迁移与上传都会往里记，孤儿扫描只认这里。"""
    from pathlib import Path

    from db import get_db

    sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    conn = get_db()
    conn.executescript(sql)
    conn.commit()


def on_enable(app) -> None:
    from services import upload

    _ensure_schema()
    upload.register_remote(_publish)
    app.logger.info("对象存储插件已启用：新上传会同步到 OSS")


def on_disable(app) -> None:
    from services import upload

    # 先摘钩子：哪怕下面的回写失败，后续上传也已经回到本地规则
    upload.unregister_remote(_publish)

    from . import storage

    try:
        stats = storage.rewrite_db("local")
        app.logger.info(
            "对象存储插件已停用：回写 %s 行 / %s 处引用，备份 %s",
            stats.get("rows", 0), stats.get("refs", 0), stats.get("backup") or "无",
        )
    except Exception:  # noqa: BLE001
        app.logger.exception("对象存储停用回写失败，地址仍指向 OSS，请手动运行回写")
