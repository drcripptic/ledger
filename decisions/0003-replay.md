# 0003: The post page is a replay, and the writer's changes are told apart from the AI's

Status: proposed, 11 Nov 2026. It replaces "What the reader sees" in decision 0002 and adds to the `snapshot` record in decision 0001.

## The problem

Decision 0002 said the reader sees the post with its full AI history beside it. The writer saw two mockups of that on 11 Nov: the post beside a list of exchanges, and exchanges under the paragraphs they shaped. Neither works. A reader wants to see how the post came to be: what it looked like at each stage of prompting, and which words the writer wrote and which the AI did.

## Agreed

### The page (the writer, 11 Nov 2026)

- **One step per stage.** A row of steps runs across the top: each exchange (`x1`, `x2`, …), each stretch of the writer's own editing between prompts (marked ✎), a step for withheld exchanges ("2 exchanges withheld by the writer"), and "Published" at the end. Previous and Next move through them.
- **At each step:** the exchange on the left (its prompt, its reply, and its tool calls as collapsed lines), and the post as it stood after that step on the right.
- **Changes are marked by who made them.** In the step's own change, the AI's added text is blue and the writer's is orange with an underline, so they differ by more than colour. Removed text is struck through. Earlier changes keep a faint tint of the same colour, so any stage shows who wrote each part.
- **No JavaScript needed.** Each step is a section of one static page, and Previous and Next are links to it.

### Capturing the writer's changes (the writer, 11 Nov 2026)

Claude Code's hooks save a copy of `post.md` when the writer sends a prompt and when the AI finishes replying. What changed between the AI finishing and the next prompt is the writer's; what changed between a prompt and the AI finishing is the AI's. The writer typing in `post.md` while the AI replies is the one case left: that step is marked mixed, never guessed.

### The trace

A `snapshot` record (decision 0001) gains `by`: `"ai"`, `"writer"` or `"mixed"`. One snapshot follows each exchange (`by: "ai"`), and one follows each stretch of the writer's own editing (`by: "writer"`).

## Open

- How a source without hooks (a chat export) tells the writer's changes apart. Until then, its steps show only the exchanges, as decision 0001 says.

## Consequences

- The posts repo carries the hook settings, written by ledger, and each post's folder keeps the saved copies until the importer reads them.
- A post written before the hooks were on has no writer steps.

## Undo

Revert this file and the code that follows it; decision 0002's "What the reader sees" stands again.
