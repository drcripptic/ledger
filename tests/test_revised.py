"""Slice 17 (issue #29): the revised note.

site.render(post_md, records) puts one line right after the <h1> line when the records hold more
than one "published" record:
    <p class="revised">Revised N time(s), last on D.</p>
N is the number of published records less one ("1 time", "2 times"); D is the last published
record's date, from its "at", written like "12 Nov 2026" (day without a leading zero, the
month's three-letter English name, the year). With one published record or none, no such line.
"""

from ledger.site import render

POST = "---\ntitle: T\n---\nText.\n"


def x(id):
    return {"type": "exchange", "id": id, "at": "2026-11-01T09:00:00Z", "source": "claude-code",
            "model": "claude-opus-5-5", "prompt": "P", "reply": "R", "tools": []}


def pub(v, at):
    return {"type": "published", "version": v, "at": at}


def after_h1(records):
    ls = render(POST, records).split("\n")
    return ls[ls.index("<h1>T</h1>") + 1]


def test_no_note_for_one_publish():
    assert 'class="revised"' not in render(POST, [x("x1"), pub(1, "2026-11-01T10:00:00Z")])
    assert 'class="revised"' not in render(POST, [x("x1")])


def test_revised_once():
    recs = [x("x1"), pub(1, "2026-11-01T10:00:00Z"), x("x2"), pub(2, "2026-11-05T10:00:00Z")]
    assert after_h1(recs) == '<p class="revised">Revised 1 time, last on 5 Nov 2026.</p>'


def test_revised_twice():
    recs = [x("x1"), pub(1, "2026-10-01T10:00:00Z"), pub(2, "2026-10-20T10:00:00Z"), x("x2"), pub(3, "2026-11-12T23:59:59Z")]
    assert after_h1(recs) == '<p class="revised">Revised 2 times, last on 12 Nov 2026.</p>'
