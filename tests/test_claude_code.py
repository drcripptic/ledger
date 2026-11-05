"""The Claude Code importer, on synthetic transcripts shaped like Claude Code's."""
import json

import pytest

from ledger import __main__ as cli
from ledger import claude_code

MODEL = "claude-opus-5-5"


def prompt(text, t, origin="human"):
    r = {"type": "user", "timestamp": t, "message": {"role": "user", "content": text}}
    if origin:
        r["origin"] = {"kind": origin}
    return r


def queued(text, t):
    return {"type": "attachment", "timestamp": t,
            "attachment": {"type": "queued_command", "prompt": text, "origin": {"kind": "human"}}}


def say(text, t, model=MODEL):
    return {"type": "assistant", "timestamp": t,
            "message": {"role": "assistant", "model": model, "content": [{"type": "text", "text": text}]}}


def tool(tid, name, args, t):
    return {"type": "assistant", "timestamp": t,
            "message": {"role": "assistant", "model": MODEL,
                        "content": [{"type": "tool_use", "id": tid, "name": name, "input": args}]}}


def result(tid, text, t):
    return {"type": "user", "timestamp": t,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": text}]}}


def write(tmp_path, records, name="s.jsonl"):
    path = tmp_path / name
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def exchanges(records):
    return [r for r in records if r.get("type") == "exchange"]


SESSION = [
    prompt("unrelated question before the post", "2026-10-30T08:00:00.000Z"),
    say("unrelated answer", "2026-10-30T08:00:05.000Z"),
    prompt("ledger start slower-software\nI want to argue some software should be slower.", "2026-10-30T09:02:11.500Z"),
    {"type": "assistant", "timestamp": "2026-10-30T09:02:12.000Z",
     "message": {"role": "assistant", "model": MODEL, "content": [{"type": "thinking", "thinking": "hidden"}]}},
    tool("t1", "WebSearch", {"query": "cost of instant email filing"}, "2026-10-30T09:02:13.000Z"),
    result("t1", "Three results about inbox habits.", "2026-10-30T09:02:20.000Z"),
    say("Name the mechanism next.", "2026-10-30T09:02:30.000Z"),
    say("A draft: Speed can hide important decisions.", "2026-10-30T09:02:31.000Z"),
    {"type": "user", "isMeta": True, "timestamp": "2026-10-30T09:03:00.000Z", "message": {"role": "user", "content": "a system note"}},
    prompt("a task finished", "2026-10-30T09:03:01.000Z", origin="task-notification"),
    queued("Too formal. Shorter sentences.", "2026-10-30T09:09:40.000Z"),
    say("Speed hides decisions.", "2026-10-30T09:09:45.000Z", model="gpt-5"),
    prompt("ledger private\nmy notes on a colleague", "2026-10-30T09:12:00.000Z"),
    say("private reply", "2026-10-30T09:12:05.000Z"),
    prompt("ledger private\nmore of the same", "2026-10-30T09:13:00.000Z"),
    say("private reply 2", "2026-10-30T09:13:05.000Z"),
    prompt("Add a paragraph on chosen slowness.", "2026-10-30T09:15:00.000Z"),
    say("None of this means slow is good in itself.", "2026-10-30T09:15:09.000Z"),
    prompt("ledger end", "2026-10-30T09:31:00.000Z"),
    say("Done.", "2026-10-30T09:31:02.000Z"),
    prompt("after the post", "2026-10-30T10:00:00.000Z"),
]


def test_span_header_and_ids(tmp_path):
    recs = claude_code.trace([write(tmp_path, SESSION)], "slower-software")
    assert recs[0] == {"ledger_trace": 1, "post": "slower-software"}
    assert [x["id"] for x in exchanges(recs)] == ["x1", "x2", "x5", "x6"]
    assert exchanges(recs)[0]["prompt"].startswith("ledger start slower-software")
    assert exchanges(recs)[-1]["prompt"] == "ledger end"


def test_exchange_reply_tools_model_and_time(tmp_path):
    x1 = exchanges(claude_code.trace([write(tmp_path, SESSION)], "slower-software"))[0]
    assert x1["at"] == "2026-10-30T09:02:11Z"
    assert x1["source"] == "claude-code" and x1["model"] == MODEL
    assert x1["reply"] == "Name the mechanism next.\n\nA draft: Speed can hide important decisions."
    assert "hidden" not in json.dumps(x1)
    assert x1["tools"] == [{
        "name": "WebSearch",
        "summary": "WebSearch: cost of instant email filing",
        "detail": '{\n "query": "cost of instant email filing"\n}\n\nThree results about inbox habits.',
    }]


def test_meta_and_notifications_are_not_prompts_and_queued_messages_are(tmp_path):
    x2 = exchanges(claude_code.trace([write(tmp_path, SESSION)], "slower-software"))[1]
    assert x2["prompt"] == "Too formal. Shorter sentences." and x2["model"] == "gpt-5"


def test_private_marker_leaves_one_gap_and_no_text(tmp_path):
    recs = claude_code.trace([write(tmp_path, SESSION)], "slower-software")
    gaps = [r for r in recs if r.get("type") == "withheld"]
    assert gaps == [{"type": "withheld", "at": "2026-10-30T09:12:00Z", "count": 2}]
    assert "colleague" not in json.dumps(recs) and "private reply" not in json.dumps(recs)


def test_private_after_the_fact_by_id(tmp_path):
    recs = claude_code.trace([write(tmp_path, SESSION)], "slower-software", {"x2"})
    assert [x["id"] for x in exchanges(recs)] == ["x1", "x5", "x6"]
    assert [r["count"] for r in recs if r.get("type") == "withheld"] == [3]


def test_span_crosses_transcripts_and_runs_to_the_end_without_a_marker(tmp_path):
    a = write(tmp_path, SESSION[2:8], "a.jsonl")
    b = write(tmp_path, [prompt("next day", "2026-10-31T09:00:00Z"), say("ok", "2026-10-31T09:00:01Z")], "b.jsonl")
    recs = claude_code.trace([a, b], "slower-software")
    assert [x["prompt"] for x in exchanges(recs)][-1] == "next day"


def test_missing_or_repeated_start_is_refused(tmp_path):
    with pytest.raises(claude_code.SpanError, match="no prompt"):
        claude_code.trace([write(tmp_path, SESSION)], "another-post")
    twice = SESSION + [prompt("ledger start slower-software", "2026-10-30T11:00:00Z")]
    with pytest.raises(claude_code.SpanError, match="2 times"):
        claude_code.trace([write(tmp_path, twice)], "slower-software")


def test_long_tool_detail_and_summary_are_cut(tmp_path):
    recs = claude_code.trace([write(tmp_path, [
        prompt("ledger start p", "2026-10-30T09:00:00Z"),
        tool("t", "Bash", {"command": "x" * 500}, "2026-10-30T09:00:01Z"),
        result("t", "y" * 9000, "2026-10-30T09:00:02Z"),
    ])], "p")
    t = exchanges(recs)[0]["tools"][0]
    assert len(t["summary"]) == claude_code.SUMMARY_MAX and len(t["detail"]) == claude_code.DETAIL_MAX


def test_cli_writes_trace(tmp_path, capsys):
    out = tmp_path / "post"
    code = cli.main(["import-claude-code", "--post", "slower-software", "--out", str(out),
                     "--private", "x6", str(write(tmp_path, SESSION))])
    assert code == 0
    lines = [json.loads(l) for l in (out / "trace.jsonl").read_text().splitlines()]
    assert lines[0]["ledger_trace"] == 1 and len(exchanges(lines)) == 3
    assert "3 exchanges, 3 withheld" in capsys.readouterr().out


def test_cli_reports_a_missing_start(tmp_path, capsys):
    assert cli.main(["import-claude-code", "--post", "nope", "--out", str(tmp_path / "o"),
                     str(write(tmp_path, SESSION))]) == 1
    assert "no prompt starting 'ledger start nope'" in capsys.readouterr().err
