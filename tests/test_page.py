"""Slice 7 (issue #19): the replay page.

site.render(post_md, records) returns one static HTML page for a post, from its post.md text and
its trace's records (a header record, one with no "type", is skipped). Lines joined with "\n":

    <!doctype html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TITLE</title>
    <style>
    ...styles...
    </style>
    </head>
    <body>
    <h1>TITLE</h1>
    <nav class="row"><a href="#x1">x1</a> <a href="#edit-1">✎</a> ...</nav>
    <main>
    ...each step's section...
    </main>
    </body>
    </html>

- TITLE: the `title:` line of post.md's front matter (between a first line `---` and the next
  `---`), its value stripped and any one pair of surrounding quotes ("" or '') taken off;
  "Untitled" if there is none. Escaped with html.escape.
- The post shown is without its front matter: before site.steps, each snapshot record's text has
  a front matter block taken off (a first line "---" through the next line "---", and the blank
  lines right after it). Text with no such block is left as it is.
- The row: one link per step from site.steps(records), `<a href="#<id>"><label escaped></a>`,
  joined with one space.
- Each section is site.render_step(step), with one line put just before its closing
  `</section>`: `<nav class="move">PREV NEXT</nav>`, where PREV is `<a href="#<previous id>">Previous</a>`
  and NEXT is `<a href="#<next id>">Next</a>`, joined with one space; the first step has no
  PREV and the last no NEXT (so one step alone has an empty nav).
- The styles hold, each on its own line, these three rules, so only the step named in the
  address shows, and the last step when none is named:
      .step { display: none; }
      .step:target, .step:last-of-type { display: block; }
      .step:target ~ .step:last-of-type { display: none; }
  and whatever else the page needs to look right (decision 0003). No JavaScript and nothing
  loaded from another site: no <script>, no src= attribute, no "://" anywhere in the page
  outside the trace's own text.
"""

import html

from ledger.site import render, render_step, steps

POST = "---\ntitle: \"A post\"\nprivate: [x9]\n---\n\nText.\n"


def x(id, prompt="P", reply="R"):
    return {"type": "exchange", "id": id, "at": "2026-11-11T09:00:00Z", "source": "claude-code",
            "model": "claude-opus-5-5", "prompt": prompt, "reply": reply, "tools": []}


RECORDS = [
    {"ledger_trace": 1, "post": "a-post"},
    x("x1"),
    {"type": "snapshot", "by": "ai", "after": "x1", "text": "Text."},
    {"type": "snapshot", "by": "writer", "after": "x1", "text": "Text. Mine."},
    x("x2"),
    {"type": "published", "version": 1, "at": "2026-11-11T10:00:00Z"},
]


def lines():
    return render(POST, RECORDS).split("\n")


def test_head_and_title():
    ls = lines()
    assert ls[:6] == ['<!doctype html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
                      '<meta name="viewport" content="width=device-width, initial-scale=1">', '<title>A post</title>']
    assert '<h1>A post</h1>' in ls
    assert ls[-2:] == ['</body>', '</html>']


def test_title_forms():
    def title(md):
        return render(md, [x("x1")]).split("\n")[5]
    assert title("---\ntitle: Plain one  \n---\nText.") == "<title>Plain one</title>"
    assert title("---\ntitle: 'Single'\n---\n") == "<title>Single</title>"
    assert title("---\ntitle: Fish & <chips>\n---\n") == "<title>Fish &amp; &lt;chips&gt;</title>"
    assert title("No front matter.\ntitle: not this\n") == "<title>Untitled</title>"
    assert title("---\nprivate: [x1]\n---\ntitle: not this\n") == "<title>Untitled</title>"


def test_the_step_row():
    ls = lines()
    assert '<nav class="row"><a href="#x1">x1</a> <a href="#edit-1">✎</a> <a href="#x2">x2</a> <a href="#v1">Published v1</a></nav>' in ls
    assert ls.index('<h1>A post</h1>') < ls.index('<main>')


def test_sections_in_order_with_moves():
    page = render(POST, RECORDS)
    st = steps(RECORDS[1:])
    ids = [s.id for s in st]
    moves = []
    for i, s in enumerate(st):
        parts = []
        if i > 0:
            parts.append(f'<a href="#{ids[i - 1]}">Previous</a>')
        if i < len(st) - 1:
            parts.append(f'<a href="#{ids[i + 1]}">Next</a>')
        sec = render_step(s)
        assert sec.endswith("\n</section>")
        moves.append(sec[: -len("</section>")] + f'<nav class="move">{" ".join(parts)}</nav>\n</section>')
    assert "<main>\n" + "\n".join(moves) + "\n</main>" in page
    assert '<nav class="move"><a href="#x1">Previous</a> <a href="#x2">Next</a></nav>' in page


def test_one_step_has_an_empty_move():
    assert '<nav class="move"></nav>' in render(POST, [x("x1")])


def test_only_the_target_or_the_last_step_shows():
    ls = lines()
    s, e = ls.index("<style>"), ls.index("</style>")
    style = [l.strip() for l in ls[s:e]]
    for rule in (".step { display: none; }",
                 ".step:target, .step:last-of-type { display: block; }",
                 ".step:target ~ .step:last-of-type { display: none; }"):
        assert rule in style


def test_no_script_and_nothing_from_elsewhere():
    page = render(POST, RECORDS)
    assert "<script" not in page.lower()
    assert "src=" not in page
    assert "://" not in page


def test_trace_text_is_escaped_in_the_page():
    page = render(POST, [x("x1", prompt="<script>go()</script> http://x.example")])
    assert "<script" not in page
    assert html.escape("<script>go()</script>") in page


def test_front_matter_is_not_shown():
    recs = [x("x1"), {"type": "snapshot", "by": "ai", "after": "x1", "text": "---\ntitle: T\nprivate: [x9]\n---\n\nBody text.\n"},
            {"type": "snapshot", "by": "writer", "after": "x1", "text": "No front matter here.\n---\nnot: this\n---\n"}]
    page = render(POST, recs)
    assert "private: [x9]" not in page
    assert '<ins class="ai">Body text.\n</ins>' in page
    assert "not: this" in page
