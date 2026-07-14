# tinycache

[English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md)

mirrordoc のデモ用の小さなインメモリキャッシュです。

## インストール

```bash
pip install tinycache
```

## 使い方

```python
from tinycache import Cache

cache = Cache(max_items=128)
cache.set("greeting", "hello")
print(cache.get("greeting"))
```

## オプション

| オプション | デフォルト | 効果 |
|---|---|---|
| `max_items` | `128` | この数を超えると LRU で削除 |
| `ttl` | `None` | エントリが失効するまでの秒数 |

## ロードマップ

- 永続化バックエンド
- 非同期 API

リリース履歴は[変更履歴](CHANGELOG.md)を参照してください。
