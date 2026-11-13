"""The post's file, told to the AI (a fix to slice 11, issue #23).

The writer types `ledger start <slug>` and then just writes with the AI. They never say where the
post goes: the hook tells the AI on every prompt while the session is writing a post.

ledger.snapshot.post_context(root, slug) returns exactly:
    'This session is writing the post "<slug>". The post is the file <root>/<slug>/post.md
     (create it if it doesn\'t exist): write and edit the post there, and nowhere else.'
on one line (the two parts joined by one space), where <root>/<slug>/post.md is the absolute
path (Path(root).resolve() / slug / "post.md").

hook("prompt", ...) returns json.dumps({"hookSpecificOutput": {"hookEventName":
"UserPromptSubmit", "additionalContext": post_context(root, slug)}}) for a prompt that isn't a
marker while the session is writing a post; "" for one when it isn't. Markers are unchanged.
"""

import json
from pathlib import Path

from ledger.snapshot import MARKER_CONTEXT, hook, post_context


def transcript(root, prompts=()):
    p = root / "claude" / "sess.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps({"type": "user", "timestamp": "2026-11-13T09:00:00.000Z",
                                     "message": {"role": "user", "content": t}}) + "\n" for t in prompts))
    return p


def say(root, t, prompt, sid="s1"):
    return hook("prompt", {"session_id": sid, "transcript_path": str(t), "cwd": "/elsewhere",
                           "hook_event_name": "UserPromptSubmit", "prompt": prompt}, root)


def out(context):
    return json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}})


def test_the_text(tmp_path):
    path = tmp_path.resolve() / "goals-of-ledger" / "post.md"
    assert post_context(tmp_path, "goals-of-ledger") == (
        f'This session is writing the post "goals-of-ledger". The post is the file {path} '
        "(create it if it doesn't exist): write and edit the post there, and nowhere else.")


def test_the_path_is_absolute_even_from_a_relative_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert str(tmp_path.resolve() / "p" / "post.md") in post_context(Path("."), "p")


def test_every_prompt_in_a_span_names_the_file(tmp_path):
    t = transcript(tmp_path, ["ledger start why", "Write it.", "Shorter."])
    assert say(tmp_path, t, "ledger start why") == out(MARKER_CONTEXT)
    assert say(tmp_path, t, "Write it.") == out(post_context(tmp_path, "why"))
    assert say(tmp_path, t, "Shorter.") == out(post_context(tmp_path, "why"))


def test_a_new_start_names_the_new_post(tmp_path):
    t = transcript(tmp_path)
    say(tmp_path, t, "ledger start one")
    say(tmp_path, t, "ledger start two")
    assert say(tmp_path, t, "Go.") == out(post_context(tmp_path, "two"))


def test_outside_a_span_nothing(tmp_path):
    t = transcript(tmp_path)
    assert say(tmp_path, t, "Hello.") == ""
    say(tmp_path, t, "ledger start why")
    say(tmp_path, t, "ledger end")
    assert say(tmp_path, t, "Hello again.") == ""


def test_only_this_session(tmp_path):
    t = transcript(tmp_path)
    say(tmp_path, t, "ledger start why", sid="s1")
    assert say(tmp_path, t, "Hello.", sid="s2") == ""


def test_markers_are_unchanged_inside_a_span(tmp_path):
    t = transcript(tmp_path)
    say(tmp_path, t, "ledger start why")
    assert say(tmp_path, t, "ledger private my salary") == out(MARKER_CONTEXT)
    assert say(tmp_path, t, "ledger end") == out(MARKER_CONTEXT)
