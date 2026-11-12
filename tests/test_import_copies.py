"""Slice 13 (issue #25): import the copies.

import_claude_code (slice 3) also reads <root>/<slug>/.ledger/snapshots.jsonl, the copies the
hooks saved (slice 11), and writes snapshot records:
    {"type": "snapshot", "by": "ai" | "writer" | "mixed", "after": <exchange id or None>, "text": ...}
and nothing else: no session id, no path, no time.

The hooks' numbers: a prompt copy's n counts the prompts before that prompt; a stop copy's n
counts them including it. A session's transcript is the one whose file name (without .jsonl)
is the session id, and exchange n of it is the one exchanges() numbers n.

Changes: go through the copies in file order, each compared with the copy before it in the file
(the first with ""). Where the text is unchanged, nothing. Otherwise one snapshot, with text the
copy's text and:
- by: "ai" for a stop copy; "writer" for a prompt copy; "mixed" for a prompt copy with
  "interrupted": true.
- after: the id of the copy's session's exchange n, if that exchange is one of the post's (shown
  or withheld); else the id of that session's latest exchange of the post numbered below n; else
  the id of the post's exchange just before that session's first exchange of the post (in the
  post's order); else None.

Where they go: each snapshot right after the record holding its "after" exchange (exchange or
withheld record), in copy order; snapshots with after None before every exchange.

Withheld stretches fold: all the snapshots between a withheld record and the next exchange
record become one snapshot: text the last one's text, after the last one's after, and by their
common by if they all have the same, else "mixed". So no in-between draft is written.

Appending: the trace only grows. For each "after" value, the snapshots already in the trace with
that after are the first ones of that after; only the ones beyond them are written, each placed as
above among the records being appended; one whose after record is already in the trace (or None)
goes before every new exchange or withheld record.
A re-import with no new exchange and no new copy changes nothing and returns 0 (the count
returned is still exchanges added).

No snapshots.jsonl: no snapshot records, exactly as in slice 3.
"""

import json
from pathlib import Path

from ledger.importer import import_claude_code


def at(minute, second=0):
    return f"2026-11-12T09:{minute:02d}:{second:02d}.500Z"


def turn(text, minute):
    return [{"type": "user", "timestamp": at(minute), "message": {"role": "user", "content": text}},
            {"type": "assistant", "timestamp": at(minute, 10),
             "message": {"role": "assistant", "model": "claude-opus-5-5", "content": [{"type": "text", "text": "Re: " + text}]}}]


def session(root, sid, *prompts, start=0):
    p = root / "claude" / f"{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    recs = [r for i, t in enumerate(prompts) for r in turn(t, start + i)]
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return p


def cp(event, n, text, sid="s1", interrupted=False):
    c = {"event": event, "at": "2026-11-12T09:00:00Z", "session_id": sid, "n": n, "text": text}
    if event == "prompt":
        c["interrupted"] = interrupted
    return c


def save(root, copies, slug="a-post"):
    d = root / slug / ".ledger"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "snapshots.jsonl", "a") as f:
        for c in copies:
            f.write(json.dumps(c) + "\n")


def trace(root, slug="a-post"):
    return [json.loads(l) for l in (root / slug / "trace.jsonl").read_text().splitlines()][1:]


def short(records):
    out = []
    for r in records:
        if r["type"] == "exchange":
            out.append(r["id"])
        elif r["type"] == "withheld":
            out.append("w:" + ",".join(r["ids"]))
        elif r["type"] == "snapshot":
            out.append((r["by"], r["after"], r["text"]))
    return out


def snap(by, after, text):
    return {"type": "snapshot", "by": by, "after": after, "text": text}


