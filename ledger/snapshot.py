"""Slice 11: save copies of post.md at each prompt and stop."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from ledger.claude_code import prompt_index

import re

MARKER_CONTEXT = 'This prompt is a ledger marker. Reply with exactly "Recording." and nothing else, and do nothing else: no tools, no other text.'


def _get_slug_from_prompt(prompt):
    """Extract slug from 'ledger start <slug>' command."""
    if not prompt:
        return None
    parts = prompt.strip().split()
    if len(parts) >= 3 and parts[0] == "ledger" and parts[1] == "start":
        slug = parts[2]
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            return slug
        return None
    return None


def _is_marker_prompt(prompt):
    """Check if prompt is a marker (ledger start, ledger end, or ledger private)."""
    if not prompt:
        return False
    parts = prompt.strip().split()
    if len(parts) >= 2 and parts[0] == "ledger" and parts[1] in ("start", "end", "private"):
        return True
    return False


def _session_file(root, session_id):
    """Path to the session file."""
    return root / ".ledger" / "sessions" / f"{session_id}.json"


def _get_session_slug(root, session_id):
    """Get the slug this session is writing, or None if not recording."""
    sf = _session_file(root, session_id)
    if not sf.exists():
        return None
    data = json.loads(sf.read_text())
    return data.get("slug")


def _set_session_slug(root, session_id, slug):
    """Record that this session is writing this post."""
    sf = _session_file(root, session_id)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"slug": slug}))


def _clear_session(root, session_id):
    """Clear the session recording state."""
    sf = _session_file(root, session_id)
    if sf.exists():
        sf.unlink()


def _append_copy(root, slug, event, session_id, n, text, interrupted=None):
    """Append a snapshot copy to the post's snapshots.jsonl file."""
    snapshots_path = root / slug / ".ledger" / "snapshots.jsonl"
    snapshots_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    copy = {
        "event": event,
        "at": now,
        "session_id": session_id,
        "n": n,
        "text": text,
    }
    if interrupted is not None:
        copy["interrupted"] = interrupted

    with open(snapshots_path, "a") as f:
        f.write(json.dumps(copy, ensure_ascii=False) + "\n")


def _get_post_text(root, slug):
    """Get the current text of post.md for this slug."""
    post_path = root / slug / "post.md"
    if not post_path.exists():
        return ""
    return post_path.read_text()


def _copy_transcript(root, transcript_path):
    """Copy the transcript file to .ledger/transcripts/."""
    transcripts_dir = root / ".ledger" / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    name = Path(transcript_path).name
    dest = transcripts_dir / name

    with open(transcript_path, "r") as src:
        content = src.read()
    dest.write_text(content)


def _is_interrupted(root, slug, session_id):
    """Check if this session's last copy is a prompt without an intervening stop."""
    snapshots_path = root / slug / ".ledger" / "snapshots.jsonl"
    if not snapshots_path.exists():
        return False

    lines = snapshots_path.read_text().splitlines()
    for line in reversed(lines):
        try:
            copy = json.loads(line)
            if copy.get("session_id") == session_id:
                return copy.get("event") == "prompt"
        except json.JSONDecodeError:
            continue
    return False


def post_context(root, slug):
    """Return the context string telling the AI where the post is."""
    post_path = Path(root).resolve() / slug / "post.md"
    return f'This session is writing the post "{slug}". The post is the file {post_path} (create it if it doesn\'t exist): write and edit the post there, and nowhere else.'


def hook(event, payload, root):
    """Handle one Claude Code hook call and return what the command prints to stdout."""
    try:
        session_id = payload.get("session_id")
        transcript_path = payload.get("transcript_path")

        if event == "prompt":
            prompt = payload.get("prompt", "")

            marker_out = json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": MARKER_CONTEXT
                }
            })

            slug = _get_session_slug(root, session_id)
            is_marker = _is_marker_prompt(prompt)

            if is_marker:
                start_slug = _get_slug_from_prompt(prompt)
                if start_slug:
                    _set_session_slug(root, session_id, start_slug)
                    slug = start_slug

                end_cmd = prompt.strip().split()
                if len(end_cmd) >= 2 and end_cmd[0] == "ledger" and end_cmd[1] == "end":
                    _clear_session(root, session_id)

            if slug:
                n = 0
                if transcript_path:
                    try:
                        n = prompt_index(transcript_path)
                    except (OSError, FileNotFoundError):
                        n = 0

                text = _get_post_text(root, slug)

                interrupted = None
                if event == "prompt":
                    interrupted = _is_interrupted(root, slug, session_id)

                _append_copy(root, slug, event, session_id, n, text, interrupted=interrupted)

            if is_marker:
                return marker_out
            if slug:
                return json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": post_context(root, slug)}})
            return ""

        elif event == "stop":
            slug = _get_session_slug(root, session_id)
            if slug and transcript_path:
                try:
                    _copy_transcript(root, transcript_path)
                except (OSError, FileNotFoundError):
                    pass

                n = 0
                try:
                    n = prompt_index(transcript_path)
                except (OSError, FileNotFoundError):
                    n = 0

                text = _get_post_text(root, slug)
                _append_copy(root, slug, event, session_id, n, text)

            return ""

        return ""

    except Exception:
        return ""
