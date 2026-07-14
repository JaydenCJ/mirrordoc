# 上級ガイド

ディレクトリ方式のミラーも使えます。このファイルの日本語訳は
`docs/ja/guide.md` にあり、自動的に検出されます。

## 削除ポリシー

エントリは least-recently-used の順に削除されます。

```bash
python -c "from tinycache import Cache; print(Cache(max_items=2))"
```
