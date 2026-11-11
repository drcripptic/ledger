"""Parse Claude Code transcripts into exchanges."""

import json
from pathlib import Path


def _is_prompt(record):
    """Check if a record is the writer's prompt."""
    if record.get("type") != "user":
        return False
    message = record.get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str) or not content.strip():
        return False
    if record.get("isMeta") or record.get("isCompactSummary"):
        return False
    if record.get("isSidechain"):
        return False
    origin = record.get("origin")
    if origin and origin.get("kind") != "human":
        return False
    stripped = content.strip()
    if stripped.startswith("[Request interrupted by user"):
        return False
    return True


def _is_queued_command(record):
    """Check if a record is an attachment with queued_command (typed while AI busy)."""
    if record.get("type") != "attachment":
        return False
    attachment = record.get("attachment", {})
    if attachment.get("type") != "queued_command":
        return False
    prompt = attachment.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    mode = attachment.get("commandMode")
    if mode is not None and mode != "prompt":
        return False
    origin = attachment.get("origin")
    if origin and origin.get("kind") != "human":
        return False
    return True


def _parse_timestamp(ts):
    """Cut timestamp to whole seconds with Z suffix."""
    if ts is None:
        return None
    if "T" not in ts:
        return ts
    base = ts.split(".")[0]
    if base.endswith("Z"):
        return base[:20] + "Z"
    return ts[:19] + "Z"


def _tool_summary(name, input_):
    """Build tool summary: name with first meaningful field."""
    fields = ["description", "query", "command", "file_path", "url", "pattern", "prompt"]
    what = None
    for field in fields:
        val = input_.get(field)
        if isinstance(val, str) and val.strip():
            what = " ".join(val.strip().split())
            break
    if what:
        summary = f"{name}: {what}"
    else:
        summary = name
    if len(summary) > 120:
        summary = summary[:119] + "…"
    return summary


def _tool_detail(input_, result_text):
    """Build tool detail: input JSON + blank line + result, cut to 4000 chars."""
    input_json = json.dumps(input_, ensure_ascii=False, indent=1)
    if result_text:
        detail = f"{input_json}\n\n{result_text}"
    else:
        detail = input_json
    if len(detail) > 4000:
        detail = detail[:3999] + "…"
    return detail


def exchanges(path):
    """Read a Claude Code transcript and return its exchanges."""
    path = Path(path)
    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.append(record)

    filtered = [r for r in records if not r.get("isSidechain")]

    prompt_positions = []
    for i, record in enumerate(filtered):
        if _is_prompt(record) or _is_queued_command(record):
            prompt_positions.append(i)

    if not prompt_positions:
        return []

    exchanges_list = []
    for pi, pos in enumerate(prompt_positions):
        record = filtered[pos]
        next_pos = prompt_positions[pi + 1] if pi + 1 < len(prompt_positions) else None
        exchange_records = filtered[pos:next_pos]

        if _is_prompt(record):
            prompt_text = record["message"]["content"].strip()
        else:
            prompt_text = record["attachment"]["prompt"].strip()

        at = _parse_timestamp(record.get("timestamp"))

        model = None
        reply_parts = []
        tool_uses = {}
        tool_results = {}

        for rec in exchange_records[1:]:
            if rec.get("type") == "assistant":
                message = rec.get("message", {})
                model_val = message.get("model")
                if model_val and not model_val.startswith("<"):
                    model = model_val
                content = message.get("content", [])
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            reply_parts.append(text)
                    elif block.get("type") == "tool_use":
                        tool_id = block.get("id")
                        tool_uses[tool_id] = {
                            "name": block.get("name"),
                            "input": block.get("input", {}),
                        }
            elif rec.get("type") == "user":
                content = rec.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if item.get("type") == "tool_result":
                            tool_id = item.get("tool_use_id")
                            result_content = item.get("content", "")
                            if isinstance(result_content, str):
                                tool_results[tool_id] = result_content
                            elif isinstance(result_content, list):
                                texts = []
                                for sub in result_content:
                                    if sub.get("type") == "text":
                                        texts.append(sub.get("text", ""))
                                tool_results[tool_id] = "\n".join(texts)

        tools = []
        for tid, info in tool_uses.items():
            result_text = tool_results.get(tid, "")
            summary = _tool_summary(info["name"], info["input"])
            detail = _tool_detail(info["input"], result_text)
            tools.append({
                "name": info["name"],
                "summary": summary,
                "detail": detail,
            })

        exchange = {
            "n": pi + 1,
            "at": at,
            "prompt": prompt_text,
            "model": model,
            "reply": "\n\n".join(reply_parts),
            "tools": tools,
        }
        exchanges_list.append(exchange)

    return exchanges_list


def prompt_index(path):
    """Count the writer's prompts in a transcript."""
    path = Path(path)
    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.append(record)

    filtered = [r for r in records if not r.get("isSidechain")]

    count = 0
    for record in filtered:
        if _is_prompt(record) or _is_queued_command(record):
            count += 1

    return count
