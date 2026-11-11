"""CLI for ledger - replay of exchanges."""

import argparse
from pathlib import Path


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
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    args.func(args)


if __name__ == "__main__":
    import sys
    main()
