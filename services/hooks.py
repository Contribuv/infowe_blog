"""极简 Hook 总线（预留插件扩展位，不加载外部插件）。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

_registry: dict[str, list[Callable[..., Any]]] = defaultdict(list)


def on(name: str, func: Callable[..., Any]) -> Callable[..., Any]:
    _registry[name].append(func)
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
