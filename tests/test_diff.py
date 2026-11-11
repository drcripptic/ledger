"""Slice 4 (issue #16): diff by author.

site.diff(before, after_text, by) takes the post as a list of Run(text, by, state)
and the post's new text, and returns new runs.

- `by` is "ai", "writer" or "mixed"; `state` is "kept", "added" or "removed".
- Text is split into tokens with re.findall(r"^\\s+|\\S+\\s*", text): each word with
  the whitespace after it, so joining the tokens gives the text back exactly.
- Tokens are compared by their word alone (whitespace stripped) and aligned with
  difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes().
- Runs in `before` with state "removed" are dropped first: they never carry forward.
- The old tokens come from the kept runs' text joined together, so a run may end mid-word.
  Each old token's `by` is the `by` of the run holding its first character.
- equal: the new text's tokens, keeping the `by` of the matching old tokens, state "kept".
  delete: the old tokens, keeping their `by`, state "removed".
  insert: the new tokens, with the given `by`, state "added".
  replace: the removed old tokens, then the added new tokens.
- Neighbouring tokens with the same `by` and `state` are joined into one Run.
"""

from ledger.site import Run, diff


def test_run_is_a_value():
    assert Run("a ", "ai", "kept") == Run("a ", "ai", "kept")
    r = Run("a ", "ai", "kept")
    assert (r.text, r.by, r.state) == ("a ", "ai", "kept")


def test_from_empty():
    assert diff([], "Hello world.", "ai") == [Run("Hello world.", "ai", "added")]


def test_no_change_keeps_the_old_author():
    before = [Run("Hello world.", "ai", "kept")]
    assert diff(before, "Hello world.", "writer") == [Run("Hello world.", "ai", "kept")]


def test_added_word():
    before = [Run("Hello world.", "ai", "kept")]
    assert diff(before, "Hello big world.", "writer") == [
        Run("Hello ", "ai", "kept"),
        Run("big ", "writer", "added"),
        Run("world.", "ai", "kept"),
    ]


def test_removed_word_keeps_its_author():
    before = [Run("Hello big world.", "ai", "kept")]
    assert diff(before, "Hello world.", "writer") == [
        Run("Hello ", "ai", "kept"),
        Run("big ", "ai", "removed"),
        Run("world.", "ai", "kept"),
    ]


def test_replaced_word_is_removed_then_added():
    before = [Run("Hello big world.", "ai", "kept")]
    assert diff(before, "Hello small world.", "writer") == [
        Run("Hello ", "ai", "kept"),
        Run("big ", "ai", "removed"),
        Run("small ", "writer", "added"),
        Run("world.", "ai", "kept"),
    ]


def test_new_paragraph():
    before = [Run("One.", "ai", "kept")]
    assert diff(before, "One.\n\nTwo.", "writer") == [
        Run("One.\n\n", "ai", "kept"),
        Run("Two.", "writer", "added"),
    ]


def test_earlier_tags_kept_on_unchanged_words():
    before = [
        Run("Hello ", "ai", "kept"),
        Run("big ", "writer", "added"),
        Run("world.", "ai", "kept"),
    ]
    assert diff(before, "Hello big world. Bye.", "ai") == [
        Run("Hello ", "ai", "kept"),
        Run("big ", "writer", "kept"),
        Run("world. ", "ai", "kept"),
        Run("Bye.", "ai", "added"),
    ]


def test_removed_runs_not_carried_forward():
    before = [
        Run("Hello ", "ai", "kept"),
        Run("big ", "ai", "removed"),
        Run("world.", "ai", "kept"),
    ]
    assert diff(before, "Hello world.", "writer") == [Run("Hello world.", "ai", "kept")]


def test_mixed_is_an_author():
    before = [Run("Hello world.", "writer", "kept")]
    assert diff(before, "Hello there world.", "mixed") == [
        Run("Hello ", "writer", "kept"),
        Run("there ", "mixed", "added"),
        Run("world.", "writer", "kept"),
    ]


def test_leading_whitespace_is_a_token():
    assert diff([], "  Indented.", "writer") == [Run("  Indented.", "writer", "added")]


def test_whitespace_change_alone_is_kept_with_new_spacing():
    before = [Run("One two.", "ai", "kept")]
    assert diff(before, "One\ntwo.", "writer") == [Run("One\ntwo.", "ai", "kept")]


def test_new_text_is_rebuilt_exactly():
    before = [Run("The quick brown fox.\n\nIt ran.", "ai", "kept")]
    after = "The slow brown fox.\n\nIt ran away.\n\nThe end."
    runs = diff(before, after, "writer")
    assert "".join(r.text for r in runs if r.state != "removed") == after


def test_runs_ending_mid_word_take_the_author_of_the_first_character():
    before = [
        Run("a", "ai", "kept"),
        Run("b", "writer", "kept"),
        Run("c d", "ai", "kept"),
    ]
    assert diff(before, "abc d", "writer") == [Run("abc d", "ai", "kept")]
