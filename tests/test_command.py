"""Slice 1 (issue #13): an installed `ledger` command, with the three markers as no-op subcommands."""

import subprocess
import sys
from pathlib import Path

LEDGER = Path(sys.executable).parent / "ledger"


def run(*args, cwd="/"):
    return subprocess.run([str(LEDGER), *args], capture_output=True, text=True, cwd=cwd)


def test_installed_as_a_command():
    assert LEDGER.exists()


def test_help_from_any_folder(tmp_path):
    r = run("--help", cwd=tmp_path)
    assert r.returncode == 0
    for sub in ("start", "end", "private"):
        assert sub in r.stdout


def test_markers_do_nothing_but_say_recording(tmp_path):
    for args in (("start", "a-post"), ("end",), ("private",)):
        r = run(*args, cwd=tmp_path)
        assert r.returncode == 0
        assert r.stdout.strip() == "Recording."
    assert list(tmp_path.iterdir()) == []


def test_start_needs_a_slug(tmp_path):
    assert run("start", cwd=tmp_path).returncode != 0
