# Advanced guide

Directory-style mirrors work too: this file's Japanese translation lives at
`docs/ja/guide.md` and is discovered automatically.

## Eviction

Entries are evicted least-recently-used first.

```bash
python -c "from tinycache import Cache; print(Cache(max_items=2))"
```
