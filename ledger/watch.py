"""Watch for post changes and save snapshots."""

import json
import os
from pathlib import Path


def watch(slug, root, now, sleep, stop):
    """Watch post.md for changes and save snapshots.
    
    - Loop: if stop() is true, return; otherwise check once, then sleep(2), and go round again.
    - A check reads post.md. If its text differs from the last text seen, it appends one line to
      <root>/<slug>/.ledger/snapshots.jsonl (creating the folder if needed):
      json.dumps({"event": "save", "at": now(), "text": text}, ensure_ascii=False).
    - The last text seen starts as the "text" of the file's last line, if snapshots.jsonl exists
      (any event), else None (so the first check copies).
    - post.md missing (for a moment, while an editor saves): the check does nothing, and the last
      text seen stays as it was.
    """
    post_path = Path(root) / slug / "post.md"
    ledger_dir = Path(root) / slug / ".ledger"
    snapshots_path = ledger_dir / "snapshots.jsonl"
    
    # Get the last text from existing snapshots, if any
    last_text = None
    if snapshots_path.exists():
        content = snapshots_path.read_text()
        for line in content.splitlines():
            if line.strip():
                try:
                    record = json.loads(line)
                    if "text" in record:
                        last_text = record["text"]
                except json.JSONDecodeError:
                    pass
    
    while True:
        if stop():
            return
        
        # Check once - read directly and treat FileNotFoundError as missing
        try:
            text = post_path.read_text()
        except FileNotFoundError:
            pass  # Missing for a moment; do nothing, keep last_text unchanged
        else:
            if text != last_text:
                # Ensure ledger directory exists
                ledger_dir.mkdir(parents=True, exist_ok=True)
                
                # Append snapshot
                with open(snapshots_path, "a") as f:
                    snapshot = {"event": "save", "at": now(), "text": text}
                    f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
                
                last_text = text
        
        sleep(2)
