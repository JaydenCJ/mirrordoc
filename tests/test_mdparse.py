"""Tests for the structural Markdown parser.

Each test isolates one construct the comparison engine depends on; edge
cases (fences hiding headings, code spans hiding links, escaped pipes)
matter because a parser asymmetry would surface as a false drift finding.
"""

from mirrordoc.mdparse import parse


def test_atx_headings_levels_and_lines():
    doc = parse("# one\n\n## two\n\n###### six\n")
    assert [(h.level, h.text, h.line) for h in doc.headings] == [
        (1, "one", 1),
        (2, "two", 3),
        (6, "six", 5),
    ]


def test_atx_edge_cases():
    # Trailing closing hashes are stripped; 7 hashes and `#5` are not headings.
    assert parse("## title ##\n").headings[0].text == "title"
    assert parse("####### nope\n").headings == []
    assert parse("#5 bolt\n").headings == []  # CommonMark: needs a space


def test_setext_headings_vs_thematic_break():
    doc = parse("Title\n=====\n\nSub\n---\n")
    assert [(h.level, h.text) for h in doc.headings] == [(1, "Title"), (2, "Sub")]
    # `---` after a blank line is a thematic break, not a setext underline.
    assert parse("para\n\n---\n").headings == []


def test_fence_language_content_and_tilde_variant():
    block = parse("```python\nx = 1\ny = 2\n```\n").code_blocks[0]
    assert (block.lang, block.content, block.line) == ("python", "x = 1\ny = 2", 1)
    tilde = parse("~~~text\nbody\n~~~~\n").code_blocks[0]  # longer close is fine
    assert (tilde.lang, tilde.content) == ("text", "body")
    # A heading-shaped line inside a fence is code, not structure.
    hidden = parse("```\n# not a heading\n```\n")
    assert hidden.headings == [] and len(hidden.code_blocks) == 1


def test_fence_closing_rules():
    # A backtick fence is not closed by tildes, and an unterminated fence is
    # still recorded so both sides agree on a truncated file.
    doc = parse("```\nline\n~~~\nstill code\n```\n")
    assert doc.code_blocks[0].content == "line\n~~~\nstill code"
    open_fence = parse("```bash\necho hi\n")
    assert open_fence.code_blocks[0].content == "echo hi"


def test_link_destination_forms():
    doc = parse(
        '[docs](https://example.test/docs "the docs")\n'
        "[wiki](https://example.test/A_(disambiguation))\n"
        "[spaced](<docs/user guide.md>)\n"
        "Visit <https://example.test/> now\n"
    )
    assert [(l.url, l.kind) for l in doc.links] == [
        ("https://example.test/docs", "inline"),  # title dropped
        ("https://example.test/A_(disambiguation)", "inline"),  # balanced parens
        ("docs/user guide.md", "inline"),  # angle-bracket destination
        ("https://example.test/", "autolink"),
    ]
    assert doc.links[0].text == "docs"


def test_reference_links_resolve_and_bare_brackets_do_not():
    doc = parse("[home][h]\n\nno [bracketed] definition\n\n[h]: https://example.test/home\n")
    kinds = {l.kind: l.url for l in doc.links}
    assert kinds["reference"] == "https://example.test/home"
    assert kinds["definition"] == "https://example.test/home"
    assert len(doc.links) == 2  # [bracketed] never became a link


def test_link_syntax_hidden_by_code_spans_and_escapes():
    doc = parse("use `[x](y)` literally, but [real](z.md) counts\n\\[not](a.md)\n")
    assert [l.url for l in doc.links] == ["z.md"]


def test_image_and_alt_text():
    doc = parse("![Demo shot](docs/assets/demo.svg)\n")
    assert doc.images[0].src == "docs/assets/demo.svg"
    assert doc.images[0].alt == "Demo shot"
    assert doc.links == []  # an image is not also a link


def test_table_shape_columns_rows_and_alignment():
    doc = parse("| a | b | c |\n|:--|:-:|--:|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n")
    table = doc.tables[0]
    assert (table.columns, table.rows) == (3, 2)


def test_table_cell_splitting_rules():
    # Escaped pipes never split cells; a header/delimiter width mismatch
    # means the lines are prose, not a table.
    doc = parse("| expr | out |\n|---|---|\n| `a \\| b` | ok |\n")
    assert (doc.tables[0].columns, doc.tables[0].rows) == (2, 1)
    assert parse("| a | b |\n|---|\n").tables == []


def test_links_inside_table_cells_are_collected():
    doc = parse("| tool | site |\n|---|---|\n| x | [x](https://example.test/x) |\n")
    assert [l.url for l in doc.links] == ["https://example.test/x"]


def test_list_items_bullet_and_ordered():
    doc = parse("- a\n- b\n1. c\n2) d\n* e\n+ f\n")
    markers = [li.marker for li in doc.list_items]
    assert markers == ["bullet", "bullet", "ordered", "ordered", "bullet", "bullet"]


def test_html_comments_single_and_multiline():
    doc = parse("before\n<!-- hidden note -->\nafter\n<!-- first\nsecond -->\n")
    assert [(c.text, c.line) for c in doc.comments] == [
        ("hidden note", 2),
        ("first\nsecond", 4),
    ]


def test_heading_syntax_inside_comment_is_ignored():
    doc = parse("<!--\n# not real\n-->\n# real\n")
    assert [h.text for h in doc.headings] == ["real"]


def test_blockquoted_heading_counts():
    doc = parse("> ## quoted heading\n")
    assert doc.headings[0].level == 2
    assert doc.headings[0].text == "quoted heading"


def test_crlf_input_parses_identically_and_lines_counted():
    unix = parse("# t\n\n```\nx\n```\n")
    dos = parse("# t\r\n\r\n```\r\nx\r\n```\r\n")
    assert unix.headings == dos.headings
    assert unix.code_blocks == dos.code_blocks
    assert unix.line_count == 5
    assert parse("").line_count == 0
