"""Slice 3 (issue #15): spans, ids and privacy.

ledger.importer.import_claude_code(slug, transcripts, root) imports one post's history from
Claude Code transcripts into <root>/<slug>/trace.jsonl, and returns how many exchanges it
added (withheld ones included). `ledger import-claude-code <slug> [transcript ...]` does the
same from the command line, with root the current folder, and prints nothing to stderr when
it succeeds.

Transcripts:
- The given transcript paths, plus every <root>/.ledger/transcripts/*.jsonl (saved copies).
- Files with the same name are copies of one session: only the longest (most lines) is read.
- Each is read with ledger.claude_code.exchanges(path).

Spans:
- A span starts at an exchange whose prompt's first three words are `ledger start <slug>`.
- It ends at the next exchange whose prompt's first two words are `ledger end`, or whose first
  two words are `ledger start` (any slug), or at the end of that transcript.
- Marker exchanges (`ledger start ...`, `ledger end ...`) are not part of the post.
- The post's exchanges are every exchange inside a span, from every transcript, sorted by
  "at" (a stable sort, so one transcript's order holds on equal times).
- No span in any transcript: raise ValueError and write nothing; the command prints an error
  naming the slug to stderr and exits 1.

Ids and appending:
- The post's exchanges are numbered x1, x2, ... in that order. The trace already holds some:
  its highest id (from exchange records' "id" and withheld records' "ids") is the last one
  written, and only exchanges numbered after it are appended. Nothing new: the file is left
  as it is and 0 is returned.
- A missing trace starts with the header {"ledger_trace": 1, "post": "<slug>"}. The folder
  <root>/<slug> is created if needed.
- Records are one JSON object per line, written with json.dumps(record, ensure_ascii=False).

Records:
- exchange: {"type": "exchange", "id": "x1", "at": ..., "source": "claude-code",
  "model": ..., "prompt": ..., "reply": ..., "tools": [...]}, with at, model, prompt, reply
  and tools as exchanges() gives them.
- A tool whose summary or detail contains ".ledger/" is redacted: its summary becomes just
  its name, and its detail "Redacted: it touches .ledger/."
- Withheld: an exchange whose prompt's first two words are `ledger private`, or whose id is
  in <root>/<slug>/post.md's front matter line `private: [x4, x5]` (no post.md, or no such
  line: none). Its prompt, reply and tools are never written. Withheld exchanges next to each
  other among those being appended become one record:
  {"type": "withheld", "at": <the first one's at>, "count": <how many>, "ids": ["x3", "x4"]}.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ledger.importer import import_claude_code

LEDGER = Path(sys.executable).parent / "ledger"


def at(minute, second=0):
    return f"2026-11-11T09:{minute:02d}:{second:02d}.500Z"


def prompt(text, t):
    return {"type": "user", "timestamp": t, "message": {"role": "user", "content": text}}


def reply(text, t, *tools):
    content = [{"type": "text", "text": text}, *tools]
    return {"type": "assistant", "timestamp": t, "message": {"role": "assistant", "model": "claude-opus-5-5", "content": content}}


def tool_use(id, name, input):
    return {"type": "tool_use", "id": id, "name": name, "input": input}


def tool_result(id, content, t):
    return {"type": "user", "timestamp": t, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": id, "content": content}]}}


def turn(text, minute):
    """A prompt at the given minute and a reply 10 seconds later."""
    return [prompt(text, at(minute)), reply("Re: " + text, at(minute, 10))]


def transcript(path, *turns):
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [r for t in turns for r in t]
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def trace(root, slug="a-post"):
    lines = (root / slug / "trace.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def prompts(records):
    return [r["prompt"] for r in records if r.get("type") == "exchange"]


def ids(records):
    out = []
    for r in records:
        if r.get("type") == "exchange":
            out.append(r["id"])
        elif r.get("type") == "withheld":
            out.extend(r["ids"])
    return out


def test_one_span(tmp_path):
    t = transcript(tmp_path / "s1.jsonl",
                   turn("Before.", 0),
                   turn("ledger start a-post", 1),
                   turn("Draft it.", 2),
                   turn("Shorter.", 3),
                   turn("ledger end", 4),
                   turn("After.", 5))
    assert import_claude_code("a-post", [t], tmp_path) == 2
    records = trace(tmp_path)
    assert records[0] == {"ledger_trace": 1, "post": "a-post"}
    assert records[1] == {"type": "exchange", "id": "x1", "at": "2026-11-11T09:02:00Z", "source": "claude-code",
                          "model": "claude-opus-5-5", "prompt": "Draft it.", "reply": "Re: Draft it.", "tools": []}
    assert prompts(records) == ["Draft it.", "Shorter."]
    assert ids(records) == ["x1", "x2"]


def test_no_end_runs_to_the_end_of_the_transcript(tmp_path):
    t = transcript(tmp_path / "s1.jsonl", turn("ledger start a-post", 1), turn("Draft it.", 2), turn("More.", 3))
    import_claude_code("a-post", [t], tmp_path)
    assert prompts(trace(tmp_path)) == ["Draft it.", "More."]


def test_another_start_ends_the_span(tmp_path):
    t = transcript(tmp_path / "s1.jsonl",
                   turn("ledger start a-post", 1), turn("Mine.", 2),
                   turn("ledger start other-post", 3), turn("Not mine.", 4))
    import_claude_code("a-post", [t], tmp_path)
    assert prompts(trace(tmp_path)) == ["Mine."]


def test_two_spans_in_one_session(tmp_path):
    t = transcript(tmp_path / "s1.jsonl",
                   turn("ledger start a-post", 1), turn("One.", 2), turn("ledger end", 3),
                   turn("Something else.", 4),
                   turn("ledger start a-post", 5), turn("Two.", 6))
    assert import_claude_code("a-post", [t], tmp_path) == 2
    assert prompts(trace(tmp_path)) == ["One.", "Two."]


def test_two_sessions_in_time_order(tmp_path):
    later = transcript(tmp_path / "later.jsonl", turn("ledger start a-post", 20), turn("Second.", 21))
    earlier = transcript(tmp_path / "earlier.jsonl", turn("ledger start a-post", 1), turn("First.", 2), turn("ledger end", 3))
    import_claude_code("a-post", [later, earlier], tmp_path)
    records = trace(tmp_path)
    assert prompts(records) == ["First.", "Second."]
    assert ids(records) == ["x1", "x2"]


def test_saved_copies_are_read_and_the_longest_copy_wins(tmp_path):
    transcript(tmp_path / ".ledger" / "transcripts" / "old.jsonl", turn("ledger start a-post", 1), turn("Saved.", 2))
    full = transcript(tmp_path / "sessions" / "s1.jsonl", turn("ledger start a-post", 5), turn("A.", 6), turn("B.", 7))
    transcript(tmp_path / ".ledger" / "transcripts" / "s1.jsonl", turn("ledger start a-post", 5), turn("A.", 6))
    import_claude_code("a-post", [full], tmp_path)
    assert prompts(trace(tmp_path)) == ["Saved.", "A.", "B."]


def test_ids_run_on_and_a_reimport_adds_nothing(tmp_path):
    path = tmp_path / "s1.jsonl"
    transcript(path, turn("ledger start a-post", 1), turn("One.", 2))
    assert import_claude_code("a-post", [path], tmp_path) == 1
    transcript(path, turn("ledger start a-post", 1), turn("One.", 2), turn("Two.", 3), turn("Three.", 4))
    assert import_claude_code("a-post", [path], tmp_path) == 2
    before = (tmp_path / "a-post" / "trace.jsonl").read_text()
    assert import_claude_code("a-post", [path], tmp_path) == 0
    assert (tmp_path / "a-post" / "trace.jsonl").read_text() == before
    records = trace(tmp_path)
    assert ids(records) == ["x1", "x2", "x3"]
    assert sum(1 for r in records if "ledger_trace" in r) == 1


def test_a_private_prompt_is_withheld(tmp_path):
    t = transcript(tmp_path / "s1.jsonl",
                   turn("ledger start a-post", 1), turn("One.", 2),
                   turn("ledger private my salary is 10", 3), turn("ledger private and this", 4),
                   turn("Two.", 5))
    assert import_claude_code("a-post", [t], tmp_path) == 4
    records = trace(tmp_path)
    assert records[2] == {"type": "withheld", "at": "2026-11-11T09:03:00Z", "count": 2, "ids": ["x2", "x3"]}
    assert ids(records) == ["x1", "x2", "x3", "x4"]
    assert "salary" not in (tmp_path / "a-post" / "trace.jsonl").read_text()


def test_a_private_id_in_post_md_is_withheld(tmp_path):
    (tmp_path / "a-post").mkdir()
    (tmp_path / "a-post" / "post.md").write_text("---\ntitle: A post\nprivate: [x2]\n---\n\nText.\n")
    t = transcript(tmp_path / "s1.jsonl", turn("ledger start a-post", 1), turn("One.", 2), turn("Secret plan.", 3), turn("Two.", 4))
    import_claude_code("a-post", [t], tmp_path)
    records = trace(tmp_path)
    assert prompts(records) == ["One.", "Two."]
    assert records[2] == {"type": "withheld", "at": "2026-11-11T09:03:00Z", "count": 1, "ids": ["x2"]}
    assert "Secret plan" not in (tmp_path / "a-post" / "trace.jsonl").read_text()


def test_a_tool_touching_dot_ledger_is_redacted(tmp_path):
    t = transcript(tmp_path / "s1.jsonl",
                   turn("ledger start a-post", 1),
                   [prompt("Check.", at(2)),
                    reply("Looking.", at(2, 5),
                          tool_use("t1", "Read", {"file_path": "/repo/.ledger/sessions/abc.json"}),
                          tool_use("t2", "Read", {"file_path": "/repo/a-post/post.md"})),
                    tool_result("t1", "session data", at(2, 6)),
                    tool_result("t2", "Text.", at(2, 7))])
    import_claude_code("a-post", [t], tmp_path)
    tools = trace(tmp_path)[1]["tools"]
    assert tools[0] == {"name": "Read", "summary": "Read", "detail": "Redacted: it touches .ledger/."}
    assert tools[1]["summary"] == "Read: /repo/a-post/post.md"
    assert "session data" not in (tmp_path / "a-post" / "trace.jsonl").read_text()


def test_no_start_is_refused(tmp_path):
    t = transcript(tmp_path / "s1.jsonl", turn("Just chatting.", 1), turn("ledger start other-post", 2), turn("Hi.", 3))
    with pytest.raises(ValueError):
        import_claude_code("a-post", [t], tmp_path)
    assert not (tmp_path / "a-post").exists()


def test_the_command(tmp_path):
    t = transcript(tmp_path / "s1.jsonl", turn("ledger start a-post", 1), turn("Draft it.", 2))
    r = subprocess.run([str(LEDGER), "import-claude-code", "a-post", str(t)], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stderr == ""
    assert prompts(trace(tmp_path)) == ["Draft it."]
    r = subprocess.run([str(LEDGER), "import-claude-code", "no-such-post", str(t)], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 1
    assert "no-such-post" in r.stderr
    assert "Traceback" not in r.stderr
