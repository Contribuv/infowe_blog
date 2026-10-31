"""极简 Hook 总线（预留插件扩展位，不加载外部插件）。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

_registry: dict[str, list[Callable[..., Any]]] = defaultdict(list)


def on(name: str, func: Callable[..., Any]) -> Callable[..., Any]:
    bucket = _registry[name]
    # 去重：插件停用后重新启用会再次订阅，避免同一回调重复执行
    if not any(item is func for item in bucket):
        bucket.append(func)
    return func


def emit(name: str, payload: Any) -> Any:
    current = payload
    for func in _registry.get(name, []):
        try:
            result = func(current)
        except Exception:  # 插件异常不影响主流程
            continue
        if result is not None:
            current = result
    return current