def test_an_ai_change_and_a_writer_change(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "Draft it.", "Tighten it.")
    save(tmp_path, [cp("prompt", 0, ""), cp("stop", 1, ""),
                    cp("prompt", 1, ""), cp("stop", 2, "AI draft."),
                    cp("prompt", 2, "AI draft. Mine."), cp("stop", 3, "AI draft. Mine, tighter.")])
    assert import_claude_code("a-post", [t], tmp_path) == 2
    records = trace(tmp_path)
    assert short(records) == ["x1", ("ai", "x1", "AI draft."), ("writer", "x1", "AI draft. Mine."),
                              "x2", ("ai", "x2", "AI draft. Mine, tighter.")]
    for r in records:
        if r["type"] == "snapshot":
            assert set(r) == {"type", "by", "after", "text"}


def test_an_unchanged_stretch_writes_nothing(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "Draft it.", "Just talk.")
    save(tmp_path, [cp("prompt", 0, ""), cp("stop", 1, ""), cp("prompt", 1, ""), cp("stop", 2, "Text."),
                    cp("prompt", 2, "Text."), cp("stop", 3, "Text.")])
    import_claude_code("a-post", [t], tmp_path)
    assert short(trace(tmp_path)) == ["x1", ("ai", "x1", "Text."), "x2"]


def test_writing_before_the_first_prompt_comes_first(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "Go on.")
    save(tmp_path, [cp("prompt", 0, "Started by hand."), cp("stop", 1, "Started by hand."),
                    cp("prompt", 1, "Started by hand."), cp("stop", 2, "Started by hand. More.")])
    import_claude_code("a-post", [t], tmp_path)
    assert short(trace(tmp_path)) == [("writer", None, "Started by hand."), "x1", ("ai", "x1", "Started by hand. More.")]


def test_a_mixed_copy(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "Long draft.", "Shorter.")
    save(tmp_path, [cp("prompt", 0, ""), cp("stop", 1, ""), cp("prompt", 1, ""),
                    cp("prompt", 2, "Half a draft, and my words.", interrupted=True), cp("stop", 3, "Short.")])
    import_claude_code("a-post", [t], tmp_path)
    assert short(trace(tmp_path)) == ["x1", ("mixed", "x1", "Half a draft, and my words."), "x2", ("ai", "x2", "Short.")]


def test_copies_inside_and_after_a_withheld_stretch_fold(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "One.", "ledger private draft secret", "ledger private more", "Two.")
    save(tmp_path, [cp("prompt", 0, ""), cp("stop", 1, ""),
                    cp("prompt", 1, ""), cp("stop", 2, "Shown."),
                    cp("prompt", 2, "Shown."), cp("stop", 3, "Shown. Secret draft."),
                    cp("prompt", 3, "Shown. Secret draft."), cp("stop", 4, "Shown. Final."),
                    cp("prompt", 4, "Shown. Final, mine."), cp("stop", 5, "Shown. Final, mine. End.")])
    assert import_claude_code("a-post", [t], tmp_path) == 4
    assert short(trace(tmp_path)) == ["x1", ("ai", "x1", "Shown."), "w:x2,x3", ("mixed", "x3", "Shown. Final, mine."),
                                      "x4", ("ai", "x4", "Shown. Final, mine. End.")]
    assert "Secret" not in (tmp_path / "a-post" / "trace.jsonl").read_text()


def test_a_withheld_stretch_of_ai_changes_alone_stays_ai(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "ledger private a", "ledger private b", "Two.")
    save(tmp_path, [cp("prompt", 0, ""), cp("stop", 1, ""),
                    cp("prompt", 1, ""), cp("stop", 2, "Draft."),
                    cp("prompt", 2, "Draft."), cp("stop", 3, "Final."), cp("prompt", 3, "Final.")])
    import_claude_code("a-post", [t], tmp_path)
    assert short(trace(tmp_path)) == ["w:x1,x2", ("ai", "x2", "Final."), "x3"]


def test_no_copies(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "One.")
    import_claude_code("a-post", [t], tmp_path)
    assert short(trace(tmp_path)) == ["x1"]


