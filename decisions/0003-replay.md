# 0003: The post page is a replay, the writer's changes are told apart from the AI's, and a post can be revised

Status: accepted, 11 Nov 2026. It replaces "What the reader sees" in decision 0002, and two more lines of 0002: the published site needs no JavaScript, and `docs/` holds no `attribution.json`. It changes decision 0001's trace format as set out under "The trace" below, and replaces 0001's secret scan with the one in `ledger publish`. The writer agreed 0001 and this decision together.

## The problem

A reader wants to see how a post came to be: what it looked like at each stage of prompting, which words the writer wrote and which the AI did, and how it changed after it was first published. The post beside a list of its exchanges doesn't show that.

## Agreed

### The page

- **One step per stage.** A row of steps runs across the top: each exchange (`x1`, `x2`, …), each stretch of the writer's own editing between prompts (marked ✎), a step for withheld exchanges ("2 exchanges withheld by the writer"), and "Published" at the end. Previous and Next move through them.
- **At each step:** the exchange on the left (its prompt, its reply, and its tool calls as collapsed lines), and the post as it stood after that step on the right, without its front matter.
- **Changes are marked by who made them.** In the step's own change, the AI's added text is blue and the writer's is orange with an underline and a ✎ marker, so they differ by more than colour. Removed text is struck through. Earlier changes keep a faint tint of the same colour, so any stage shows who wrote each part.
- **A withheld step** shows the post as it stood after those exchanges, never the drafts in between.
- **No JavaScript.** Each step is a section of one static page, and Previous and Next are links to it. Nothing is loaded from other sites.

### Revisions after publishing

- The writer revises a published post by typing `ledger start <slug>` again, in any session.
- A later import only appends records newer than the trace's last one.
- The step row continues past "Published" through the revision's steps to "Published v2", and so on.
- `/<slug>/` shows the latest version and says how many times, and when, it was revised. Each version keeps its own address, `/<slug>/v1/`, `/<slug>/v2/`, and an earlier version's page never changes.

### What the writer does

- In Claude Code, in the posts repo: type `ledger start <slug>` (Claude replies "Recording." and does nothing else), write, prompting and editing `<slug>/post.md` as usual, and type `ledger end` when done. The posts repo commits the hook settings, so the writer sets nothing up; a session started before they were merged needs restarting once.
- With another AI tool: run `ledger watch <slug>` while writing.
- Say publish. `ledger publish <slug>` imports the history, adds the final writer step (below), scans the trace for secrets (API keys, tokens, private keys, home-folder paths) and refuses on a match, then appends a `published` record and builds the site. The importer writes the writer's own home folder as `~`, so their own paths don't trip the scan; anyone else's still does. Claude also reads the trace for anything the writer didn't mean to publish before it goes live.

### Capturing the writer's changes

- **Claude Code: hooks.** The posts repo's `.claude/settings.json` runs `ledger snapshot prompt` when the writer sends a prompt and `ledger snapshot stop` when the AI finishes. Each saves a copy of `post.md` to `<slug>/.ledger/snapshots.jsonl`, with the session id and the prompt's number. The prompt hook records which post a session is writing in the repo-level `.ledger/sessions/<session_id>.json` on `ledger start`, and clears it on `ledger end`. The stop hook also copies the session's transcript into `.ledger/transcripts/`, so a later revision still has the earlier history whatever Claude Code deletes.
- **Markers.** `ledger start <slug>`, `ledger end` and `ledger private` are prompts. The prompt hook adds context telling Claude to reply "Recording." and do nothing else, and each is also a `ledger` subcommand that does nothing. Marker prompts aren't exchanges, but they count when prompts are numbered.
- **Who changed what.** From a prompt's copy to the next stop's copy is the AI's change. From a stop's copy to the next prompt's copy is the writer's. A prompt with no stop since the last one (the writer interrupted the AI) makes the change since the last copy mixed.
- **Joining copies to exchanges** is by prompt number, not by clock time. One shared function numbers the writer's prompts in a transcript, skipping tool results, subagent entries and compaction summaries; the hooks and the importer both use it. When the prompt hook runs, the transcript doesn't yet hold that prompt (checked on a real session), so a prompt copy's number counts the prompts before it, and a stop copy's counts the prompt it follows.
- **Any other AI tool: the fallback.** `ledger watch <slug>` saves a copy whenever `post.md` changes. Those changes, and mixed hook changes, are split by matching at import, against everything the AI wrote so far in the full transcript: its replies and the text of its file writes and edits. Added text that repeats at least 6 words in a row of that, ignoring case, spacing and punctuation, is the AI's; the rest is the writer's. Where both kinds of copy exist, the hooks win.
- **At publish,** if `post.md` differs from the last copy, that difference is a final writer step, so "Published" always matches the page's last step. A post with no copies (written before the hooks) gets no final step, and its replay shows the exchanges only.
- **Withheld stretches:** withheld exchanges keep their ids, so the ids show a gap, and a `withheld` record lists them in `ids`. Copies taken inside a withheld stretch, and the writer's copies after it until the next shown exchange, fold into the withheld step, so no in-between draft is published: the importer writes them as one snapshot, the last copy's text.
- **Kept out of `docs/`:** `.ledger/`; tool details that read or write anything under `.ledger/` (the importer redacts them); session ids and transcript paths; and any post with no `published` record. A version's pages, once written, are never rewritten.

### The trace (changes to decision 0001)

- **`snapshot`** gains `by`: `"ai"`, `"writer"` or `"mixed"`. One follows each exchange that changed the post (`by: "ai"`), and one follows each stretch of the writer's own editing (`by: "writer"`). Copies from `ledger watch` are written `by: "mixed"`. A mixed snapshot also carries `ai`: the character ranges of its added text that matching found to be the AI's. A snapshot carries only `type`, `by`, `after`, `text` and `ai`.
- **`published`**, a new record: `{"type": "published", "version": 1, "at": "..."}`, written at each publish.
- **A post's trace covers every span** that started it, across sessions, in time order. Exchange ids run on across spans and are never reused. A trace only ever grows.
- **Published files:** `docs/` holds each published post's page, `post.md` and `trace.jsonl`. `attribution.json` isn't written in the MVP (see Open).

## Open

- The writer typing in `post.md` while the AI replies: matching splits it, but the writer's words that happen to repeat the reply are credited to the AI.
- `attribution.json` and paragraph-level attribution: the replay may replace them.
- Importers for AI tools other than Claude Code. The fallback captures the writer's changes with any tool, but only Claude Code's history can be imported in the MVP.
- Hook details: whether slash commands and resumed sessions fire the prompt hook and keep the session id. Confirmed against Claude Code's documentation and a real session when the copy-saving tests are written.

## Consequences

- The posts repo carries the hook settings, and keeps saved copies, session state and transcript copies in `.ledger/`, which is never published.
- A post written before the hooks were on has no writer steps.
- The site generator reads one trace per post and writes one page per version.

## Undo

Revert this file and the code that follows it; decision 0002's "What the reader sees" and decision 0001's trace format stand again.
