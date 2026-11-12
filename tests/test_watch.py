"""Slice 15 (issue #27): copy on every save.

ledger.watch.watch(slug, root, now, sleep, stop) watches <root>/<slug>/post.md:

- Loop: if stop() is true, return; otherwise check once, then sleep(2), and go round again.
- A check reads post.md. If its text differs from the last text seen, it appends one line to
  <root>/<slug>/.ledger/snapshots.jsonl (creating the folder if needed):
  json.dumps({"event": "save", "at": now(), "text": text}, ensure_ascii=False).
- The last text seen starts as the "text" of the file's last line, if snapshots.jsonl exists
  (any event), else None (so the first check copies).
- post.md missing (for a moment, while an editor saves): the check does nothing, and the last
  text seen stays as it was.

`ledger watch <slug>` runs it with root the current folder, now() the UTC time like
"2026-11-12T10:00:00Z", the real time.sleep, and stop() never true; Ctrl-C ends it quietly
(exit 0, nothing on stderr).
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ledger.watch import watch

LEDGER = Path(sys.executable).parent / "ledger"


def lines(root):
    p = root / "a-post" / ".ledger" / "snapshots.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def run(root, edits):
    """Run watch; before check k (from 0), apply edits[k] (None: leave, "": delete, else write)."""
    post = root / "a-post" / "post.md"
    post.parent.mkdir(parents=True, exist_ok=True)
    k = {"n": 0}
    clock = iter(f"2026-11-12T10:00:{s:02d}Z" for s in range(0, 60, 2))
    slept = []

    def stop():
        n = k["n"]
        if n >= len(edits):
            return True
        e = edits[n]
        if e == "":
            post.unlink(missing_ok=True)
        elif e is not None:
            post.write_text(e)
        k["n"] += 1
        return False

    watch("a-post", root, lambda: next(clock), slept.append, stop)
    return slept


def test_a_change_is_copied(tmp_path):
    slept = run(tmp_path, ["One.", None, "One. Two."])
    assert lines(tmp_path) == [
        {"event": "save", "at": "2026-11-12T10:00:00Z", "text": "One."},
        {"event": "save", "at": "2026-11-12T10:00:02Z", "text": "One. Two."},
    ]
    assert slept == [2, 2, 2]


def test_no_change_no_copy(tmp_path):
    run(tmp_path, ["Same.", None, None, "Same."])
    assert [l["text"] for l in lines(tmp_path)] == ["Same."]


def test_starts_from_the_last_copy(tmp_path):
    d = tmp_path / "a-post" / ".ledger"
    d.mkdir(parents=True)
    (d / "snapshots.jsonl").write_text(json.dumps({"event": "stop", "at": "x", "session_id": "s", "n": 1, "text": "Old."}) + "\n")
    run(tmp_path, ["Old.", "New."])
    assert [l["text"] for l in lines(tmp_path)] == ["Old.", "New."]
    assert lines(tmp_path)[1]["event"] == "save"


def test_missing_for_a_moment(tmp_path):
    run(tmp_path, ["One.", "", "One.", "", "Two."])
    assert [l["text"] for l in lines(tmp_path)] == ["One.", "Two."]


def test_stop_before_any_check(tmp_path):
    slept = run(tmp_path, [])
    assert slept == [] and lines(tmp_path) == []


def test_the_command_copies_and_ctrl_c_ends_it(tmp_path):
    (tmp_path / "a-post").mkdir()
    (tmp_path / "a-post" / "post.md").write_text("Hello.")
    p = subprocess.Popen([str(LEDGER), "watch", "a-post"], cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 10
    while not lines(tmp_path) and time.time() < deadline:
        time.sleep(0.1)
    p.send_signal(signal.SIGINT)
    out, err = p.communicate(timeout=10)
    assert p.returncode == 0 and err == ""
    [l] = lines(tmp_path)
    assert l["text"] == "Hello." and l["event"] == "save" and len(l["at"]) == 20 and l["at"].endswith("Z")
