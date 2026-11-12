import json, re
from pathlib import Path
from ledger.claude_code import exchanges
from ledger.site import attribute as site_attribute

REDACTED = "Redacted: it touches .ledger/."

def _words(p, n): return p.split()[:n]

def _transcripts(paths, root):
    best = {}
    for p in [Path(x) for x in paths] + sorted((Path(root) / ".ledger" / "transcripts").glob("*.jsonl")):
        n = len(p.read_text().splitlines())
        if p.name not in best or n > best[p.name][0]:
            best[p.name] = (n, p)
    return [p for _, p in best.values()]

def _post_exchanges(slug, paths, root):
    out, found = [], False
    for p in _transcripts(paths, root):
        inside = False
        for x in exchanges(p):
            w = x["prompt"].split()
            if w[:3] == ["ledger", "start", slug]:
                inside = found = True; continue
            if w[:2] in (["ledger", "end"], ["ledger", "start"]):
                inside = False; continue
            if inside: out.append(dict(x, _sid=p.stem))
    if not found: raise ValueError(f"no `ledger start {slug}` in the transcripts")
    return sorted(out, key=lambda x: x["at"])

def _private_ids(post):
    if not post.exists(): return set()
    m = re.search(r"^private:\s*\[(.*?)\]", post.read_text(), re.M)
    return {s.strip() for s in m.group(1).split(",") if s.strip()} if m else set()

def _tilde(text):
    """The writer's own home folder, written as ~."""
    home = str(Path.home()).rstrip("/")
    if not home or home == "/" or not text:
        return text
    return re.sub(re.escape(home) + r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9_-])", "~", text)


def _tool(t):
    if ".ledger/" in t["summary"] or ".ledger/" in t["detail"]:
        return {"name": t["name"], "summary": t["name"], "detail": REDACTED}
    return dict(t, summary=_tilde(t["summary"]), detail=_tilde(t["detail"]))

def _copies(post_dir):
    p = post_dir / ".ledger" / "snapshots.jsonl"
    if not p.exists(): return []
    out = []
    for line in p.read_text().splitlines():
        try: out.append(json.loads(line))
        except ValueError: pass
    return out

def _has_hook_copies(copies):
    return any(c.get("event") in ("prompt", "stop") for c in copies)

