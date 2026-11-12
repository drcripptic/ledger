"""site.diff: diff by author."""

from dataclasses import dataclass
from pathlib import Path
import html
import json
import re
import shutil
from difflib import SequenceMatcher


@dataclass
class Run:
    """A run of text with an author and state."""
    text: str
    by: str
    state: str


def _tokenize(text: str) -> list[str]:
    """Split text into tokens: each word with its trailing whitespace, plus standalone whitespace."""
    return re.findall(r"^\s+|\S+\s*", text)


def _word(token: str) -> str:
    """Extract the word from a token (whitespace stripped)."""
    return token.strip()


def diff(before: list[Run], after_text: str, by: str) -> list[Run]:
    r"""Diff the before runs against after_text, returning new runs with authorship preserved.

    - Text is split into tokens with re.findall(r"^\s+|\S+\s*", text). Each word has trailing whitespace; standalone whitespace is its own token.
    - Tokens are compared by their word alone and aligned with difflib.SequenceMatcher.
    - Runs in `before` with state "removed" are dropped first.
    - equal: keep the by of matching old tokens, state "kept".
    - delete: keep their by, state "removed".
    - insert: new tokens with the given by, state "added".
    - replace: removed old tokens, then added new tokens.
    - Neighbouring tokens with the same by and state are joined.
    """
    after_tokens = _tokenize(after_text)
    after_words = [_word(t) for t in after_tokens]

    # Drop removed runs from before
    kept_runs = [r for r in before if r.state != "removed"]
    before_text = "".join(r.text for r in kept_runs)
    before_tokens = _tokenize(before_text)
    before_words = [_word(t) for t in before_tokens]

    # Map each character position to its run's by value
    char_to_by: list[str] = []
    for run in kept_runs:
        char_to_by.extend([run.by] * len(run.text))

    # Determine each token's by from the run holding its first character
    token_to_by: list[str] = []
    pos = 0
    for token in before_tokens:
        if pos < len(char_to_by):
            token_to_by.append(char_to_by[pos])
        pos += len(token)

    matcher = SequenceMatcher(None, before_words, after_words, autojunk=False)

    result: list[Run] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                result.append(Run(after_tokens[k - i1 + j1], token_to_by[k], "kept"))
        elif tag == "delete":
            for k in range(i1, i2):
                result.append(Run(before_tokens[k], token_to_by[k], "removed"))
        elif tag == "insert":
            for k in range(j1, j2):
                result.append(Run(after_tokens[k], by, "added"))
        elif tag == "replace":
            for k in range(i1, i2):
                result.append(Run(before_tokens[k], token_to_by[k], "removed"))
            for k in range(j1, j2):
                result.append(Run(after_tokens[k], by, "added"))

    # Join neighbouring tokens with the same by and state
    if not result:
        return []

    joined: list[Run] = [result[0]]
    for run in result[1:]:
        prev = joined[-1]
        if run.by == prev.by and run.state == prev.state:
            joined[-1] = Run(prev.text + run.text, prev.by, prev.state)
        else:
            joined.append(run)

    return joined


@dataclass
class Step:
    """A step in the replay."""
    kind: str
    id: str
    label: str
    exchange: dict | None
    runs: list[Run]


def _settle(runs: list[Run]) -> list[Run]:
    """Drop removed runs, set all state to kept, join neighbouring same-by runs."""
    kept = [r for r in runs if r.state != "removed"]
    settled: list[Run] = []
    for run in kept:
        run = Run(run.text, run.by, "kept")
        if settled and run.by == settled[-1].by:
            settled[-1] = Run(settled[-1].text + run.text, run.by, "kept")
        else:
            settled.append(run)
    return settled


