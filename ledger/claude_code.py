"""Import a post's span of Claude Code session transcripts as trace records (decision 0001).

A transcript is a `.jsonl` file under `~/.claude/projects/`. The writer's prompts are `user`
records with string content and a human (or no) origin, plus `queued_command` attachments
(messages typed while the session was busy). Everything the AI did until the next prompt is one
exchange: its text, joined, and its tool calls with their results.
"""
import json
import re

START = re.compile(r"^\s*ledger start\s+(\S+)", re.I)
END = re.compile(r"^\s*ledger end\b", re.I)
PRIVATE = re.compile(r"^\s*ledger private\b", re.I)
DETAIL_MAX = 4000
SUMMARY_MAX = 120
SOURCE = "claude-code"


class SpanError(ValueError):
    pass


def _records(paths):
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and not r.get("isSidechain"):
                    yield r


def _utc(ts):
    return (ts or "")[:19] + "Z" if ts else None


def _prompt(r):
    """The writer's prompt in this record, or None."""
    if r.get("type") == "user" and not r.get("isMeta"):
        text, kind = (r.get("message") or {}).get("content"), (r.get("origin") or {}).get("kind")
    elif r.get("type") == "attachment" and (r.get("attachment") or {}).get("type") == "queued_command":
        a = r["attachment"]
        if a.get("commandMode") not in (None, "prompt"):
            return None
        text, kind = a.get("prompt"), (a.get("origin") or {}).get("kind")
    else:
        return None
    if not isinstance(text, str) or kind not in ("human", None) or not text.strip():
        return None
    return text.strip()


def _result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _summary(name, args):
    args = args if isinstance(args, dict) else {}
    for key in ("description", "query", "command", "file_path", "url", "pattern", "prompt"):
        if isinstance(args.get(key), str) and args[key].strip():
            what = " ".join(args[key].split())
            break
    else:
        what = ""
    line = f"{name}: {what}" if what else name
    return line if len(line) <= SUMMARY_MAX else line[: SUMMARY_MAX - 1] + "…"


def _cut(text):
    return text if len(text) <= DETAIL_MAX else text[: DETAIL_MAX - 1] + "…"


def read_exchanges(paths):
    """Every exchange in the transcripts, in order: {at, prompt, model, reply, tools}."""
    exchanges, by_tool_id = [], {}
    for r in _records(paths):
        text = _prompt(r)
        if text is not None:
            exchanges.append({"at": _utc(r.get("timestamp")), "prompt": text, "model": None, "reply": [], "tools": []})
            continue
        if not exchanges:
            continue
        x, msg = exchanges[-1], r.get("message") or {}
        content = msg.get("content")
        if r.get("type") == "assistant" and isinstance(content, list):
            if msg.get("model") and not msg["model"].startswith("<"):
                x["model"] = msg["model"]
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    x["reply"].append(b["text"].strip())
                elif b.get("type") == "tool_use":
                    tool = {"name": b.get("name", "tool"), "args": b.get("input"), "result": ""}
                    x["tools"].append(tool)
                    by_tool_id[b.get("id")] = tool
        elif r.get("type") == "user" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in by_tool_id:
                    by_tool_id[b["tool_use_id"]]["result"] = _result_text(b.get("content"))
    return exchanges


def _tool_record(tool):
    detail = json.dumps(tool["args"], ensure_ascii=False, indent=1) if tool["args"] else ""
    if tool["result"]:
        detail = f"{detail}\n\n{tool['result']}" if detail else tool["result"]
    return {"name": tool["name"], "summary": _summary(tool["name"], tool["args"]), "detail": _cut(detail)}


def trace(paths, slug, private_ids=()):
    """The trace records for post `slug`: a header, then exchanges and withheld gaps, in order.

    The span runs from the prompt `ledger start <slug>` to the next `ledger end`, both included;
    with no end yet, to the end of the transcripts. Exchange ids count every exchange in the span,
    so an id stays the same whether or not that exchange is withheld.
    """
    exchanges = read_exchanges(paths)
    starts = [i for i, x in enumerate(exchanges) if (m := START.match(x["prompt"])) and m.group(1) == slug]
    if not starts:
        raise SpanError(f"no prompt starting 'ledger start {slug}' in the transcripts")
    if len(starts) > 1:
        raise SpanError(f"'ledger start {slug}' appears {len(starts)} times; a post has one start")
    span = exchanges[starts[0]:]
    end = next((i for i, x in enumerate(span) if END.match(x["prompt"])), None)
    span = span if end is None else span[: end + 1]

    out, gap = [{"ledger_trace": 1, "post": slug}], None
    for n, x in enumerate(span, 1):
        xid = f"x{n}"
        if PRIVATE.match(x["prompt"]) or xid in private_ids:
            if gap is None:
                gap = {"type": "withheld", "at": x["at"], "count": 0}
                out.append(gap)
            gap["count"] += 1
            continue
        gap = None
        out.append({
            "type": "exchange", "id": xid, "at": x["at"], "source": SOURCE, "model": x["model"],
            "prompt": x["prompt"], "reply": "\n\n".join(x["reply"]),
            "tools": [_tool_record(t) for t in x["tools"]],
        })
    return out
