"""Slice 6 (issue #18): one step's HTML.

site.render_step(step) takes a site.Step (slice 5) and returns its section as a string, lines
joined with "\n":

    <section id="<step.id>" class="step <step.kind>">
    <div class="exchange">
    ...the exchange part, below...
    </div>
    <div class="post">...the runs, below...</div>
    </section>

The exchange part, for an exchange step, one line each:
- <div class="model">model</div>, left out when the model is None;
- <div class="prompt">prompt</div>;
- <div class="reply">reply</div>;
- for each tool: <details class="tool"><summary>summary</summary><pre>detail</pre></details>.
For any other step, one line, <p class="note">text</p>, where text is:
- writer: "The writer's own editing."
- mixed: "The writer's editing, split from the AI's by matching."
- withheld: "<n> exchanges withheld by the writer." ("1 exchange ..." for one), n being the
  number at the start of the step's label;
- published: the label and a full stop ("Published v1.").

The runs, joined with nothing between them:
- kept: <span class="<by>">text</span>
- added: <ins class="<by>">text</ins>, and a writer's added run starts with the marker:
  <ins class="writer"><span class="mark">✎</span>text</ins>
- removed: <del class="<by>">text</del>

Every piece of text from the trace (model, prompt, reply, summary, detail, run text) is escaped
with html.escape(text, quote=True). Nothing else is.
"""

import html

from ledger.site import Run, Step, render_step


def ex(id="x1", prompt="Draft it.", reply="Here.", tools=(), model="claude-opus-5-5"):
    return {"type": "exchange", "id": id, "at": "2026-11-11T09:00:00Z", "source": "claude-code",
            "model": model, "prompt": prompt, "reply": reply, "tools": list(tools)}


def test_an_exchange_step_whole():
    step = Step("exchange", "x1", "x1", ex(), [Run("Hello world.", "ai", "added")])
    assert render_step(step) == "\n".join([
        '<section id="x1" class="step exchange">',
        '<div class="exchange">',
        '<div class="model">claude-opus-5-5</div>',
        '<div class="prompt">Draft it.</div>',
        '<div class="reply">Here.</div>',
        '</div>',
        '<div class="post"><ins class="ai">Hello world.</ins></div>',
        '</section>',
    ])


def test_no_model_line_when_none():
    out = render_step(Step("exchange", "x1", "x1", ex(model=None), []))
    assert 'class="model"' not in out
    assert '<div class="post"></div>' in out


def test_tools_are_collapsed_lines():
    tools = [{"name": "Read", "summary": "Read: /p/post.md", "detail": '{\n "file_path": "/p/post.md"\n}\n\nText.'},
             {"name": "Bash", "summary": "Bash: ls", "detail": "{}"}]
    out = render_step(Step("exchange", "x1", "x1", ex(tools=tools), []))
    lines = out.split("\n")
    i = lines.index('<div class="reply">Here.</div>')
    assert lines[i + 1] == '<details class="tool"><summary>Read: /p/post.md</summary><pre>{'
    assert '</pre></details>\n<details class="tool"><summary>Bash: ls</summary><pre>{}</pre></details>\n</div>' in out
    assert "&quot;file_path&quot;: &quot;/p/post.md&quot;" in out


def test_runs_are_marked_by_who_and_what():
    runs = [Run("Kept AI. ", "ai", "kept"), Run("Kept mine. ", "writer", "kept"),
            Run("New AI. ", "ai", "added"), Run("New mine. ", "writer", "added"),
            Run("Gone. ", "ai", "removed"), Run("Gone mine.", "writer", "removed")]
    out = render_step(Step("writer", "edit-1", "✎", None, runs))
    assert ('<div class="post">'
            '<span class="ai">Kept AI. </span>'
            '<span class="writer">Kept mine. </span>'
            '<ins class="ai">New AI. </ins>'
            '<ins class="writer"><span class="mark">✎</span>New mine. </ins>'
            '<del class="ai">Gone. </del>'
            '<del class="writer">Gone mine.</del>'
            '</div>') in out


def test_notes_for_other_steps():
    def note(step):
        lines = render_step(step).split("\n")
        assert lines[0] == f'<section id="{step.id}" class="step {step.kind}">'
        assert lines[1] == '<div class="exchange">' and lines[3] == "</div>"
        return lines[2]
    assert note(Step("writer", "edit-1", "✎", None, [])) == '<p class="note">The writer&#x27;s own editing.</p>'
    assert note(Step("mixed", "edit-2", "✎", None, [])) == '<p class="note">The writer&#x27;s editing, split from the AI&#x27;s by matching.</p>'
    assert note(Step("withheld", "withheld-1", "2 withheld", None, [])) == '<p class="note">2 exchanges withheld by the writer.</p>'
    assert note(Step("withheld", "withheld-2", "1 withheld", None, [])) == '<p class="note">1 exchange withheld by the writer.</p>'
    assert note(Step("published", "v1", "Published v1", None, [])) == '<p class="note">Published v1.</p>'


def test_everything_from_the_trace_is_escaped():
    bad = '<script>alert("x")</script> & \'q\''
    tools = [{"name": "Bash", "summary": bad, "detail": bad}]
    step = Step("exchange", "x1", "x1", ex(prompt=bad, reply=bad, tools=tools, model=bad),
                [Run(bad, "ai", "kept"), Run(bad, "writer", "added"), Run(bad, "ai", "removed")])
    out = render_step(step)
    assert "<script>" not in out
    assert out.count(html.escape(bad, quote=True)) == 8


def test_newlines_kept_in_text():
    out = render_step(Step("exchange", "x1", "x1", ex(reply="One.\n\nTwo."), [Run("A.\n\nB.", "ai", "kept")]))
    assert '<div class="reply">One.\n\nTwo.</div>' in out
    assert '<span class="ai">A.\n\nB.</span>' in out