def steps(records: list[dict]) -> list[Step]:
    """Turn trace records into replay steps."""
    result: list[Step] = []
    post: list[Run] = []
    edit_count = 0
    withheld_idx = 0
    withheld_count_val = 0
    in_withheld = False
    last_exchange: dict | None = None

    for record in records:
        if record["type"] == "exchange":
            if in_withheld:
                withheld_post = _settle(post)
                result.append(Step("withheld", f"withheld-{withheld_idx}",
                                  f"{withheld_count_val} withheld", None, withheld_post))
                in_withheld = False

            last_exchange = record
            settled = _settle(post)
            result.append(Step("exchange", record["id"], record["id"], record, settled))

        elif record["type"] == "snapshot":
            by = record["by"]
            text = record["text"]

            if in_withheld:
                if by == "ai":
                    post = diff(post, text, "ai")
                elif by == "writer":
                    post = diff(post, text, "writer")
                elif by == "mixed":
                    ai_ranges = record.get("ai") or []
                    post = _apply_mixed_diff(post, text, ai_ranges)

            else:
                if last_exchange is None and not in_withheld:
                    if by == "ai":
                        post = diff(post, text, "ai")
                    elif by == "writer":
                        edit_count += 1
                        new_post = diff(post, text, "writer")
                        result.append(Step("writer", f"edit-{edit_count}", "✎", None, new_post))
                        post = new_post
                    elif by == "mixed":
                        edit_count += 1
                        ai_ranges = record.get("ai") or []
                        new_post = _apply_mixed_diff(post, text, ai_ranges)
                        result.append(Step("mixed", f"edit-{edit_count}", "✎", None, new_post))
                        post = new_post

                elif last_exchange is not None:
                    if by == "ai":
                        post = diff(post, text, "ai")
                        for st in result:
                            if st.kind == "exchange" and st.exchange == last_exchange:
                                st.runs = list(post)
                                break
                    elif by == "writer":
                        edit_count += 1
                        new_post = diff(post, text, "writer")
                        result.append(Step("writer", f"edit-{edit_count}", "✎", None, new_post))
                        post = new_post
                    elif by == "mixed":
                        edit_count += 1
                        ai_ranges = record.get("ai") or []
                        new_post = _apply_mixed_diff(post, text, ai_ranges)
                        result.append(Step("mixed", f"edit-{edit_count}", "✎", None, new_post))
                        post = new_post

        elif record["type"] == "withheld":
            if in_withheld:
                withheld_post = _settle(post)
                result.append(Step("withheld", f"withheld-{withheld_idx}",
                                  f"{withheld_count_val} withheld", None, withheld_post))
            withheld_idx += 1
            withheld_count_val = record["count"]
            in_withheld = True

        elif record["type"] == "published":
            if in_withheld:
                withheld_post = _settle(post)
                result.append(Step("withheld", f"withheld-{withheld_idx}",
                                  f"{withheld_count_val} withheld", None, withheld_post))
                in_withheld = False

            settled = _settle(post)
            version = record["version"]
            result.append(Step("published", f"v{version}", f"Published v{version}", None, settled))

    if in_withheld:
        withheld_post = _settle(post)
        result.append(Step("withheld", f"withheld-{withheld_idx}",
                         f"{withheld_count_val} withheld", None, withheld_post))

    return result


def _apply_mixed_diff(before: list[Run], text: str, ai_ranges: list[list[int]]) -> list[Run]:
    """Apply a mixed diff, splitting added text by ai ranges.

    ai_ranges are [start, end) character offsets into `text` (the after text).
    Added text inside an ai range has by "ai", outside has by "writer".
    """
    before_text = "".join(r.text for r in before if r.state != "removed")
    base_runs = diff(before, text, "writer")

    result: list[Run] = []
    text_pos = 0

    def is_ai(pos: int) -> bool:
        """Check if a position in `text` falls within an ai range."""
        for start, end in ai_ranges:
            if start <= pos < end:
                return True
        return False

    def next_ai_start_after(pos: int) -> float:
        """Find the next ai range start after pos, or inf if none."""
        next_start = float('inf')
        for start, _ in ai_ranges:
            if start > pos:
                next_start = min(next_start, start)
        return next_start

    def end_of_ai_range(pos: int) -> int:
        """Find the end of an ai range that contains pos."""
        for start, end in ai_ranges:
            if start <= pos < end:
                return end
        return 0

    for run in base_runs:
        if run.state == "removed":
            result.append(run)
        elif run.state == "kept":
            result.append(Run(run.text, run.by, "kept"))
            text_pos += len(run.text)
        elif run.state == "added":
            remaining = run.text
            run_text_pos = 0

            while remaining:
                abs_pos = text_pos + run_text_pos
                if is_ai(abs_pos):
                    ai_end = end_of_ai_range(abs_pos)
                    chunk_len = min(ai_end - abs_pos, len(remaining))
                    result.append(Run(remaining[:chunk_len], "ai", "added"))
                    remaining = remaining[chunk_len:]
                    run_text_pos += chunk_len
                else:
                    next_start = next_ai_start_after(abs_pos)
                    if next_start == float('inf'):
                        result.append(Run(remaining, "writer", "added"))
                        break
                    else:
                        end_of_this_run_abs = text_pos + len(run.text)
                        chunk_len = min(int(next_start - abs_pos), len(remaining))
                        result.append(Run(remaining[:chunk_len], "writer", "added"))
                        remaining = remaining[chunk_len:]
                        run_text_pos += chunk_len

            text_pos += len(run.text)

    if not result:
        return []

    joined: list[Run] = [result[0]]
    for run in result[1:]:
        if run.by == joined[-1].by and run.state == joined[-1].state:
            joined[-1] = Run(joined[-1].text + run.text, run.by, run.state)
        else:
            joined.append(run)

    return joined


