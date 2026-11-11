"""The `ledger` command."""

import argparse
import sys


def _recording(args):
    # A marker: the writer types it as a prompt, and the hooks act on it.
    # As a command it does nothing, so a shell attempt is harmless.
    print("Recording.")
    return 0


def parser():
    p = argparse.ArgumentParser(prog="ledger", description="AI-assisted writing, with full observability.")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("start", help="marker: start recording a post (does nothing as a command)")
    s.add_argument("slug")
    s.set_defaults(func=_recording)
    sub.add_parser("end", help="marker: stop recording (does nothing as a command)").set_defaults(func=_recording)
    sub.add_parser("private", help="marker: withhold this exchange (does nothing as a command)").set_defaults(func=_recording)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
