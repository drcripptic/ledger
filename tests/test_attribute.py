"""Slice 14 (issue #26): match against what the AI wrote.

site.attribute(before_text, after_text, corpus) returns the character ranges ([start, end) offsets
into after_text, as a list of [start, end] lists, sorted, neighbours merged) of the added text
that repeats at least 6 words in a row of corpus, ignoring case, spacing and punctuation.

- Tokens are site.diff's (re.findall(r"^\\s+|\\S+\\s*", text)). The added tokens are those
  site.diff([Run(before_text, "ai", "kept")], after_text, "x") marks "added"; a token's span is
  where it sits in after_text.
- A token's words are re.findall(r"\\w+", token.lower()). Corpus words likewise, from corpus.
- A stretch is a run of added tokens next to each other in after_text. Within a stretch, every
  6 words in a row (across its tokens) that also appear 6 in a row in the corpus mark the tokens
  from the one holding the first of the 6 words to the one holding the last (so a token with no
  words between them, like "-- ", is marked too).
- A range is the span of marked tokens next to each other (whole tokens, with their whitespace).
"""

from ledger.site import attribute

CORPUS = "Here is a draft: The quick brown fox jumps over the lazy dog, again and again."


def test_nothing_added():
    assert attribute("Same text.", "Same text.", CORPUS) == []


def test_a_copied_sentence_is_the_ais():
    after = "Mine. The quick brown fox jumps over the lazy dog."
    i = after.index("The")
    assert attribute("Mine.", after, CORPUS) == [[i, len(after)]]


def test_case_spacing_and_punctuation_are_ignored():
    after = "Mine. the QUICK, brown   fox -- jumps over"
    i = after.index("the")
    assert attribute("Mine.", after, CORPUS) == [[i, len(after)]]


def test_five_words_are_not_enough():
    assert attribute("Mine.", "Mine. The quick brown fox jumps.", CORPUS) == []


def test_only_the_matching_part_of_a_stretch():
    after = "I wrote this myself then the quick brown fox jumps over"
    i = after.index("the quick")
    assert attribute("", after, CORPUS) == [[i, len(after)]]


def test_kept_text_is_never_marked():
    before = "The quick brown fox jumps over the lazy dog."
    assert attribute(before, before + " Mine.", CORPUS) == []


def test_matching_does_not_cross_kept_text():
    before = "The quick brown keep fox jumps over"
    after = "The quick brown NEW keep fox jumps over"
    assert attribute(before, after, CORPUS) == []


def test_two_ranges():
    after = "The quick brown fox jumps over. Mine here. the lazy dog, again and again."
    a = after.index(" Mine")
    b = after.index("the lazy")
    assert attribute("", after, CORPUS) == [[0, a + 1], [b, len(after)]]


REPLY = "Rivers carve their valleys over many thousands of years, slowly and without any plan at all."
FILE_EDIT = '{"file_path": "/x/post.md", "content": "Cities grow along the rivers that first gave them water and trade."}'


def test_a_lightly_edited_reply():
    after = "Rivers carve their valleys over many THOUSANDS of years, quickly and without any plan at all."
    a = after.index("quickly")
    b = after.index("and without")
    assert attribute("", after, REPLY) == [[0, a], [b, len(after)]]


def test_text_from_a_file_edit():
    after = "Intro. Cities grow along the rivers that first gave them water and trade."
    i = after.index("Cities")
    assert attribute("Intro.", after, REPLY + "\n\n" + FILE_EDIT) == [[i, len(after)]]


def test_the_writers_own_text():
    assert attribute("", "I walked down to the river this morning and thought about it.", REPLY + "\n\n" + FILE_EDIT) == []


def test_text_only_in_a_later_corpus_is_not_matched():
    after = "Cities grow along the rivers that first gave them water and trade."
    assert attribute("", after, REPLY) == []
