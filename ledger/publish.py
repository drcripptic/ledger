"""ledger publish: import, a final writer step, a secret scan, the published record, the site."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ledger.importer import import_claude_code
from ledger.site import build


class Refused(ValueError):
    """Publishing was refused; the message says why."""


SECRETS = [
    ("API key", r"sk-[A-Za-z0-9_-]{20,}"),
    ("API key", r"AKIA[A-Z0-9]{16}"),
    ("API key", r"AIza[A-Za-z0-9_-]{35}"),
    ("token", r"gh[pousr]_[A-Za-z0-9]{36,}"),
    ("token", r"github_pat_[A-Za-z0-9_]{22,}"),
    ("token", r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    ("token", r"ops_[A-Za-z0-9_-]{40,}"),
    ("token", r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\."),
    ("private key", r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    ("home-folder path", r"/(?:Users|home)/[A-Za-z0-9._-]+"),
]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _records(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _append(path, record):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _where(r):
    if r.get("type") == "exchange":
        return r["id"]
    if r.get("type") == "withheld":
        return r["ids"][0]
    return r.get("type") or "header"


def scan(records):
    """The first secret found, as (kind, where), or None."""
    for r in records:
        text = json.dumps(r, ensure_ascii=False)
        for kind, pattern in SECRETS:
            if re.search(pattern, text):
                return kind, _where(r)
    return None


def publish(slug, root, transcripts=(), out="docs"):
    root = Path(root)
    try:
        import_claude_code(slug, list(transcripts), root)
    except ValueError as e:
        raise Refused(str(e)) from None
    path = root / slug / "trace.jsonl"
    records = _records(path)
    snaps = [r for r in records if r.get("type") == "snapshot"]
    post = root / slug / "post.md"
    text = post.read_text() if post.is_file() else ""
    if snaps and snaps[-1]["text"] != text:
        after = None
        for r in records:
            if r.get("type") == "exchange":
                after = r["id"]
            elif r.get("type") == "withheld":
                after = r["ids"][-1]
        rec = {"type": "snapshot", "by": "writer", "after": after, "text": text}
        _append(path, rec)
        records.append(rec)
    found = scan(records)
    if found:
        kind, where = found
        raise Refused(f"{slug} not published: its trace has what looks like a {kind}, in {where}. "
                      f"Take it out of {path} (or mark the exchange private and remove its record), then publish again.")
    version = sum(1 for r in records if r.get("type") == "published") + 1
    _append(path, {"type": "published", "version": version, "at": _now()})
    build(root, root / out)
    return version
