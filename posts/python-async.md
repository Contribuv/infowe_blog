## 从同步到异步的进化之路

Python 的异步编程经历了漫长而痛苦的进化。让我们从头梳理这条路，理解每一步解决了什么问题。

### 第一阶段：同步阻塞

```python
import time

def fetch_data(url):
    time.sleep(1)  # 模拟网络请求
    return f"Data from {url}"

def main():
    urls = ["api/1", "api/2", "api/3"]
    results = [fetch_data(url) for url in urls]
    print(results)

# 耗时 3 秒
```

这是最原始的方式 — 一个任务做完才能做下一个。CPU 大量时间花在等待 I/O 上。

### 第二阶段：多线程

```python
from concurrent.futures import ThreadPoolExecutor

def fetch_data(url):
    time.sleep(1)
    return f"Data from {url}"

with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(fetch_data, urls))

# 耗时约 1 秒，但有 GIL 限制
```

多线程解决了并发问题，但 Python 的 GIL 让 CPU 密集型任务无法真正并行，线程切换也有开销。

### 第三阶段：回调函数（Callback Hell）

```python
def fetch_data(url, callback):
    def on_done():
        result = http_get(url)  # 伪代码
        callback(result)
    schedule(on_done)
```

回调解决了同步等待的问题，但导致了著名的"回调地狱"——嵌套的回调让代码难以阅读和维护。

### 第四阶段：生成器协程（yield from）

```python
import asyncio

@asyncio.coroutine
def fetch_data(url):
    response = yield from aiohttp_get(url)
    return response
```

Python 3.4 引入了 `asyncio` 和 `yield from` 语法，用生成器来模拟协程。这是一个巨大的进步，但写法仍然别扭。

### 第五阶段：async/await（现代方案）

```python
import asyncio
import aiohttp

async def fetch_data(session, url):
    async with session.get(url) as response:
        return await response.json()

async def main():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_data(session, f"api/{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)
        return results

asyncio.run(main())
```

这才是我们想要的！代码读起来像同步，性能像异步。

## 关键概念深入

### Event Loop（事件循环）

事件循环是 asyncio 的心脏。它在单线程中不断循环，检查哪些协程可以继续执行：

```python
async def task(name, delay):
    print(f"{name} 开始")
    await asyncio.sleep(delay)
    print(f"{name} 完成")
    return name

async def main():
    results = await asyncio.gather(
        task("A", 2),
        task("B", 1),
        task("C", 0.5),
    )
    print(f"结果: {results}")

# 输出:
# A 开始
# B 开始
# C 开始
# C 完成
# B 完成
# A 完成
# 结果: ['A', 'B', 'C']
```

### 什么时候该用 async？

| 场景 | 推荐方案 |
|------|----------|
| Web API 大量并发请求 | async + aiohttp |
| WebSocket 实时通信 | async |
| CPU 密集型计算 | 多进程 |
| 简单 CRUD 脚本 | 同步即可 |
| 数据库操作 | async（配合 asyncpg 等） |

## 总结

Python 异步编程从回调到 `async/await` 的进化，本质上是在**可读性**和**性能**之间寻找最优解。现在我们拥有的 `async/await` 语法，几乎完美地平衡了这两者。

记住：**"IO 密集用 async，CPU 密集用 multiprocessing"** — 这是 Python 并发编程的黄金法则。
