"""ledger's command line.

    python -m ledger import-claude-code --post <slug> --out <dir> [--private x4,x5] <transcript.jsonl>...

writes <dir>/trace.jsonl (decision 0001).
"""
import argparse
import json
import sys
from pathlib import Path

from . import claude_code


def main(argv=None):
    p = argparse.ArgumentParser(prog="ledger")
    sub = p.add_subparsers(dest="command", required=True)
    cc = sub.add_parser("import-claude-code", help="write a post's trace from Claude Code transcripts")
    cc.add_argument("--post", required=True, help="the slug given in 'ledger start <slug>'")
    cc.add_argument("--out", required=True, type=Path, help="the post's folder")
    cc.add_argument("--private", default="", help="exchange ids to withhold, comma-separated")
    cc.add_argument("transcripts", nargs="+", type=Path, help="transcripts, oldest first")
    args = p.parse_args(argv)

    private = {i.strip() for i in args.private.split(",") if i.strip()}
    try:
        records = claude_code.trace(args.transcripts, args.post, private)
    except claude_code.SpanError as e:
        print(f"ledger: {e}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "trace.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    exchanges = sum(r.get("type") == "exchange" for r in records)
    withheld = sum(r.get("count", 0) for r in records if r.get("type") == "withheld")
    print(f"ledger: wrote {path}: {exchanges} exchanges, {withheld} withheld")
    return 0


if __name__ == "__main__":
    sys.exit(main())
