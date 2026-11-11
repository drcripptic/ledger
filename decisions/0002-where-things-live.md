# 0002: The product's principle, and where the code, the posts and the published site live

Status: accepted, 11 Nov 2026. This file records decisions taken on the v0 plan (issue 2) between 30 Oct and 11 Nov 2026. Until now they lived only in that issue's text.

## Context

ledger's design was agreed in issue 2 and its comments: what the reader sees, and where it's hosted. Nothing at the start of a session reads that issue, so its decisions were lost from one session to the next. Twice, a plan put post text in the wrong repo. This file gives them one home. Any plan that touches where posts live, or how they're published, cites it.

## Decision

### The product's principle (the writer, 11 Nov 2026)

ledger is for writers who want to show their work. The writer is the core user, and readers are who they show it to.

- **Transparent by default.** The whole history is captured and published, and the writer never has to choose to show it. Withholding an exchange is still possible (a visible gap, as below), but it's an exception kept out of the main flow. A product that leads with hiding things trains writers into habits that work against their real goal.
- **Complete, faithful and easy to follow.** A reader can quickly see what actually happened: what the AI wrote, what the writer kept, and what they changed. It's shown as it was, never framed in the writer's favour. The writer gains from the honesty itself, not from how the page presents them.

### Two repos, for the MVP

Repos hold the data for the MVP (the writer, 11 Nov 2026). Once the writer's and the reader's experience is settled, a better long-term home, such as a hosted service, gets its own decision.

| Repo | Visibility | Holds | Never holds |
|---|---|---|---|
| **This repo** (ledger) | public | The machinery: the trace format, importers, attribution, the site generator, the publish step, and their tests | Any post's text, any trace, anything about the writer's private work |
| **The writer's posts repo** | private, with GitHub Pages serving only its `docs/` folder | Drafts and each post's folder (decision 0001). Under `docs/`, the published site: each published post's full trace (`post.md`, `trace.jsonl`, `attribution.json`) and the pages built from it | In `docs/`: drafts, unpublished posts, and exchanges the writer withheld |

- **Only `docs/` is public.** Pages serves the posts repo's `main` branch from `/docs`, never from the root, which would publish the whole repo.
- **Only the publish step writes to `docs/`,** and only on the writer's go-ahead for that post.
- **Why one repo, not a separate public one** (the writer, 11 Nov 2026, replacing the plan's separate Pages repo): it's simpler; the repo's history stays private, so a file published by mistake leaves the site once it's removed from `docs/`, where a public repo's history would keep it; and no new repo or access is needed. It needs Pages on a private repo, which this account has (checked in its Pages settings, 11 Nov 2026).

### Hosting: a static site on GitHub Pages (decided 30 Oct 2026)

- A published post and its history don't change, so ledger builds plain HTML, CSS and JS pages, and any interactivity runs in the browser. GitHub doesn't run a build step, and there's no server.
- Limits checked on 30 Oct 2026: a 1 GB site, and 100 GB a month of bandwidth (a soft limit).
- Substack was set aside on 30 Oct 2026 because it can't show the history inside a post (issue 2's comments).

### What the reader sees (decided 30 Oct 2026)

- The post, with its full AI history beside it, from any AI model.
- Exchanges the writer marked private show as a visible gap ("2 exchanges withheld by the writer"), never removed silently.
- Tool calls are shown as collapsed lines under each reply, which open to the details.

## Consequences

- The site generator writes its output into the posts repo's `docs/`. It never writes into this one.
- `docs/` holds a `.nojekyll` file, so Pages serves the files exactly as built and doesn't run Jekyll on them.
- The trace published in `docs/` has already had withheld exchanges dropped (decision 0001), so they can't be published.
- A change to any row of the table above is a new decision that supersedes this one.

## Undo

Supersede this file with a new decision. Nothing is built on it yet.
