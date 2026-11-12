"""Slice 11 (issue #23): save copies.

ledger.snapshot.hook(event, payload, root) handles one Claude Code hook call and returns what the
command prints to stdout ("" for nothing). event is "prompt" (the UserPromptSubmit hook) or
"stop" (the Stop hook); payload is the hook's JSON input (session_id, transcript_path, cwd, and
prompt for "prompt"); root is the posts repo.

`ledger snapshot prompt|stop` reads the payload from stdin, takes root from the
CLAUDE_PROJECT_DIR environment variable, or payload's cwd if that isn't set, prints what hook()
returns, and always exits 0: on bad input or any error it prints nothing at all. It never prints
a decision, so it never blocks the writer.

Sessions: <root>/.ledger/sessions/<session_id>.json holds {"slug": "<slug>"} while the session
is writing a post.

prompt:
- A prompt whose first three words are `ledger start <slug>` writes the session's file (a new
  start replaces the slug).
- Then, if the session is writing a post, append a copy (below) with event "prompt" to that post.
- A prompt whose first two words are `ledger end` then removes the session's file (its copy is
  still taken, to the post it ends).
- On a marker (first two words `ledger start`, `ledger end` or `ledger private`) return
  json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
  "additionalContext": MARKER_CONTEXT}}), whether or not a post is being written. Otherwise "".

stop:
- If the session is writing a post: append a copy with event "stop", and copy the transcript
  file to <root>/.ledger/transcripts/<the transcript's file name> (replacing an older copy).
- Returns "".

A copy is one line appended to <root>/<slug>/.ledger/snapshots.jsonl (folders created as
needed), json.dumps(..., ensure_ascii=False):
    {"event": "prompt" | "stop", "at": <now, UTC, "YYYY-MM-DDTHH:MM:SSZ">,
     "session_id": ..., "n": <ledger.claude_code.prompt_index(transcript_path), 0 if the file
     is missing>, "text": <<root>/<slug>/post.md's text, "" if missing>}
and a prompt copy also has "interrupted": true when this session's last copy in that file is a
prompt copy (the AI was stopped before it finished), false otherwise.

Nothing is written anywhere when the session isn't writing a post.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from ledger.snapshot import MARKER_CONTEXT, hook

LEDGER = Path(sys.executable).parent / "ledger"
MARKER_OUT = json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": MARKER_CONTEXT}})


def transcript(root, name="sess.jsonl", prompts=()):
    p = root / "claude" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    recs = [{"type": "user", "timestamp": "2026-11-12T09:00:00.000Z", "message": {"role": "user", "content": t}} for t in prompts]
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return p


def payload(t, prompt=None, sid="s1"):
    d = {"session_id": sid, "transcript_path": str(t), "cwd": "/elsewhere", "hook_event_name": "UserPromptSubmit" if prompt is not None else "Stop"}
    if prompt is not None:
        d["prompt"] = prompt
    return d


def copies(root, slug="a-post"):
    p = root / slug / ".ledger" / "snapshots.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def write_post(root, text, slug="a-post"):
    (root / slug).mkdir(parents=True, exist_ok=True)
    (root / slug / "post.md").write_text(text)


def test_marker_context_is_the_recording_reply():
    assert "Recording." in MARKER_CONTEXT


def test_start_records_the_session_and_takes_a_copy(tmp_path):
    t = transcript(tmp_path, prompts=["Hi."])
    write_post(tmp_path, "Draft.")
    assert hook("prompt", payload(t, "ledger start a-post"), tmp_path) == MARKER_OUT
    assert json.loads((tmp_path / ".ledger" / "sessions" / "s1.json").read_text()) == {"slug": "a-post"}
    [c] = copies(tmp_path)
    assert set(c) == {"event", "at", "session_id", "n", "text", "interrupted"}
    assert (c["event"], c["session_id"], c["n"], c["text"], c["interrupted"]) == ("prompt", "s1", 1, "Draft.", False)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", c["at"])


def test_prompt_then_stop(tmp_path):
    t = transcript(tmp_path, prompts=["ledger start a-post"])
    hook("prompt", payload(t, "ledger start a-post"), tmp_path)
    hook("stop", payload(t), tmp_path)
    write_post(tmp_path, "Mine.")
    t = transcript(tmp_path, prompts=["ledger start a-post", "Draft it."])
    assert hook("prompt", payload(t, "Draft it."), tmp_path) == ""
    write_post(tmp_path, "Mine. AI's.")
    assert hook("stop", payload(t), tmp_path) == ""
    cs = copies(tmp_path)
    assert [(c["event"], c["n"], c["text"]) for c in cs] == [
        ("prompt", 1, ""), ("stop", 1, ""), ("prompt", 2, "Mine."), ("stop", 2, "Mine. AI's.")]
    assert "interrupted" not in cs[1] and cs[2]["interrupted"] is False


def test_a_prompt_with_no_stop_before_it_is_flagged(tmp_path):
    t = transcript(tmp_path, prompts=["ledger start a-post", "Long draft."])
    hook("prompt", payload(t, "ledger start a-post"), tmp_path)
    hook("stop", payload(t), tmp_path)
    hook("prompt", payload(t, "Long draft."), tmp_path)
    hook("prompt", payload(t, "Shorter."), tmp_path)
    assert [c.get("interrupted") for c in copies(tmp_path)] == [False, None, False, True]


def test_interrupted_looks_only_at_this_session(tmp_path):
    t1, t2 = transcript(tmp_path, "a.jsonl"), transcript(tmp_path, "b.jsonl")
    hook("prompt", payload(t1, "ledger start a-post", sid="s1"), tmp_path)
    hook("prompt", payload(t2, "ledger start a-post", sid="s2"), tmp_path)
    assert [c["interrupted"] for c in copies(tmp_path)] == [False, False]


def test_end_takes_a_last_copy_then_stops_recording(tmp_path):
    t = transcript(tmp_path)
    hook("prompt", payload(t, "ledger start a-post"), tmp_path)
    write_post(tmp_path, "Done.")
    assert hook("prompt", payload(t, "ledger end"), tmp_path) == MARKER_OUT
    assert not (tmp_path / ".ledger" / "sessions" / "s1.json").exists()
    assert copies(tmp_path)[-1]["text"] == "Done."
    n = len(copies(tmp_path))
    hook("stop", payload(t), tmp_path)
    hook("prompt", payload(t, "Something else."), tmp_path)
    assert len(copies(tmp_path)) == n


def test_private_is_a_marker_and_still_copied(tmp_path):
    t = transcript(tmp_path)
    hook("prompt", payload(t, "ledger start a-post"), tmp_path)
    hook("stop", payload(t), tmp_path)
    assert hook("prompt", payload(t, "ledger private my salary"), tmp_path) == MARKER_OUT
    assert copies(tmp_path)[-1]["event"] == "prompt"


def test_another_start_switches_post(tmp_path):
    t = transcript(tmp_path)
    hook("prompt", payload(t, "ledger start a-post"), tmp_path)
    hook("prompt", payload(t, "ledger start b-post"), tmp_path)
    hook("stop", payload(t), tmp_path)
    assert len(copies(tmp_path, "a-post")) == 1
    assert [c["event"] for c in copies(tmp_path, "b-post")] == ["prompt", "stop"]


def test_no_post_started_writes_nothing(tmp_path):
    t = transcript(tmp_path, prompts=["Hi."])
    assert hook("prompt", payload(t, "Hi."), tmp_path) == ""
    assert hook("stop", payload(t), tmp_path) == ""
    assert hook("prompt", payload(t, "ledger end"), tmp_path) == MARKER_OUT
    assert hook("prompt", payload(t, "ledger private x"), tmp_path) == MARKER_OUT
    assert sorted(p.name for p in tmp_path.iterdir()) == ["claude"]


def test_stop_copies_the_transcript(tmp_path):
    t = transcript(tmp_path, "abc.jsonl", prompts=["ledger start a-post"])
    hook("prompt", payload(t, "ledger start a-post"), tmp_path)
    hook("stop", payload(t), tmp_path)
    saved = tmp_path / ".ledger" / "transcripts" / "abc.jsonl"
    assert saved.read_text() == t.read_text()
    t = transcript(tmp_path, "abc.jsonl", prompts=["ledger start a-post", "More."])
    hook("stop", payload(t), tmp_path)
    assert saved.read_text() == t.read_text()


def test_missing_transcript_counts_zero(tmp_path):
    hook("prompt", payload(tmp_path / "nope.jsonl", "ledger start a-post"), tmp_path)
    assert copies(tmp_path)[0]["n"] == 0


def run(event, stdin, cwd, env_root=None):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    if env_root is not None:
        env["CLAUDE_PROJECT_DIR"] = str(env_root)
    return subprocess.run([str(LEDGER), "snapshot", event], input=stdin, capture_output=True, text=True, cwd=cwd, env=env)


def test_the_command_uses_the_project_dir(tmp_path):
    t = transcript(tmp_path)
    p = payload(t, "ledger start a-post")
    r = run("prompt", json.dumps(p), cwd=tmp_path / "claude", env_root=tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == MARKER_OUT
    assert len(copies(tmp_path)) == 1


def test_the_command_falls_back_to_cwd(tmp_path):
    t = transcript(tmp_path)
    p = payload(t, "ledger start a-post")
    p["cwd"] = str(tmp_path)
    r = run("prompt", json.dumps(p), cwd=tmp_path / "claude")
    assert r.returncode == 0
    assert len(copies(tmp_path)) == 1


def test_the_command_never_fails_or_blocks(tmp_path):
    for event, stdin in (("prompt", "not json"), ("stop", ""), ("prompt", "{}"), ("bogus", "{}")):
        r = run(event, stdin, cwd=tmp_path, env_root=tmp_path)
        assert r.returncode == 0, (event, stdin, r.stderr)
        assert r.stdout == ""
        assert "decision" not in r.stdout
