"""CLI for ledger - replay of exchanges."""

import argparse
import sys

from ledger.importer import import_claude_code
from ledger.site import build


def cmd_start(args):
    """Start recording for a post."""
    if not args.slug:
        print("Error: start requires a slug argument", file=sys.stderr)
        sys.exit(1)
    print("Recording.")


def cmd_end(args):
    """End recording."""
    print("Recording.")


def cmd_private(args):
    """Mark as private."""
    print("Recording.")


def cmd_import_claude_code(args):
    """Import Claude Code transcripts for a post."""
    if not args.slug:
        print("Error: import-claude-code requires a slug argument", file=sys.stderr)
        sys.exit(1)
    try:
        count = import_claude_code(args.slug, args.transcripts, args.root)
        print(f"Added {count} exchanges")
        sys.exit(0)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_site(args):
    """Build the site from a posts folder."""
    try:
        build(args.posts, args.out)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="ledger",
        description="CLI for ledger - replay of exchanges"
    )
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # start subcommand
    start_parser = subparsers.add_parser("start", help="Start recording for a post")
    start_parser.add_argument("slug", nargs="?", default="", help="Post slug")
    start_parser.set_defaults(func=cmd_start)
    
    # end subcommand
    end_parser = subparsers.add_parser("end", help="End recording")
    end_parser.set_defaults(func=cmd_end)
    
    # private subcommand
    private_parser = subparsers.add_parser("private", help="Mark as private")
    private_parser.set_defaults(func=cmd_private)

    # import-claude-code subcommand
    import_parser = subparsers.add_parser("import-claude-code", help="Import Claude Code transcripts for a post")
    import_parser.add_argument("slug", nargs="?", default="", help="Post slug")
    import_parser.add_argument("transcripts", nargs="*", default=[], help="Transcript paths")
    import_parser.add_argument("--root", default=".", help="Root directory")
    import_parser.set_defaults(func=cmd_import_claude_code)

    # site subcommand
    site_parser = subparsers.add_parser("site", help="Build the site from a posts folder")
    site_parser.add_argument("posts", default="posts", nargs="?", help="Posts folder")
    site_parser.add_argument("--out", default="docs", help="Output directory")
    site_parser.set_defaults(func=cmd_site)

    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    args.func(args)


if __name__ == "__main__":
    main()