def test_no_session_id_or_path_in_the_trace(tmp_path):
    sid = "9f1c2d3e-session"
    t = session(tmp_path, sid, "ledger start a-post", "One.")
    save(tmp_path, [cp("prompt", 0, "", sid=sid), cp("stop", 1, "", sid=sid), cp("prompt", 1, "", sid=sid), cp("stop", 2, "T.", sid=sid)])
    import_claude_code("a-post", [t], tmp_path)
    text = (tmp_path / "a-post" / "trace.jsonl").read_text()
    assert sid not in text and str(tmp_path) not in text and "snapshots.jsonl" not in text
    assert short(trace(tmp_path)) == ["x1", ("ai", "x1", "T.")]


def test_two_sessions_join_by_session_id(tmp_path):
    a = session(tmp_path, "sa", "ledger start a-post", "First.", "ledger end", start=0)
    b = session(tmp_path, "sb", "ledger start a-post", "Second.", start=20)
    save(tmp_path, [cp("prompt", 0, "", sid="sa"), cp("stop", 1, "", sid="sa"),
                    cp("prompt", 1, "", sid="sa"), cp("stop", 2, "A.", sid="sa"), cp("prompt", 2, "A.", sid="sa"),
                    cp("prompt", 0, "A. Between.", sid="sb"), cp("stop", 1, "A. Between.", sid="sb"),
                    cp("prompt", 1, "A. Between.", sid="sb"), cp("stop", 2, "A. Between. B.", sid="sb")])
    import_claude_code("a-post", [a, b], tmp_path)
    assert short(trace(tmp_path)) == ["x1", ("ai", "x1", "A."), ("writer", "x1", "A. Between."), "x2", ("ai", "x2", "A. Between. B.")]


def test_reimport_appends_only_new_copies(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "One.")
    save(tmp_path, [cp("prompt", 0, ""), cp("stop", 1, ""), cp("prompt", 1, ""), cp("stop", 2, "A.")])
    assert import_claude_code("a-post", [t], tmp_path) == 1
    before = (tmp_path / "a-post" / "trace.jsonl").read_text()
    assert import_claude_code("a-post", [t], tmp_path) == 0
    assert (tmp_path / "a-post" / "trace.jsonl").read_text() == before
    save(tmp_path, [cp("prompt", 2, "A. Mine.")])
    assert import_claude_code("a-post", [t], tmp_path) == 0
    t = session(tmp_path, "s1", "ledger start a-post", "One.", "Two.")
    save(tmp_path, [cp("stop", 3, "A. Mine. B.")])
    assert import_claude_code("a-post", [t], tmp_path) == 1
    assert short(trace(tmp_path)) == ["x1", ("ai", "x1", "A."), ("writer", "x1", "A. Mine."), "x2", ("ai", "x2", "A. Mine. B.")]


def test_a_start_with_no_exchange_yet_still_takes_its_copies(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post")
    save(tmp_path, [cp("prompt", 0, ""), cp("stop", 1, "Started.")])
    assert import_claude_code("a-post", [t], tmp_path) == 0
    assert short(trace(tmp_path)) == [("ai", None, "Started.")]


def test_a_new_copy_for_an_old_exchange_goes_before_the_new_records(tmp_path):
    t = session(tmp_path, "s1", "ledger start a-post", "One.")
    save(tmp_path, [cp("prompt", 0, ""), cp("stop", 1, ""), cp("prompt", 1, ""), cp("stop", 2, "A.")])
    import_claude_code("a-post", [t], tmp_path)
    session(tmp_path, "s1", "ledger start a-post", "One.", "ledger private a", "Two.")
    save(tmp_path, [cp("prompt", 2, "A. B."), cp("stop", 3, "A. B. C."), cp("prompt", 3, "A. B. C."), cp("stop", 4, "A. B. C. D.")])
    assert import_claude_code("a-post", [t], tmp_path) == 2
    assert short(trace(tmp_path)) == ["x1", ("ai", "x1", "A."),
                                      ("writer", "x1", "A. B."), "w:x2", ("ai", "x2", "A. B. C."),
                                      "x3", ("ai", "x3", "A. B. C. D.")]
