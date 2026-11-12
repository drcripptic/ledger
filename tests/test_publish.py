"""Slice 9 (issue #21): ledger publish.

ledger.publish.publish(slug, root, transcripts=(), out="docs") publishes one post from the posts
repo at root and returns the new version number. `ledger publish <slug> [transcript ...]
[--out DIR]` does the same with root the current folder, prints "Published <slug> v<N>.", and
on a refusal prints the reason to stderr (no traceback) and exits 1.

In order:
1. Import: ledger.importer.import_claude_code(slug, transcripts, root). Its ValueError (no span)
   is a refusal.
2. A final writer step: if the trace has a snapshot record and <root>/<slug>/post.md's text
   differs from the last snapshot's text, append {"type": "snapshot", "by": "writer",
   "after": <the id of the trace's last exchange, or the last id of its last withheld record>,
   "text": <post.md's text>}. A trace with no snapshot gets none.
3. Scan the trace's text for secrets (below). On a match, raise Refused (a ValueError) naming the
   kind and the record's id (an exchange's id, a withheld's first id, or "snapshot") and append
   nothing more.
4. Append {"type": "published", "version": <published records so far + 1>, "at": <now, UTC,
   "YYYY-MM-DDTHH:MM:SSZ">}.
5. Build the site: ledger.site.build(root, root / out).

Secrets, each with its kind:
- "API key": sk-<20 or more of A-Za-z0-9_->, AKIA<16 of A-Z0-9>, AIza<35 of A-Za-z0-9_->.
- "token": gh[pousr]_<36 or more of A-Za-z0-9>, github_pat_<22 or more of A-Za-z0-9_>,
  xox[abprs]-<10 or more of A-Za-z0-9->, ops_<40 or more of A-Za-z0-9_->, and a JWT
  (eyJ<10 or more of A-Za-z0-9_->.eyJ<10 or more of A-Za-z0-9_->.).
- "private key": -----BEGIN <words, or none> PRIVATE KEY-----.
- "home-folder path": /Users/<name> or /home/<name>, where <name> is one or more of A-Za-z0-9._-
  (/Users/Shared included).

Home folders: the importer writes the writer's own home folder (Path.home()) as "~" in every
prompt, reply, tool summary and tool detail, so their own paths never trip the scan.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ledger.importer import import_claude_code
from ledger.publish import Refused, publish

LEDGER = Path(sys.executable).parent / "ledger"


def at(minute, second=0):
    return f"2026-11-12T09:{minute:02d}:{second:02d}.500Z"


def turn(text, minute, reply=None, tools=()):
    content = [{"type": "text", "text": reply or ("Re: " + text)}]
    content += [{"type": "tool_use", "id": f"t{minute}{i}", "name": n, "input": inp} for i, (n, inp) in enumerate(tools)]
    return [{"type": "user", "timestamp": at(minute), "message": {"role": "user", "content": text}},
            {"type": "assistant", "timestamp": at(minute, 10), "message": {"role": "assistant", "model": "claude-opus-5-5", "content": content}}]


def session(root, *turns, sid="s1"):
    p = root / "claude" / f"{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for t in turns for r in t))
    return p


def post(root, text, slug="a-post"):
    (root / slug).mkdir(parents=True, exist_ok=True)
    (root / slug / "post.md").write_text(text)


def copies(root, items, slug="a-post"):
    d = root / slug / ".ledger"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "snapshots.jsonl", "a") as f:
        for event, n, text in items:
            c = {"event": event, "at": "2026-11-12T09:00:00Z", "session_id": "s1", "n": n, "text": text}
            if event == "prompt":
                c["interrupted"] = False
            f.write(json.dumps(c) + "\n")


def trace(root, slug="a-post"):
    return [json.loads(l) for l in (root / slug / "trace.jsonl").read_text().splitlines()]


@pytest.fixture(autouse=True)
def home(monkeypatch):
    """The writer's home, as a path the scan would refuse if it weren't written as ~."""
    h = Path("/home/writer")
    monkeypatch.setenv("HOME", str(h))
    return h


def test_a_clean_publish(tmp_path):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Draft it.", 2))
    post(tmp_path, "---\ntitle: A post\n---\n\nText.\n")
    assert publish("a-post", tmp_path, [t]) == 1
    recs = trace(tmp_path)
    assert [r.get("type") for r in recs] == [None, "exchange", "published"]
    assert recs[-1]["version"] == 1 and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", recs[-1]["at"])
    page = (tmp_path / "docs" / "a-post" / "index.html").read_text()
    assert "<title>A post</title>" in page
    assert (tmp_path / "docs" / ".nojekyll").exists()


def test_a_changed_final_file_is_a_writer_step(tmp_path):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Draft it.", 2))
    copies(tmp_path, [("prompt", 0, ""), ("stop", 1, ""), ("prompt", 1, ""), ("stop", 2, "AI text.")])
    post(tmp_path, "AI text. My last words.")
    publish("a-post", tmp_path, [t])
    recs = trace(tmp_path)
    assert recs[-2] == {"type": "snapshot", "by": "writer", "after": "x1", "text": "AI text. My last words."}
    assert recs[-1]["type"] == "published"


def test_an_unchanged_final_file_adds_no_step(tmp_path):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Draft it.", 2))
    copies(tmp_path, [("prompt", 0, ""), ("stop", 1, ""), ("prompt", 1, ""), ("stop", 2, "AI text.")])
    post(tmp_path, "AI text.")
    publish("a-post", tmp_path, [t])
    assert [r.get("type") for r in trace(tmp_path)] == [None, "exchange", "snapshot", "published"]


def test_no_copies_no_final_step(tmp_path):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Draft it.", 2))
    post(tmp_path, "Written somehow.")
    publish("a-post", tmp_path, [t])
    assert [r.get("type") for r in trace(tmp_path)] == [None, "exchange", "published"]


def test_final_step_after_a_withheld_stretch(tmp_path):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("One.", 2), turn("ledger private x", 3))
    copies(tmp_path, [("prompt", 0, ""), ("stop", 1, ""), ("prompt", 1, ""), ("stop", 2, "A.")])
    post(tmp_path, "A. B.")
    publish("a-post", tmp_path, [t])
    assert trace(tmp_path)[-2]["after"] == "x2"


def test_a_second_publish_is_version_2(tmp_path):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Draft it.", 2))
    post(tmp_path, "Text.")
    assert publish("a-post", tmp_path, [t]) == 1
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Draft it.", 2), turn("ledger start a-post", 30), turn("Revise.", 31))
    assert publish("a-post", tmp_path, [t]) == 2
    recs = trace(tmp_path)
    assert [r.get("type") for r in recs] == [None, "exchange", "published", "exchange", "published"]
    assert recs[-1]["version"] == 2


SECRETS = [
    ("API key", "sk-ant-api03-" + "a" * 30),
    ("API key", "AKIA" + "ABCDEFGHIJKLMNOP"),
    ("API key", "AIza" + "B" * 35),
    ("token", "ghp_" + "c" * 36),
    ("token", "github_pat_" + "d" * 30),
    ("token", "xoxb-" + "1234567890-abc"),
    ("token", "ops_" + "e" * 45),
    ("token", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.sig"),
    ("private key", "-----BEGIN OPENSSH PRIVATE KEY-----"),
    ("private key", "-----BEGIN PRIVATE KEY-----"),
    ("home-folder path", "/Users/someone/notes.txt"),
    ("home-folder path", "/home/someone/notes.txt"),
]


@pytest.mark.parametrize("kind,secret", SECRETS)
def test_each_kind_of_secret_is_refused(tmp_path, kind, secret):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Fine.", 2), turn("Look.", 3, reply="Found " + secret + " here."))
    post(tmp_path, "Text.")
    with pytest.raises(Refused) as e:
        publish("a-post", tmp_path, [t])
    assert kind in str(e.value) and "x2" in str(e.value)
    assert not any(r.get("type") == "published" for r in trace(tmp_path))
    assert not (tmp_path / "docs").exists()


def test_a_secret_in_a_snapshot_is_refused(tmp_path):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Draft.", 2))
    copies(tmp_path, [("prompt", 0, ""), ("stop", 1, ""), ("prompt", 1, ""), ("stop", 2, "key ghp_" + "f" * 36)])
    post(tmp_path, "key ghp_" + "f" * 36)
    with pytest.raises(Refused) as e:
        publish("a-post", tmp_path, [t])
    assert "token" in str(e.value) and "snapshot" in str(e.value)


def test_the_writers_own_home_is_written_as_tilde(tmp_path, home):
    t = session(tmp_path, turn("ledger start a-post", 1),
                turn(f"Read {home}/posts/a-post/post.md", 2, reply=f"Read {home}.", tools=[("Read", {"file_path": f"{home}/posts/a-post/post.md"})]))
    import_claude_code("a-post", [t], tmp_path)
    x = trace(tmp_path)[1]
    assert x["prompt"] == "Read ~/posts/a-post/post.md"
    assert x["reply"] == "Read ~."
    assert x["tools"][0]["summary"] == "Read: ~/posts/a-post/post.md"
    assert str(home) not in x["tools"][0]["detail"] and "~/posts/a-post/post.md" in x["tools"][0]["detail"]


def test_a_home_path_publishes_once_written_as_tilde(tmp_path, home):
    t = session(tmp_path, turn("ledger start a-post", 1), turn(f"Edit {home}/posts/a-post/post.md", 2))
    post(tmp_path, "Text.")
    assert publish("a-post", tmp_path, [t]) == 1


def test_the_command(tmp_path, home):
    t = session(tmp_path, turn("ledger start a-post", 1), turn("Draft it.", 2))
    post(tmp_path, "Text.")
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    r = subprocess.run([str(LEDGER), "publish", "a-post", str(t)], capture_output=True, text=True, cwd=tmp_path, env=env)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "Published a-post v1."
    assert (tmp_path / "docs" / "a-post" / "index.html").exists()
    t2 = session(tmp_path, turn("ledger start b-post", 1), turn("Leak ghp_" + "g" * 36, 2), sid="s2")
    post(tmp_path, "B.", slug="b-post")
    r = subprocess.run([str(LEDGER), "publish", "b-post", str(t2)], capture_output=True, text=True, cwd=tmp_path, env=env)
    assert r.returncode == 1
    assert "token" in r.stderr and "Traceback" not in r.stderr
