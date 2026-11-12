"""Slice 16 (issue #28): import with matching.

import_claude_code (slices 3 and 13) changes like this:

Save copies: snapshots.jsonl may also hold copies from `ledger watch` (slice 15):
{"event": "save", "at": ..., "text": ...}.
- If the file holds any hook copy ("prompt" or "stop"), save copies are skipped entirely: the
  hooks win.
- Otherwise each save copy is a change like a hook copy (compared with the copy before it in
  the file, the first with ""), with by "mixed" and after the id of the post's latest exchange
  (shown or withheld) whose "at" is at or before the copy's "at"; none: None. Placement,
  folding and appending are as in slice 13.

The AI's ranges: every snapshot record written with by "mixed" also gets
"ai": site.attribute(before, text, corpus), where:
- text is the record's text, and before is the text of the copy compared with (for a folded
  snapshot, the one compared with the stretch's first change);
- corpus is what the AI had written by the copy's "at" (for a folded snapshot, its last
  change's copy): in every transcript read, every assistant record (not isSidechain) whose
  timestamp, cut to whole seconds, is at or before that "at": its text blocks' text, and for
  each tool_use block every string in its input under the keys "content" and "new_string", at
  any depth (so MultiEdit's edits count), all joined with "\\n\\n". Tool results never count.
Records with by "ai" or "writer" get no "ai" key.

site.render: a snapshot's ranges are offsets into its full text; when render leaves out the
front matter, it moves them back by the length of what it left out (a range, or the part of
it, that falls inside the front matter is dropped).
"""

import json
from pathlib import Path

from ledger.importer import import_claude_code
from ledger.site import render

REPLY = "Rivers carve their valleys over many thousands of years, slowly and without any plan."
EDIT = "Cities grow along the rivers that first gave them water and trade."
OWN = "I walked down to the river this morning and thought about it."


def at(minute, second=0):
    return f"2026-11-12T09:{minute:02d}:{second:02d}.500Z"


def prompt(text, minute):
    return {"type": "user", "timestamp": at(minute), "message": {"role": "user", "content": text}}


def reply(minute, text, *tools):
    return {"type": "assistant", "timestamp": at(minute, 10),
            "message": {"role": "assistant", "model": "claude-opus-5-5", "content": [{"type": "text", "text": text}, *tools]}}


def turn(text, minute, answer=None):
    return [prompt(text, minute), reply(minute, answer or "Re: " + text)]


def session(root, sid, *turns):
    p = root / "claude" / f"{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for t in turns for r in t))
    return p


def save(root, copies, slug="a-post"):
    d = root / slug / ".ledger"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "snapshots.jsonl", "a") as f:
        for c in copies:
            f.write(json.dumps(c) + "\n")


def saved(minute, second, text):
    return {"event": "save", "at": f"2026-11-12T09:{minute:02d}:{second:02d}Z", "text": text}


def hook(event, n, minute, text, interrupted=False, sid="s1"):
    c = {"event": event, "at": f"2026-11-12T09:{minute:02d}:30Z", "session_id": sid, "n": n, "text": text}
    if event == "prompt":
        c["interrupted"] = interrupted
    return c


def snaps(root, slug="a-post"):
    rs = [json.loads(l) for l in (root / slug / "trace.jsonl").read_text().splitlines()][1:]
    return [r for r in rs if r["type"] == "snapshot"]


def test_save_copies_only(tmp_path):
    t = session(tmp_path, "s1", turn("ledger start a-post", 0), turn("Draft it.", 1, REPLY), turn("Shorter.", 2))
    text = REPLY + " And I add this."
    save(tmp_path, [saved(0, 30, "Title."), saved(1, 30, text), saved(1, 40, text)])
    assert import_claude_code("a-post", [t], tmp_path) == 2
    rs = [json.loads(l) for l in (tmp_path / "a-post" / "trace.jsonl").read_text().splitlines()][1:]
    assert [(r["type"], r.get("after"), r.get("text")) for r in rs] == [
        ("snapshot", None, "Title."), ("exchange", None, None), ("snapshot", "x1", text), ("exchange", None, None)]
    assert rs[0] == {"type": "snapshot", "by": "mixed", "after": None, "text": "Title.", "ai": []}
    assert rs[2]["by"] == "mixed"
    assert rs[2]["ai"] == [[0, text.index("And")]]


