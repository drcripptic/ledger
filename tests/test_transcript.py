"""Slice 2 (issue #14): one Claude Code transcript to exchanges.

ledger.claude_code.exchanges(path) reads one transcript (.jsonl, one JSON record per line)
and returns its exchanges, in order. Each is a dict:

    {"n": 1, "at": "2026-11-11T09:00:00Z", "prompt": "...", "model": "...",
     "reply": "...", "tools": [{"name": "...", "summary": "...", "detail": "..."}]}

ledger.claude_code.prompt_index(path) is the number of the writer's prompts in the file.

The writer's prompts:
- a record with type "user", message.content a non-empty string, not isMeta, not
  isCompactSummary, not isSidechain, and origin.kind "human" or no origin;
- an attachment record whose attachment.type is "queued_command" (typed while the AI was busy),
  with attachment.prompt a non-empty string, commandMode "prompt" or absent, and
  attachment.origin.kind "human" or no attachment.origin (a message from another session
  has kind "peer").
- Not a prompt: "[Request interrupted by user]" (or text starting with it).
The prompt text is stripped. Markers (`ledger start <slug>`, `ledger end`, `ledger private`)
are ordinary prompts here.

An exchange is a prompt and everything until the next prompt:
- n: the prompt's number in the file, from 1.
- at: the prompt record's timestamp cut to whole seconds, with "Z" (UTC).
- model: message.model of the exchange's assistant records (the last seen), or None.
  Ignore models starting with "<" (e.g. "<synthetic>").
- reply: the text blocks of its assistant records, each stripped, empty ones skipped,
  joined with "\n\n". Thinking blocks are left out.
- tools: one per tool_use block, in order. summary: "<name>: <what>", where <what> is the
  first non-empty string among input's description, query, command, file_path, url, pattern,
  prompt, with whitespace collapsed; just "<name>" if none. Cut to 120 characters, ending "…"
  when cut. detail: the input as json.dumps(input, ensure_ascii=False, indent=1), then a blank
  line and the tool's result text (from the user record's tool_result with that tool_use_id;
  content a string, or the text blocks of a list joined with "\n"); cut to 4,000 characters,
  ending "…" when cut.
- Records with isSidechain true are skipped entirely. Lines that aren't JSON are skipped.
- Anything before the first prompt is ignored.
"""

import json

from ledger.claude_code import exchanges, prompt_index

TS = "2026-11-11T09:00:{:02d}.123Z"
_t = iter(range(60))


def ts():
    return TS.format(next(_t) % 60)


def prompt(text, **kw):
    return {"type": "user", "timestamp": ts(), "message": {"role": "user", "content": text}, **kw}


def queued(text, mode=None):
    a = {"type": "queued_command", "prompt": text}
    if mode:
        a["commandMode"] = mode
    return {"type": "attachment", "timestamp": ts(), "attachment": a}


def assistant(*blocks, model="claude-opus-5-5", **kw):
    return {"type": "assistant", "timestamp": ts(), "message": {"role": "assistant", "model": model, "content": list(blocks)}, **kw}


def text(t):
    return {"type": "text", "text": t}


def thinking(t):
    return {"type": "thinking", "thinking": t}


def tool_use(id, name, input):
    return {"type": "tool_use", "id": id, "name": name, "input": input}


def tool_result(id, content):
    return {"type": "user", "timestamp": ts(), "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": id, "content": content}]}}


def write(tmp_path, records, extra_lines=()):
    p = tmp_path / "session.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in records) + "".join(extra_lines))
    return p


def test_plain_prompts(tmp_path):
    p = write(tmp_path, [
        prompt("  ledger start my-post  "),
        assistant(text("Recording.")),
        prompt("Draft an opening."),
        assistant(text("Here it is."), text("  "), text("Done.")),
    ])
    xs = exchanges(p)
    assert [x["n"] for x in xs] == [1, 2]
    assert [x["prompt"] for x in xs] == ["ledger start my-post", "Draft an opening."]
    assert xs[1]["reply"] == "Here it is.\n\nDone."
    assert xs[1]["model"] == "claude-opus-5-5"
    assert xs[0]["at"] == "2026-11-11T09:00:" + xs[0]["at"][17:19] + "Z"
    assert len(xs[0]["at"]) == 20
    assert prompt_index(p) == 2


def test_tool_results_are_not_prompts(tmp_path):
    p = write(tmp_path, [
        prompt("Read the post."),
        assistant(tool_use("t1", "Read", {"file_path": "/x/post.md"})),
        tool_result("t1", "Hello world."),
        assistant(tool_use("t2", "Bash", {"command": "ls   -la", "description": "List files"})),
        tool_result("t2", [{"type": "text", "text": "a"}, {"type": "image"}, {"type": "text", "text": "b"}]),
        assistant(text("It says hello.")),
    ])
    [x] = exchanges(p)
    assert x["reply"] == "It says hello."
    assert [t["name"] for t in x["tools"]] == ["Read", "Bash"]
    assert x["tools"][0]["summary"] == "Read: /x/post.md"
    assert x["tools"][0]["detail"] == json.dumps({"file_path": "/x/post.md"}, ensure_ascii=False, indent=1) + "\n\nHello world."
    assert x["tools"][1]["summary"] == "Bash: List files"
    assert x["tools"][1]["detail"].endswith("\n\na\nb")
    assert prompt_index(p) == 1