def _strings(obj):
    """Every string under the keys "content" and "new_string", at any depth."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("content", "new_string") and isinstance(v, str):
                out.append(v)
            elif isinstance(v, (dict, list)):
                out.extend(_strings(v))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_strings(item))
    return out


def _written(paths):
    """What the AI wrote, as (timestamp cut to whole seconds, text), from every transcript read."""
    out = []
    for t in paths:
        for line in Path(t).read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or rec.get("type") != "assistant" or rec.get("isSidechain"):
                continue
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            ts = (rec.get("timestamp") or "")[:19]
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    out.append((ts, block.get("text", "")))
                elif block.get("type") == "tool_use":
                    out.extend((ts, x) for x in _strings(block.get("input", {})))
    return out


def _ai_corpus(written, cutoff_at):
    """What the AI had written by cutoff_at (whole seconds)."""
    return "\n\n".join(t for ts, t in written if ts <= cutoff_at[:19])


def _snapshots(copies, xs, ids, written, slug):
    """(by, after, text) per change, in copy order."""
    # Skip save copies entirely if any hook copies exist
    if _has_hook_copies(copies):
        save_copies = [c for c in copies if c.get("event") == "save"]
        copies = [c for c in copies if c.get("event") != "save"]

    by_sn = {(x["_sid"], x["n"]): ids[i] for i, x in enumerate(xs)}
    out, prev = [], ""

    # For save copies: find exchange whose at <= copy's at; ties go to the latest by index
    def find_exchange_by_at(copy_at):
        cut_sec = copy_at[:19] if len(copy_at) >= 19 else copy_at
        candidates = []
        for i, x in enumerate(xs):
            x_at = x.get("at", "")[:19] if len(x.get("at", "")) >= 19 else x.get("at", "")
            if x_at <= cut_sec:
                candidates.append((i, x))
        if not candidates: return None
        best_i, _ = max(candidates, key=lambda t: (t[1].get("at", "")[:19], t[0]))
        return ids[best_i]

    for c in copies:
        text = c.get("text", "")
        if text == prev: continue

        event = c.get("event")
        if event == "save":
            by = "mixed"
            after = find_exchange_by_at(c.get("at", ""))
        elif event == "stop":
            by = "ai"
            sid, n = c["session_id"], c["n"]
            after = by_sn.get((sid, n))
            if after is None:
                below = [x["n"] for x in xs if x["_sid"] == sid and x["n"] < n]
                if below: after = by_sn[(sid, max(below))]
                else:
                    first = next((i for i, x in enumerate(xs) if x["_sid"] == sid), None)
                    after = ids[first - 1] if first else None
        elif c.get("interrupted"):
            by = "mixed"
            sid, n = c["session_id"], c["n"]
            after = by_sn.get((sid, n))
            if after is None:
                below = [x["n"] for x in xs if x["_sid"] == sid and x["n"] < n]
                if below: after = by_sn[(sid, max(below))]
                else:
                    first = next((i for i, x in enumerate(xs) if x["_sid"] == sid), None)
                    after = ids[first - 1] if first else None
        else:
            by = "writer"
            sid, n = c["session_id"], c["n"]
            after = by_sn.get((sid, n))
            if after is None:
                below = [x["n"] for x in xs if x["_sid"] == sid and x["n"] < n]
                if below: after = by_sn[(sid, max(below))]
                else:
                    first = next((i for i, x in enumerate(xs) if x["_sid"] == sid), None)
                    after = ids[first - 1] if first else None

        # Build snapshot record
        rec = {"type": "snapshot", "by": by, "after": after, "text": text, "_before": prev, "_at": c.get("at", "")}

        # For mixed: compute AI ranges (always include ai key)
        if by == "mixed":
            corpus = _ai_corpus(written, c.get("at", ""))
            rec["ai"] = site_attribute(prev, text, corpus)

        prev = text  # Update prev AFTER using it for attribute()
        out.append(rec)
    return out

def import_claude_code(slug, transcripts, root="."):
    root = Path(root)
    xs = _post_exchanges(slug, transcripts, root)
    ids = [f"x{n}" for n in range(1, len(xs) + 1)]
    path = root / slug / "trace.jsonl"
    last, have = 0, {}
    if path.exists():
        for line in path.read_text().splitlines():
            r = json.loads(line)
            for i in ([r["id"]] if r.get("type") == "exchange" else r.get("ids", []) if r.get("type") == "withheld" else []):
                last = max(last, int(i[1:]))
            if r.get("type") == "snapshot":
                have[r["after"]] = have.get(r["after"], 0) + 1
    private = _private_ids(root / slug / "post.md")
    # full sequence of items
    items = []
    for n, x in enumerate(xs, 1):
        xid = f"x{n}"
        if _words(x["prompt"], 2) == ["ledger", "private"] or xid in private:
            if items and items[-1]["kind"] == "withheld" and items[-1]["ids"][-1] == f"x{n-1}":
                items[-1]["ids"].append(xid)
            else:
                items.append({"kind": "withheld", "ids": [xid], "x": x, "snaps": []})
        else:
            items.append({"kind": "exchange", "ids": [xid], "x": x, "snaps": []})
    where = {i: it for it in items for i in it["ids"]}
    lead = []
    written = _written(_transcripts(transcripts, root))
    for s in _snapshots(_copies(root / slug), xs, ids, written, slug):
        (where[s["after"]]["snaps"] if s["after"] else lead).append(s)
    for it in items:
        if it["kind"] == "withheld" and it["snaps"]:
            ss = it["snaps"]
            bys = {s["by"] for s in ss}
            folded = {"type": "snapshot", "by": bys.pop() if len(bys) == 1 else "mixed", "after": ss[-1]["after"], "text": ss[-1]["text"]}
            if folded["by"] == "mixed":
                folded["ai"] = site_attribute(ss[0]["_before"], ss[-1]["text"], _ai_corpus(written, ss[-1]["_at"]))
            it["snaps"] = [folded]
    seen = {}
    def fresh(snaps):
        out = []
        for s in snaps:
            k = seen.get(s["after"], 0); seen[s["after"]] = k + 1
            if k >= have.get(s["after"], 0): out.append(s)
        return out
    early, late, added = fresh(lead), [], 0
    for it in items:
        new_ids = [i for i in it["ids"] if int(i[1:]) > last]
        snaps = fresh(it["snaps"])
        if not new_ids:
            early += snaps; continue
        x = it["x"]
        added += len(new_ids)
        if it["kind"] == "withheld":
            late.append({"type": "withheld", "at": x["at"], "count": len(new_ids), "ids": new_ids})
        else:
            late.append({"type": "exchange", "id": new_ids[0], "at": x["at"], "source": "claude-code", "model": x["model"],
                         "prompt": _tilde(x["prompt"]), "reply": _tilde(x["reply"]), "tools": [_tool(t) for t in x["tools"]]})
        late += snaps
    records = [{k: v for k, v in r.items() if not k.startswith("_")} for r in early + late]
    if not records: return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", encoding="utf-8") as f:
        if new: f.write(json.dumps({"ledger_trace": 1, "post": slug}, ensure_ascii=False) + "\n")
        for r in records: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return added