def test_a_mixed_hook_copy(tmp_path):
    t = session(tmp_path, "s1", turn("ledger start a-post", 0), turn("Draft it.", 1, REPLY), turn("Shorter.", 2))
    text = "Intro. " + REPLY + " " + OWN
    save(tmp_path, [hook("prompt", 0, 0, ""), hook("stop", 1, 0, ""), hook("prompt", 1, 1, "Intro."),
                    hook("prompt", 2, 1, text, interrupted=True), hook("stop", 3, 2, "Short.")])
    import_claude_code("a-post", [t], tmp_path)
    s = snaps(tmp_path)
    assert [(r["by"], r["after"]) for r in s] == [("writer", None), ("mixed", "x1"), ("ai", "x2")]
    assert "ai" not in s[0] and "ai" not in s[2]
    assert s[1]["ai"] == [[len("Intro. "), text.index(OWN)]]


def test_hooks_win_over_save_copies(tmp_path):
    t = session(tmp_path, "s1", turn("ledger start a-post", 0), turn("Draft it.", 1, REPLY))
    save(tmp_path, [hook("prompt", 0, 0, ""), saved(0, 40, "Typing."), hook("stop", 1, 0, ""),
                    hook("prompt", 1, 1, ""), saved(1, 20, "Half."), hook("stop", 2, 1, REPLY)])
    import_claude_code("a-post", [t], tmp_path)
    assert [(r["by"], r["after"], r["text"]) for r in snaps(tmp_path)] == [("ai", "x1", REPLY)]


def test_ai_text_only_in_a_file_edit(tmp_path):
    edit = {"type": "tool_use", "id": "t1", "name": "Edit",
            "input": {"file_path": "/p/a-post/post.md", "old_string": "x", "new_string": EDIT}}
    read = {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/p/a-post/post.md"}}
    result = {"type": "user", "timestamp": at(1, 20),
              "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": OWN}]}}
    t = session(tmp_path, "s1", turn("ledger start a-post", 0), [prompt("Add a line.", 1), reply(1, "Done.", edit, read), result])
    text = OWN + " " + EDIT
    save(tmp_path, [saved(1, 30, text)])
    import_claude_code("a-post", [t], tmp_path)
    [s] = snaps(tmp_path)
    assert s["ai"] == [[len(OWN) + 1, len(text)]]


def test_multi_edit_counts(tmp_path):
    edit = {"type": "tool_use", "id": "t1", "name": "MultiEdit",
            "input": {"file_path": "/p/post.md", "edits": [{"old_string": "a", "new_string": EDIT}]}}
    t = session(tmp_path, "s1", turn("ledger start a-post", 0), [prompt("Add.", 1), reply(1, "Done.", edit)])
    save(tmp_path, [saved(1, 30, EDIT)])
    import_claude_code("a-post", [t], tmp_path)
    assert snaps(tmp_path)[0]["ai"] == [[0, len(EDIT)]]


def test_text_the_ai_writes_later_is_not_matched(tmp_path):
    t = session(tmp_path, "s1", turn("ledger start a-post", 0), turn("Go.", 1), turn("Again.", 2, REPLY))
    save(tmp_path, [saved(1, 30, REPLY)])
    import_claude_code("a-post", [t], tmp_path)
    assert snaps(tmp_path)[0]["ai"] == []


def test_render_moves_ranges_past_the_front_matter():
    fm = "---\ntitle: T\n---\n"
    text = fm + "Mine. " + REPLY
    i = text.index("Rivers")
    records = [{"type": "exchange", "id": "x1", "at": "2026-11-12T09:01:00Z", "source": "claude-code",
                "model": "claude-opus-5-5", "prompt": "P", "reply": "R", "tools": []},
               {"type": "snapshot", "by": "mixed", "after": "x1", "text": text, "ai": [[0, 4], [i, len(text)]]}]
    page = render(fm + "Mine.", records)
    assert '<ins class="ai">' + REPLY + "</ins>" in page.replace("&#x27;", "'")
    assert '<span class="mark">✎</span>Mine. </ins>' in page


def test_a_tie_goes_after_the_latest_exchange(tmp_path):
    t = session(tmp_path, "s1", turn("ledger start a-post", 0), turn("One.", 1), turn("Two.", 1))
    save(tmp_path, [saved(1, 30, "Mine.")])
    import_claude_code("a-post", [t], tmp_path)
    assert [(r["by"], r["after"]) for r in snaps(tmp_path)] == [("mixed", "x2")]


def test_a_folded_mixed_copy_has_ranges(tmp_path):
    t = session(tmp_path, "s1", turn("ledger start a-post", 0), turn("One.", 1),
                turn("ledger private x", 2), turn("Two.", 3))
    save(tmp_path, [saved(1, 30, "Shown."), saved(2, 30, "Shown. Secret draft."), saved(2, 40, "Shown. Final.")])
    import_claude_code("a-post", [t], tmp_path)
    assert snaps(tmp_path)[1] == {"type": "snapshot", "by": "mixed", "after": "x2", "text": "Shown. Final.", "ai": []}
