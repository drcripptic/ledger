"""Slice 5 (issue #17): steps from the trace.

site.steps(records) takes a trace's records (the header line already left out) and returns the
replay's steps, in order. Each is a Step(kind, id, label, exchange, runs):

- kind: "exchange", "writer", "mixed", "withheld" or "published".
- id: the exchange's id ("x3"); "edit-1", "edit-2", ... for writer and mixed steps (one count for
  both); "withheld-1", ... for withheld steps; "v1", "v2", ... for published steps (the record's
  version).
- label: the exchange's id; "✎" for writer and mixed steps; "<count> withheld"; "Published v<version>".
- exchange: the exchange record for an exchange step, else None.
- runs: the post as it stood after the step, as a list of site.Run (slice 4).

The post starts empty ([]). Going through the records in order:

- exchange: a new exchange step. Its runs are the post settled (below).
- snapshot with by "ai": the post becomes site.diff(post, text, "ai"), and the latest exchange
  step's runs become that (the AI's change shows on its own exchange's step).
- snapshot with by "writer": a new writer step; the post becomes site.diff(post, text, "writer"),
  and the step's runs are that.
- snapshot with by "mixed": a new mixed step; the post becomes site.diff(post, text, "writer"),
  then each added run is split at the snapshot's "ai" ranges ([start, end) character offsets
  into text, the new post text): added text inside a range has by "ai", outside "writer".
  Offsets count the text of runs that aren't "removed". Neighbouring runs with the same by and
  state are joined. A mixed snapshot with no "ai" key has no ranges.
- withheld: a new withheld step, with the post settled. Until the next exchange or published
  record, every snapshot changes the post as above but makes no step of its own, and the
  withheld step's runs become the post settled: it shows the post as it stood, never a draft.
- published: a new published step, with the post settled.

Settled: removed runs dropped, every run's state "kept", neighbouring runs with the same by joined.
"""

from ledger.site import Run, Step, steps


def x(id, prompt="P"):
    return {"type": "exchange", "id": id, "at": "2026-11-11T09:00:00Z", "source": "claude-code",
            "model": "claude-opus-5-5", "prompt": prompt, "reply": "R", "tools": []}


def snap(by, after, text, ai=None):
    r = {"type": "snapshot", "by": by, "after": after, "text": text}
    if ai is not None:
        r["ai"] = ai
    return r


def withheld(*ids):
    return {"type": "withheld", "at": "2026-11-11T09:05:00Z", "count": len(ids), "ids": list(ids)}


def published(v):
    return {"type": "published", "version": v, "at": "2026-11-11T10:00:00Z"}


def test_exchanges_only():
    a, b = x("x1"), x("x2")
    assert steps([a, b]) == [
        Step("exchange", "x1", "x1", a, []),
        Step("exchange", "x2", "x2", b, []),
    ]


def test_ai_snapshot_marks_its_own_exchange():
    a, b = x("x1"), x("x2")
    s = steps([a, snap("ai", "x1", "Hello world."), b, snap("ai", "x2", "Hello big world.")])
    assert [st.id for st in s] == ["x1", "x2"]
    assert s[0].runs == [Run("Hello world.", "ai", "added")]
    assert s[1].runs == [Run("Hello ", "ai", "kept"), Run("big ", "ai", "added"), Run("world.", "ai", "kept")]


def test_exchange_with_no_change_shows_the_post_settled():
    a, b = x("x1"), x("x2")
    s = steps([a, snap("ai", "x1", "Hello world."), b])
    assert s[1].runs == [Run("Hello world.", "ai", "kept")]


def test_writer_copy_is_its_own_step():
    a, b = x("x1"), x("x2")
    s = steps([a, snap("ai", "x1", "Hello world."), snap("writer", "x1", "Hello there world."), b])
    assert [(st.kind, st.id, st.label) for st in s] == [
        ("exchange", "x1", "x1"), ("writer", "edit-1", "✎"), ("exchange", "x2", "x2")]
    assert s[1].exchange is None
    assert s[1].runs == [Run("Hello ", "ai", "kept"), Run("there ", "writer", "added"), Run("world.", "ai", "kept")]
    assert s[2].runs == [Run("Hello ", "ai", "kept"), Run("there ", "writer", "kept"), Run("world.", "ai", "kept")]


def test_writer_removal_is_struck_on_its_step_then_gone():
    s = steps([x("x1"), snap("ai", "x1", "One two three."), snap("writer", "x1", "One three."), x("x2")])
    assert s[1].runs == [Run("One ", "ai", "kept"), Run("two ", "ai", "removed"), Run("three.", "ai", "kept")]
    assert s[2].runs == [Run("One three.", "ai", "kept")]