def _parse_title(md: str) -> str:
    """Extract title from front matter, or 'Untitled' if not present."""
    lines = md.split("\n")
    if not lines[0].strip() == "---":
        return "Untitled"
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i]
        if line.lower().startswith("title:"):
            value = line[len("title:"):]
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            return value
        i += 1
    return "Untitled"


def _get_front_matter(text: str) -> str:
    """Return the front matter block including trailing newlines, or empty string."""
    lines = text.split("\n")
    if not lines[0].strip() == "---":
        return ""
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        i += 1
    if i >= len(lines):
        return ""
    # Front matter is lines[0..i] plus the newlines between them.
    # If there are blank lines after line i, include those too (with their newlines).
    end = i + 1  # Start from the line after closing ---
    while end < len(lines) and lines[end].strip() == "":
        end += 1  # Include all blank lines after closing ---
    # Reconstruct: lines[0..end-1] joined with \n, plus trailing \n if original had content after
    fm_lines = lines[:end]
    result = "\n".join(fm_lines) + "\n"
    return result

def _strip_front_matter(text: str) -> str:
    """Remove front matter block from text if present."""
    fm = _get_front_matter(text)
    if not fm:
        return text
    lines = text.split("\n")
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        i += 1
    if i >= len(lines):
        return text
    i += 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    return "\n".join(lines[i:]) if i < len(lines) else ""


