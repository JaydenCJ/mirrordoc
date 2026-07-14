# tinycache

[English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md)

A tiny in-memory cache used to demonstrate mirrordoc.

## Install

```bash
pip install tinycache
```

## Usage

```python
from tinycache import Cache

cache = Cache(max_items=128)
cache.set("greeting", "hello")
print(cache.get("greeting"))
```

## Options

| Option | Default | Effect |
|---|---|---|
| `max_items` | `128` | Evict least-recently-used entries beyond this |
| `ttl` | `None` | Seconds before an entry expires |

## Roadmap

- Persistent backend
- Async API

See the [changelog](CHANGELOG.md) for release history.
