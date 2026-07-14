# tinycache

[English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md)

一个用来演示 mirrordoc 的小型内存缓存。

## 安装

```bash
pip install tinycache
```

## 用法

```python
from tinycache import Cache

cache = Cache(max_items=128)
cache.set("问候", "你好")
print(cache.get("问候"))
```

## 选项

| 选项 | 默认值 | 效果 |
|---|---|---|
| `max_items` | `128` | 超过该数量时按 LRU 淘汰 |
| `ttl` | `None` | 条目过期前的秒数 |
