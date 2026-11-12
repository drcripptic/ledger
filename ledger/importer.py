"""Import Claude Code transcripts into a post trace."""

import json
from pathlib import Path

from ledger.claude_code import exchanges


def _read_private_ids(post_dir):
    """Read private ids from post.md front matter."""
    post_md = post_dir / "post.md"
    if not post_md.exists():
        return set()
    text = post_md.read_text()
    if not text.startswith("---"):
        return set()
    end = text.find("---", 3)
    if end < 0:
        return set()
    front_matter = text[4:end]
    for line in front_matter.splitlines():
        stripped = line.strip()
        if stripped.startswith("private:"):
            rest = stripped[8:].strip()
            if rest.startswith("[") and rest.endswith("]"):
                ids_str = rest[1:-1].strip()
                if not ids_str:
                    return set()
                ids = set()
                for item in ids_str.split(","):
                    item = item.strip()
                    if item.startswith("x"):
                        ids.add(item)
                return ids
    return set()


def _is_private_prompt(prompt):
    """Check if a prompt starts with 'ledger private'."""
    words = prompt.strip().split()
    return len(words) >= 2 and words[0] == "ledger" and words[1] == "private"


def _is_start_prompt(prompt, slug):
    """Check if a prompt starts with 'ledger start <slug>'."""
    words = prompt.strip().split()
    return len(words) >= 3 and words[0] == "ledger" and words[1] == "start" and words[2] == slug


def _is_end_prompt(prompt):
    """Check if a prompt starts with 'ledger end'."""
    words = prompt.strip().split()
    return len(words) >= 2 and words[0] == "ledger" and words[1] == "end"


def _is_any_start_prompt(prompt):
    """Check if a prompt starts with 'ledger start' (any slug)."""
    words = prompt.strip().split()
    return len(words) >= 2 and words[0] == "ledger" and words[1] == "start"


def _extract_spans(exchanges_list, slug):
    """Extract spans for the given slug from exchanges."""
    spans = []
    i = 0
    while i < len(exchanges_list):
        ex = exchanges_list[i]
        if _is_start_prompt(ex["prompt"], slug):
            start_idx = i + 1
            j = start_idx
            while j < len(exchanges_list):
                next_ex = exchanges_list[j]
                if _is_end_prompt(next_ex["prompt"]):
                    break
                if _is_any_start_prompt(next_ex["prompt"]):
                    break
                j += 1
            spans.append(exchanges_list[start_idx:j])
        i += 1
    return spans


def _all_transcript_paths(transcripts, root):
    """Get all transcript paths, with saved copies, picking longest on duplicates."""
    saved_dir = root / ".ledger" / "transcripts"
    seen = {}
    
    for t in transcripts:
        name = Path(t).name
        if name not in seen or len(Path(t).read_text().splitlines()) > len(Path(seen[name]).read_text().splitlines()):
            seen[name] = t
    
    if saved_dir.exists():
        for p in saved_dir.glob("*.jsonl"):
            name = p.name
            if name not in seen or len(p.read_text().splitlines()) > len(Path(seen[name]).read_text().splitlines()):
                seen[name] = str(p)
    
    return list(seen.values())


def _redact_tools(tools):
    """Redact tool details touching .ledger/."""
    result = []
    for tool in tools:
        summary = tool["summary"]
        detail = tool["detail"]
        name = tool["name"]
        if ".ledger/" in summary or ".ledger/" in detail:
            result.append({
                "name": name,
                "summary": name,
                "detail": "Redacted: it touches .ledger/."
            })
        else:
            result.append(tool)
    return result


def import_claude_code(slug, transcripts, root):
    """Import a post's history from Claude Code transcripts.
    
    Returns the number of exchanges added (including withheld ones).
    """
    root = Path(root)
    transcript_paths = _all_transcript_paths(transcripts, root)
    
    all_exchanges = []
    for tp in transcript_paths:
        ex_list = exchanges(tp)
        spans = _extract_spans(ex_list, slug)
        for span in spans:
            for ex in span:
                all_exchanges.append(ex)
    
    if not all_exchanges:
        raise ValueError(f"No ledger start {slug} found")
    
    all_exchanges.sort(key=lambda e: e["at"])
    
    post_dir = root / slug
    post_dir.mkdir(parents=True, exist_ok=True)
    trace_path = post_dir / "trace.jsonl"
    
    existing_records = []
    last_id_n = 0
    
    if trace_path.exists():
        for line in trace_path.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                existing_records.append(record)
                if record.get("type") == "exchange":
                    ex_id = record["id"]
                    n = int(ex_id[1:])
                    last_id_n = max(last_id_n, n)
                elif record.get("type") == "withheld":
                    for wid in record["ids"]:
                        n = int(wid[1:])
                        last_id_n = max(last_id_n, n)
    
    private_ids = _read_private_ids(post_dir)
    
    numbered_exchanges = []
    for i, ex in enumerate(all_exchanges):
        id_str = f"x{i+1}"
        numbered_exchanges.append((id_str, ex))
    
    newer_exchanges = [ne for ne in numbered_exchanges if int(ne[0][1:]) > last_id_n]
    
    if not newer_exchanges:
        return 0
    
    has_header = any("ledger_trace" in r for r in existing_records)
    
    records_to_write = []
    if not has_header and trace_path.exists():
        records_to_write.append({"ledger_trace": 1, "post": slug})
    
    withheld_batch = []
    for id_str, ex in newer_exchanges:
        is_private = _is_private_prompt(ex["prompt"]) or id_str in private_ids
        
        if is_private:
            withheld_batch.append((id_str, ex))
        else:
            while withheld_batch:
                first_id, first_ex = withheld_batch[0]
                records_to_write.append({
                    "type": "withheld",
                    "at": first_ex["at"],
                    "count": len(withheld_batch),
                    "ids": [b[0] for b in withheld_batch]
                })
                withheld_batch = []
            
            redacted_tools = _redact_tools(ex["tools"])
            records_to_write.append({
                "type": "exchange",
                "id": id_str,
                "at": ex["at"],
                "source": "claude-code",
                "model": ex["model"],
                "prompt": ex["prompt"],
                "reply": ex["reply"],
                "tools": redacted_tools
            })
    
    while withheld_batch:
        first_id, first_ex = withheld_batch[0]
        records_to_write.append({
            "type": "withheld",
            "at": first_ex["at"],
            "count": len(withheld_batch),
            "ids": [b[0] for b in withheld_batch]
        })
        withheld_batch = []
    
    if not trace_path.exists() and not has_header:
        records_to_write.insert(0, {"ledger_trace": 1, "post": slug})
    
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records_to_write)
    with open(trace_path, "a") as f:
        f.write(text)
    
    return len(newer_exchanges)
