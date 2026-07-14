# The structure model

mirrordoc never renders Markdown and never machine-translates anything. It
reduces each file to a **skeleton** — the parts a translation must preserve —
and compares the two skeletons. This document is the exact contract.

## What a mirror must preserve

| Element | Compared as | Divergence | Severity |
|---|---|---|---|
| Headings | level sequence (text is free) | `heading-missing` / `heading-extra` / `heading-level` | error |
| Fenced code blocks | count, info language, byte content | `codeblock-count` / `codeblock-lang` / `codeblock-drift` | error |
| Tables | count and column count | `table-count` / `table-shape` | error |
| Tables | body row count | `table-rows` | warning |
| Links | multiset of destinations | `link-missing` | error |
| Links | extra destinations in the mirror | `link-extra` | warning |
| Images | destination sequence | `image-missing` / `image-extra` | error |
| List items | total count | `list-items` | warning |

Prose — paragraph text, heading titles, table cells, link anchor text, image
alt text — is never compared. That is the translation.

## Deliberate leniencies

- **Anchor fragments are ignored by default.** `[jump](#install)` and
  `[jump](#安装)` are equivalent, because translated headings produce
  different slugs. Opt back in with `"check_anchors": true`.
- **Localized links are equivalent.** A `zh` mirror linking `CHANGELOG.zh.md`
  satisfies a canonical link to `CHANGELOG.md`; the same applies to the
  directory convention (`docs/zh/guide.md` for `docs/guide.md`). The rewrite
  is applied only to otherwise-unmatched links, so a language-switcher line
  that names every translation still matches exactly.
- **`--lax-code`** drops the byte-content comparison for code blocks (some
  teams translate comments inside examples) while still requiring the same
  count and info language.

## Parsing rules and known simplifications

The parser is line-based and CommonMark-informed: ATX and setext headings,
backtick and tilde fences (including unterminated ones), GFM pipe tables with
escaped-pipe handling, inline/reference/autolink links, inline code spans
(which hide link syntax), HTML comments (which hide everything), and
blockquoted structure.

Two constructs are intentionally not modeled:

- **Indented (4-space) code blocks.** Fenced blocks are the norm in modern
  docs; indented blocks are parsed as prose.
- **Raw HTML blocks** other than comments.

Because the canonical file and the mirror are parsed by exactly the same
rules, these simplifications are symmetric: they can hide a difference inside
an unmodeled construct, but they can never report a false one.

## The sync marker

`mirrordoc stamp <mirror>` pins a mirror to the source's current commit:

```text
<!-- mirrordoc: source=README.md commit=<full sha> -->
```

The path is relative to the mirror (like a Markdown link). `mirrordoc check`
then asks git whether any later commit touched the source: if so, the mirror
is **stale** (`stale-marker`, error). Without a marker, the last commit dates
of the two files are compared instead (`stale-commit`, warning) — weaker
evidence, hence the lower severity. Outside a git repository, staleness is
skipped with a note and structure checking still works.