def test_summary_falls_back_and_is_cut(tmp_path):
    p = write(tmp_path, [
        prompt("Go."),
        assistant(tool_use("t1", "Mystery", {"n": 3}), tool_use("t2", "WebSearch", {"query": "q " * 200})),
    ])
    [x] = exchanges(p)
    assert x["tools"][0]["summary"] == "Mystery"
    s = x["tools"][1]["summary"]
    assert len(s) == 120 and s.endswith("…") and s.startswith("WebSearch: q q")


def test_detail_cut_to_4000(tmp_path):
    p = write(tmp_path, [prompt("Go."), assistant(tool_use("t1", "Read", {"file_path": "f"})), tool_result("t1", "x" * 10000)])
    d = exchanges(p)[0]["tools"][0]["detail"]
    assert len(d) == 4000 and d.endswith("…")


def test_subagent_entries_are_skipped(tmp_path):
    p = write(tmp_path, [
        prompt("Go."),
        prompt("A subagent's task", isSidechain=True),
        assistant(text("Subagent reply."), isSidechain=True),
        assistant(text("Main reply.")),
    ])
    [x] = exchanges(p)
    assert x["reply"] == "Main reply."
    assert prompt_index(p) == 1


def test_interrupted_turn(tmp_path):
    p = write(tmp_path, [
        prompt("Write a long draft."),
        assistant(text("Starting")),
        prompt("[Request interrupted by user]"),
        prompt("[Request interrupted by user for tool use]"),
        prompt("Shorter, please."),
        assistant(text("OK.")),
    ])
    xs = exchanges(p)
    assert [x["prompt"] for x in xs] == ["Write a long draft.", "Shorter, please."]
    assert xs[0]["reply"] == "Starting"
    assert prompt_index(p) == 2


def test_compaction_summary_and_meta_are_not_prompts(tmp_path):
    p = write(tmp_path, [
        prompt("One."),
        prompt("This session is being continued...", isCompactSummary=True),
        prompt("<command-name>/clear</command-name>", isMeta=True),
        prompt("Hook said no.", origin={"kind": "hook"}),
        prompt("Two.", origin={"kind": "human"}),
    ])
    assert [x["prompt"] for x in exchanges(p)] == ["One.", "Two."]
    assert prompt_index(p) == 2


def test_messages_typed_while_busy_are_prompts(tmp_path):
    p = write(tmp_path, [
        prompt("One."),
        assistant(text("Working.")),
        queued("  Also this.  "),
        queued("/compact", mode="bash"),
        assistant(text("Done both.")),
    ])
    xs = exchanges(p)
    assert [x["prompt"] for x in xs] == ["One.", "Also this."]
    assert [x["n"] for x in xs] == [1, 2]
    assert xs[1]["reply"] == "Done both."


def test_message_from_another_session_is_not_a_prompt(tmp_path):
    from_peer = queued("A message from another session.")
    from_peer["attachment"]["origin"] = {"kind": "peer"}
    from_writer = queued("Typed while busy.")
    from_writer["attachment"]["origin"] = {"kind": "human"}
    p = write(tmp_path, [
        prompt("One."),
        assistant(text("Working.")),
        from_peer,
        from_writer,
        assistant(text("Done.")),
    ])
    assert [x["prompt"] for x in exchanges(p)] == ["One.", "Typed while busy."]
    assert prompt_index(p) == 2


def test_thinking_is_dropped_and_synthetic_model_ignored(tmp_path):
    p = write(tmp_path, [
        prompt("Go."),
        assistant(thinking("secret reasoning"), text("Answer.")),
        assistant(text("More."), model="<synthetic>"),
    ])
    [x] = exchanges(p)
    assert x["reply"] == "Answer.\n\nMore."
    assert x["model"] == "claude-opus-5-5"
    assert "secret reasoning" not in json.dumps(x)


def test_before_first_prompt_and_bad_lines_ignored(tmp_path):
    p = write(tmp_path, [assistant(text("Stray.")), {"type": "summary"}, prompt("Go."), assistant(text("Hi."))], extra_lines=["not json\n", "\n"])
    [x] = exchanges(p)
    assert x["reply"] == "Hi."
    assert x["model"] == "claude-opus-5-5"


def test_no_model_is_none(tmp_path):
    p = write(tmp_path, [prompt("Go.")])
    [x] = exchanges(p)
    assert x["model"] is None and x["reply"] == "" and x["tools"] == []
