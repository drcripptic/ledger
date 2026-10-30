# 0001: The trace format

Status: proposed, 30 Oct 2026.

## Context

ledger shows readers how a post was written: every prompt and reply behind it, which model replied, what the writer changed, and which paragraph each exchange shaped. Writing happens elsewhere, with any AI model, so ledger needs one format that every importer writes and the site generator reads. This file defines it.

## Decision

### A post is a folder

```
<slug>/
  post.md           the published text, with front matter
  trace.jsonl       the history, one record per line, in order
  attribution.json  each paragraph's origin and the exchanges behind it
```

The folder lives in the writer's posts repo, never in this one.

### `post.md`

Markdown with YAML front matter:

```yaml
---
title: The case for slower software
author: "[Writer name]"
published: 2026-10-30
private: [x4, x5]   # optional: exchanges withheld after the fact
---
```

A paragraph is a block of text separated by a blank line. Paragraphs are numbered from 1 in order.

### `trace.jsonl`

The first line is a header; every other line is one record, in time order. Times are UTC, RFC 3339.

```json
{"ledger_trace": 1, "post": "slower-software"}
{"type": "exchange", "id": "x1", "at": "2026-10-30T09:02:11Z", "source": "claude-code", "model": "claude-opus-5-5", "prompt": "...", "reply": "...", "tools": []}
{"type": "exchange", "id": "x2", "at": "2026-10-30T09:09:40Z", "source": "chatgpt-export", "model": "gpt-5", "prompt": "...", "reply": "...", "tools": [{"name": "web_search", "summary": "Searched the web: GitHub Pages limits", "detail": "..."}]}
{"type": "withheld", "at": "2026-10-30T09:12:00Z", "count": 2}
{"type": "snapshot", "after": "x2", "text": "..."}
```

- **`exchange`:** one prompt from the writer and everything the AI did until it next waited for the writer: its reply text (joined, if it came in several messages) and its tool calls. `id`s are `x1`, `x2`, … in order, and never reused. `model` is the model's own identifier as the source reports it; `source` names the importer.
- **`tools`:** one entry per tool call. `summary` is one line a reader sees collapsed; `detail` opens beneath it, cut to 4,000 characters.
- **`withheld`:** stands where the writer marked exchanges private. It carries only their count and the time of the first. The exchanges themselves are never written to the trace.
- **`snapshot`:** the full post text at a point in the writing, for Replay. Optional: a source that can't show the post's state between exchanges writes none, and Replay shows only the exchanges.

### `attribution.json`

```json
{"paragraphs": [
  {"n": 1, "origin": "writer", "exchanges": []},
  {"n": 2, "origin": "edited", "exchanges": ["x1", "x2"], "draft": "..."},
  {"n": 3, "origin": "ai", "exchanges": ["x3"]}
]}
```

`origin` is `writer` (no AI text kept), `edited` (an AI draft the writer changed; `draft` holds the AI's version) or `ai` (AI text kept as written). How ledger works this out is its own decision, made when the attribution step is built.

### Marking a span and private exchanges

- **The span:** a post's history is the exchanges from a prompt starting `ledger start <slug>` to one starting `ledger end`. It may cross sessions and sources.
- **Private, in the moment:** a prompt starting `ledger private` withholds that exchange.
- **Private, afterwards:** the exchange ids in `post.md`'s `private` list.

Withheld exchanges are dropped when the trace is written, so they can't reach a published site.

## Consequences

- Every importer writes the same three files, so the site generator has one input.
- A trace can include text the writer didn't mean to publish: file contents in tool calls, for instance. Publishing therefore scans the trace for secrets and refuses on a match. That check comes with the publish step.
- `ledger_trace: 1` versions the format. A change that breaks readers bumps it.

## Undo

Supersede this file with a new decision. Nothing is built on it yet.