def render(post_md: str, records: list[dict]) -> str:
    """Render a post as a complete HTML page."""
    title = _parse_title(post_md)

    styles = """<style>
.step { display: none; }
.step:target, .step:last-of-type { display: block; }
.step:target ~ .step:last-of-type { display: none; }
.ai { color: blue; }
.writer { color: orange; text-decoration: underline; }
del { text-decoration: line-through; }
del.earlier { opacity: 0.5; }
ins.earlier.ai { opacity: 0.7; }
ins.earlier.writer { opacity: 0.7; }
.row { margin-bottom: 1em; }
.move { margin-top: 1em; }
</style>"""

    recs = records[1:] if records and "ledger_trace" in records[0] else records
    stripped = []
    for r in recs:
        if r.get("type") == "snapshot":
            r = dict(r)
            fm = _get_front_matter(r["text"])
            if fm:
                r["text"] = _strip_front_matter(r["text"])
                # Adjust AI ranges for removed front matter
                if "ai" in r:
                    fm_len = len(fm)
                    adjusted = []
                    for start, end in r["ai"]:
                        # Shift range past the front matter
                        new_start = max(start - fm_len, 0)
                        new_end = end - fm_len
                        # Drop ranges entirely within the front matter (start < fm_len)
                        if start >= fm_len and new_end > 0:
                            adjusted.append([new_start, new_end])
                    r["ai"] = adjusted
        stripped.append(r)
    step_list = steps(stripped)

    # Count published records and get the last one's date
    published_records = [r for r in recs if r.get("type") == "published"]
    revised_note = ""
    if len(published_records) > 1:
        revision_count = len(published_records) - 1
        time_word = "time" if revision_count == 1 else "times"
        last_pub = published_records[-1]
        at = last_pub.get("at", "")
        date_part = at[:10]
        day, month_num, year = int(date_part[8:10]), int(date_part[5:7]), date_part[:4]
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        formatted_date = f"{day} {months[month_num - 1]} {year}"
        revised_note = f'<p class="revised">Revised {revision_count} {time_word}, last on {formatted_date}.</p>'

    nav_links = []
    for step in step_list:
        label_esc = html.escape(step.label)
        nav_links.append(f'<a href="#{step.id}">{label_esc}</a>')
    nav_row = '<nav class="row">' + " ".join(nav_links) + '</nav>'

    section_lines = []
    for i, step in enumerate(step_list):
        prev_link = f'<a href="#{step_list[i - 1].id}">Previous</a>' if i > 0 else ""
        next_link = f'<a href="#{step_list[i + 1].id}">Next</a>' if i < len(step_list) - 1 else ""
        move_nav_parts = [p for p in [prev_link, next_link] if p]
        move_nav = ' '.join(move_nav_parts)

        step_html = render_step(step)
        step_html = step_html.replace("</section>", f'<nav class="move">{move_nav}</nav>\n</section>')
        section_lines.append(step_html)

    sections = "\n".join(section_lines)

    escaped_title = html.escape(title)

    header_after = "" if not revised_note else revised_note + "\n"

    page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escaped_title}</title>
{styles}
</head>
<body>
<h1>{escaped_title}</h1>
{header_after}{nav_row}
<main>
{sections}
</main>
</body>
</html>'''

    return page


def render_step(step: Step) -> str:
    """Render a step as HTML."""
    esc = lambda t: html.escape(t, quote=True)

    lines = []
    lines.append(f'<section id="{esc(step.id)}" class="step {esc(step.kind)}">')
    lines.append('<div class="exchange">')

    if step.kind == "exchange":
        exchange = step.exchange
        if exchange["model"] is not None:
            lines.append(f'<div class="model">{esc(exchange["model"])}</div>')
        lines.append(f'<div class="prompt">{esc(exchange["prompt"])}</div>')
        lines.append(f'<div class="reply">{esc(exchange["reply"])}</div>')

        for tool in exchange.get("tools") or []:
            summary = esc(tool["summary"])
            detail = esc(tool["detail"])
            lines.append(f'<details class="tool"><summary>{summary}</summary><pre>{detail}</pre></details>')
    else:
        if step.kind == "writer":
            text = "The writer&#x27;s own editing."
        elif step.kind == "mixed":
            text = "The writer&#x27;s editing, split from the AI&#x27;s by matching."
        elif step.kind == "withheld":
            n = int(step.label.split()[0])
            suffix = "exchange" if n == 1 else "exchanges"
            text = f"{n} {suffix} withheld by the writer."
        elif step.kind == "published":
            text = step.label + "."
        else:
            text = ""
        lines.append(f'<p class="note">{text}</p>')

    lines.append("</div>")

    post_runs = []
    for run in step.runs:
        by = esc(run.by)
        text = esc(run.text)
        if run.state == "kept":
            post_runs.append(f'<span class="{by}">{text}</span>')
        elif run.state == "added":
            if run.by == "writer":
                post_runs.append(f'<ins class="{by}"><span class="mark">✎</span>{text}</ins>')
            else:
                post_runs.append(f'<ins class="{by}">{text}</ins>')
        elif run.state == "removed":
            post_runs.append(f'<del class="{by}">{text}</del>')

    lines.append('<div class="post">' + "".join(post_runs) + '</div>')
    lines.append('</section>')

    return "\n".join(lines)


def attribute(before_text: str, after_text: str, corpus: str) -> list[list[int]]:
    r"""Return character ranges of added text that repeat at least 6 words from corpus.

    - Tokens are re.findall(r"^\s+|\S+\s*", text). Added tokens are those marked "added" by diff.
    - A token's words are re.findall(r"\w+", token.lower()). Corpus words likewise, from corpus.
    - A stretch is a run of added tokens next to each other in after_text. Within a stretch, every
      6 words in a row (across its tokens) that also appear 6 in a row in the corpus mark the tokens
      from the one holding the first of the 6 words to the one holding the last.
    - A range is the span of marked tokens next to each other (whole tokens, with their whitespace).
    """
    # Tokenize after_text and identify which tokens are added via diff
    after_tokens = _tokenize(after_text)

    # Build a map from character position to token index in after_text
    pos_to_token: list[int] = []
    pos = 0
    for i, token in enumerate(after_tokens):
        for _ in range(len(token)):
            pos_to_token.append(i)
        pos += len(token)

    # Use diff to find added text spans
    added_runs = diff([Run(before_text, "writer", "kept")], after_text, "ai")

    # Build list of added runs with their positions in after_text
    # Only count position for non-removed runs since removed text is not in after_text
    pos_in_after = 0
    added_runs_with_pos: list[tuple[int, str]] = []  # (start_pos_in_after, text)
    
    for run in added_runs:
        if run.state == "added":
            added_runs_with_pos.append((pos_in_after, run.text))
            pos_in_after += len(run.text)
        elif run.state == "kept":
            pos_in_after += len(run.text)
        # removed runs don't contribute to after_text positions

    # Build list of consecutive added tokens in order from the added runs
    added_with_pos: list[tuple[int, str]] = []
    for start_pos, run_text in added_runs_with_pos:
        # Tokenize the run text and compute token positions within it
        run_tokens = _tokenize(run_text)
        pos_in_run = 0
        for token in run_tokens:
            added_with_pos.append((start_pos + pos_in_run, token))
            pos_in_run += len(token)

    if not added_with_pos:
        return []

    # Extract all words from corpus (lowercase only)
    corpus_words = re.findall(r"\w+", corpus.lower())

    # Build a set of all 6-word sequences in corpus
    corpus_sequences = set()
    for i in range(len(corpus_words) - 5):
        seq = tuple(corpus_words[i:i+6])
        corpus_sequences.add(seq)

    # Group added tokens into stretches (runs of added text separated by non-added)
    stretches: list[list[tuple[int, str]]] = []
    current_stretch: list[tuple[int, str]] = []

    for start, token in added_with_pos:
        if not current_stretch or start == current_stretch[-1][0] + len(current_stretch[-1][1]):
            # This token is adjacent to the previous one
            current_stretch.append((start, token))
        else:
            # Gap - save current stretch and start a new one
            if current_stretch:
                stretches.append(current_stretch)
            current_stretch = [(start, token)]

    if current_stretch:
        stretches.append(current_stretch)

    # For each stretch, find which tokens contain matching 6-word sequences
    marked_ranges: list[list[int]] = []

    for stretch in stretches:
        # Extract all words from this stretch (lowercase), tracking which token each word comes from
        stretch_words: list[tuple[str, int]] = []  # (word, token_idx)
        for i, (start, token) in enumerate(stretch):
            words = re.findall(r"\w+", token.lower())
            for w in words:
                stretch_words.append((w, i))

        # Find 6-word sequences that match corpus
        matched_tokens: set[int] = set()
        for i in range(len(stretch_words) - 5):
            seq = tuple(stretch_words[j][0] for j in range(i, i+6))
            if seq in corpus_sequences:
                # Mark tokens from first to last word of this match
                first_token_idx = stretch_words[i][1]
                last_token_idx = stretch_words[i+5][1]
                for t in range(first_token_idx, last_token_idx + 1):
                    matched_tokens.add(t)

        if not matched_tokens:
            continue

        # Group consecutive matched tokens into ranges
        sorted_matched = sorted(matched_tokens)
        current_range_tokens: list[int] = []

        for idx, i in enumerate(sorted_matched):
            if not current_range_tokens or i == current_range_tokens[-1] + 1:
                # Consecutive token - add to current range
                current_range_tokens.append(i)
            else:
                # Gap - output current range and start new one
                if current_range_tokens:
                    start_pos = stretch[current_range_tokens[0]][0]
                    end_pos = stretch[current_range_tokens[-1]][0] + len(stretch[current_range_tokens[-1]][1])
                    marked_ranges.append([start_pos, end_pos])
                current_range_tokens = [i]

        # Output final range
        if current_range_tokens:
            start_pos = stretch[current_range_tokens[0]][0]
            end_pos = stretch[current_range_tokens[-1]][0] + len(stretch[current_range_tokens[-1]][1])
            marked_ranges.append([start_pos, end_pos])

    return marked_ranges


def build(posts: Path, out: Path) -> list[str]:
    """Build the published site from a posts folder into out.

    Returns the slugs it wrote, in index order (newest first by last published record's "at", then by slug).

    - A post is a folder <posts>/<slug> holding trace.jsonl. Folders starting with "." are skipped.
    - A post is published if its trace has a record with type "published"; others are skipped.
    - For each published post: <out>/<slug>/index.html, <out>/<slug>/post.md (if exists), <out>/<slug>/trace.jsonl
    - Creates <out>/index.html listing published posts newest first
    - Creates <out>/.nojekyll (empty)
    - Nothing from .ledger/ is copied. Nothing else is written outside out.
    """
    posts = Path(posts)
    out = Path(out)

    # Create output directory if needed
    out.mkdir(parents=True, exist_ok=True)

    # Collect published posts with their last published record's "at" for sorting
    published_posts: list[tuple[str, str]] = []  # (slug, last_published_at)

    if not posts.exists():
        slugs = []
    else:
        for entry in posts.iterdir():
            if not entry.is_dir():
                continue
            slug = entry.name
            if slug.startswith("."):
                continue

            trace_path = entry / "trace.jsonl"
            if not trace_path.exists():
                continue

            # Read trace records
            records = []
            with open(trace_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))

            # Check if published and find last published record's "at"
            last_published_at = None
            has_published = False
            for r in records:
                if r.get("type") == "published":
                    has_published = True
                    at = r.get("at", "")
                    if last_published_at is None or at > last_published_at:
                        last_published_at = at

            if not has_published:
                continue

            published_posts.append((slug, last_published_at))

        # Proper sort: newest first by "at", then alphabetically by slug for ties
        sorted_posts = []
        grouped = {}
        for slug, at in published_posts:
            if at not in grouped:
                grouped[at] = []
            grouped[at].append(slug)
        
        # Sort groups by at descending
        for at in sorted(grouped.keys(), reverse=True):
            # Within each group, sort slugs alphabetically (ascending)
            for slug in sorted(grouped[at]):
                sorted_posts.append((slug, at))
        
        published_posts = sorted_posts

    slugs = [p[0] for p in published_posts]

    # Build each published post
    for slug in slugs:
        post_dir = posts / slug
        out_slug = out / slug
        out_slug.mkdir(parents=True, exist_ok=True)

        trace_path = post_dir / "trace.jsonl"
        records = []
        with open(trace_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        # Copy trace.jsonl byte-for-byte
        shutil.copy2(trace_path, out_slug / "trace.jsonl")

        # Copy post.md if it exists (byte-for-byte)
        post_md_path = post_dir / "post.md"
        if post_md_path.exists():
            shutil.copy2(post_md_path, out_slug / "post.md")

        # Generate index.html
        post_md_text = ""
        if post_md_path.exists():
            with open(post_md_path, "rb") as f:
                post_md_bytes = f.read()
            post_md_text = post_md_bytes.decode("utf-8")

        html_content = render(post_md_text, records)
        (out_slug / "index.html").write_text(html_content)

    # Write .nojekyll
    (out / ".nojekyll").write_text("")

    # Build index.html listing published posts
    index_body_items = []
    for slug in slugs:
        post_dir = posts / slug
        post_md_path = post_dir / "post.md"
        if post_md_path.exists():
            with open(post_md_path, "rb") as f:
                post_md_bytes = f.read()
            post_md_text = post_md_bytes.decode("utf-8")
        else:
            post_md_text = ""

        title = _parse_title(post_md_text)
        escaped_title = html.escape(title)
        index_body_items.append(f'<li><a href="{slug}/">{escaped_title}</a></li>')

    index_html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Posts</title>
<style>
.step {{ display: none; }}
.step:target, .step:last-of-type {{ display: block; }}
.step:target ~ .step:last-of-type {{ display: none; }}
.ai {{ color: blue; }}
.writer {{ color: orange; text-decoration: underline; }}
del {{ text-decoration: line-through; }}
del.earlier {{ opacity: 0.5; }}
ins.earlier.ai {{ opacity: 0.7; }}
ins.earlier.writer {{ opacity: 0.7; }}
.row {{ margin-bottom: 1em; }}
.move {{ margin-top: 1em; }}
</style>
</head>
<body>
<h1>Posts</h1>
<ul>
{chr(10).join(index_body_items)}
</ul>
</body>
</html>'''

    (out / "index.html").write_text(index_html)

    return slugs