def test_mixed_copy_split_by_ranges():
    before = "Start."
    after = "Start. AI said this. I typed that."
    i = after.index("AI said this. ")
    s = steps([x("x1"), snap("ai", "x1", before),
               snap("mixed", "x1", after, ai=[[i, i + len("AI said this. ")]])])
    assert [(st.kind, st.id, st.label) for st in s] == [("exchange", "x1", "x1"), ("mixed", "edit-1", "✎")]
    assert s[1].runs == [
        Run("Start. ", "ai", "kept"),
        Run("AI said this. ", "ai", "added"),
        Run("I typed that.", "writer", "added"),
    ]


def test_mixed_copy_without_ranges_is_the_writers():
    s = steps([x("x1"), snap("mixed", "x1", "Typed.")])
    assert s[1].runs == [Run("Typed.", "writer", "added")]


def test_edit_ids_count_writer_and_mixed_together():
    s = steps([x("x1"), snap("writer", "x1", "A."), snap("mixed", "x1", "A. B."), x("x2"), snap("writer", "x2", "A. B. C.")])
    assert [st.id for st in s] == ["x1", "edit-1", "edit-2", "x2", "edit-3"]


def test_withheld_stretch_folds_in_its_copies_and_the_writer_copy_after_it():
    s = steps([
        x("x1"), snap("ai", "x1", "Shown."),
        withheld("x2", "x3"),
        snap("ai", "x2", "Shown. Draft secret."),
        snap("ai", "x3", "Shown. Final words."),
        snap("writer", "x3", "Shown. Final words, edited."),
        x("x4"),
    ])
    assert [(st.kind, st.id, st.label) for st in s] == [
        ("exchange", "x1", "x1"), ("withheld", "withheld-1", "2 withheld"), ("exchange", "x4", "x4")]
    w = s[1]
    assert w.exchange is None
    assert all(r.state == "kept" for r in w.runs)
    assert "".join(r.text for r in w.runs) == "Shown. Final words, edited."
    assert "secret" not in "".join(r.text for st in s for r in st.runs)
    assert w.runs == [Run("Shown. Final ", "ai", "kept"), Run("words, edited.", "writer", "kept")]


def test_one_published():
    s = steps([x("x1"), snap("ai", "x1", "Done."), published(1)])
    assert s[-1] == Step("published", "v1", "Published v1", None, [Run("Done.", "ai", "kept")])


def test_two_published_with_a_revision_between():
    s = steps([
        x("x1"), snap("ai", "x1", "Done."), published(1),
        x("x2"), snap("ai", "x2", "Done. More."), published(2),
    ])
    assert [st.id for st in s] == ["x1", "v1", "x2", "v2"]
    assert s[2].runs == [Run("Done. ", "ai", "kept"), Run("More.", "ai", "added")]
    assert s[3].runs == [Run("Done. More.", "ai", "kept")]


def test_published_ends_a_withheld_fold():
    s = steps([x("x1"), withheld("x2"), snap("ai", "x2", "Hidden draft."), published(1), snap("writer", "x2", "Final.")])
    assert [st.kind for st in s] == ["exchange", "withheld", "published", "writer"]
    assert s[3].runs == [Run("Hidden draft.", "ai", "removed"), Run("Final.", "writer", "added")]


def test_mixed_keeps_added_text_before_a_later_range():
    after = "New. Keep. AI part here."
    i = after.index("AI")
    s = steps([x("x1"), snap("ai", "x1", "Keep."), snap("mixed", "x1", after, ai=[[i, len(after)]])])
    assert s[1].runs == [Run("New. ", "writer", "added"), Run("Keep. ", "ai", "kept"), Run("AI part here.", "ai", "added")]


def test_two_withheld_records_are_two_steps():
    s = steps([x("x1"), withheld("x2"), snap("writer", "x2", "A."), withheld("x3", "x4"), snap("ai", "x4", "A. B."), x("x5")])
    assert [(st.kind, st.id, st.label) for st in s] == [
        ("exchange", "x1", "x1"), ("withheld", "withheld-1", "1 withheld"), ("withheld", "withheld-2", "2 withheld"), ("exchange", "x5", "x5")]
    assert s[1].runs == [Run("A.", "writer", "kept")]
    assert s[2].runs == [Run("A. ", "writer", "kept"), Run("B.", "ai", "kept")]
