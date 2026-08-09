## 基础回顾

先快速回顾一下最基本的装饰器：

```python
def my_decorator(func):
    def wrapper(*args, **kwargs):
        print("Before")
        result = func(*args, **kwargs)
        print("After")
        return result
    return wrapper

@my_decorator
def say_hello(name):
    print(f"Hello, {name}!")
```

这很简单。下面是真正让你进阶的用法。

### 1. 带参数的装饰器

需要三层嵌套：

```python
def retry(max_attempts=3, delay=1):
    """失败自动重试的装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    print(f"重试 {attempt+1}/{max_attempts}...")
                    time.sleep(delay)
        return wrapper
    return decorator

@retry(max_attempts=5, delay=2)
def unstable_api_call():
    ...
```

### 2. 类装饰器

当装饰器需要维护状态时，用类更优雅：

```python
class CountCalls:
    def __init__(self, func):
        self.func = func
        self.count = 0
    
    def __call__(self, *args, **kwargs):
        self.count += 1
        print(f"第 {self.count} 次调用 {self.func.__name__}")
        return self.func(*args, **kwargs)

@CountCalls
def process_data():
    ...
```

### 3. 保留函数元信息

不用 `functools.wraps` 会丢失 `__name__` 和 `__doc__`：

```python
from functools import wraps

def log(func):
    @wraps(func)  # 关键！
    def wrapper(*args, **kwargs):
        print(f"调用 {func.__name__}")
        return func(*args, **kwargs)
    return wrapper
```

### 4. 方法装饰器

装饰类方法时要注意 `self`：

```python
def validate_price(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if self.price < 0:
            raise ValueError("价格不能为负")
        return method(self, *args, **kwargs)
    return wrapper

class Product:
    def __init__(self, price):
        self.price = price
    
    @validate_price
    def apply_discount(self, percent):
        self.price *= (1 - percent)
```

### 5. 可选的装饰器

有时想按条件启用：

```python
def conditional_decorator(condition, decorator):
    return decorator if condition else lambda f: f

DEBUG = True

@conditional_decorator(DEBUG, log)
def complex_calculation():
    ...
```

### 6. 注册模式

装饰器最强大的用法之一——自动注册：

```python
handlers = {}

def register(event_type):
    def decorator(func):
        handlers[event_type] = func
        return func
    return decorator

@register("user.created")
def handle_user_created(data):
    send_welcome_email(data["email"])

@register("order.paid")  
def handle_order_paid(data):
    update_inventory(data["items"])

# 使用时：
handlers[event.event_type](event.data)
```

### 7. 带缓存的属性

```python
class cached_property:
    def __init__(self, func):
        self.func = func
        self.name = func.__name__
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        value = self.func(instance)
        instance.__dict__[self.name] = value
        return value

class DataAnalyzer:
    @cached_property
    def expensive_result(self):
        print("计算中...（仅执行一次）")
        return sum(i*i for i in range(10_000_000))
```

## 结语

装饰器是 Python 最优雅的特性之一。掌握这些进阶用法，你的代码将更加 Pythonic。
