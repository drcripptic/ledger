"""Issue #8: a `private:` mark that can't be honoured is refused, never ignored.

import_claude_code reads post.md's front matter line `private: [x4, x5]` and withholds those
exchanges (slice 3). Each case below raises ValueError before anything is written: a missing
trace.jsonl isn't created, and an existing one is left byte for byte as it was. publish
turns the ValueError into Refused, so nothing is built.

- Unknown ids: ids in the list that aren't one of the post's exchanges x1 ... xN. The message
  is `private names x22, x9, which isn't in this post (x1 to x3)`: the unknown ids sorted as
  strings and joined with ", ", then the post's first and last ids.
- A form that isn't read: a line starting `private:` (in any case) that isn't `private: [...]`
  on one line, with each id written x<digits> and separated by commas. The message is
  `post.md's private line can't be read: write it as private: [x4, x5]`. `private: []` is
  read, and names none. This is checked from the top of post.md to its front matter's closing
  `---`, or through the whole file when there's no closed front matter. Past the front matter,
  only a line starting `private: [` is refused when it can't be read; any other is the post's
  own text.
- A readable list counts wherever it is in post.md, as before, and when there are several
  their ids are put together.
- Already written: an id in the list that trace.jsonl holds as an exchange record after its
  last `published` record (anywhere in it, when there is none). The message is
  `private names x2, already written to <path>: delete that file, then import again`, or, when
  the trace has a `published` record, `... <path>: delete its lines after the last published
  record, then import again`; the trace's path, and the ids sorted as strings and joined with
  ", ". An id the trace holds in a withheld record is fine, and so is an exchange record before
  the last `published` record: it's public already, and a trace only grows.
"""

import pytest

from ledger.importer import import_claude_code
from ledger.publish import Refused, publish
from test_import import prompts, trace, transcript, turn


def post(root, front, body="Text."):
    (root / "a-post").mkdir(exist_ok=True)
    (root / "a-post" / "post.md").write_text(f"---\ntitle: A post\n{front}---\n\n{body}\n")


@pytest.fixture
def t(tmp_path):
    return transcript(tmp_path / "s1.jsonl", turn("ledger start a-post", 1),
                      turn("One.", 2), turn("Secret plan.", 3), turn("Two.", 4))


def path(root):
    return root / "a-post" / "trace.jsonl"


def test_an_unknown_id_is_refused_and_nothing_is_written(tmp_path, t):
    post(tmp_path, "private: [x22]\n")
    with pytest.raises(ValueError) as e:
        import_claude_code("a-post", [t], tmp_path)
    assert str(e.value) == "private names x22, which isn't in this post (x1 to x3)"
    assert not path(tmp_path).exists()


def test_unknown_ids_are_sorted_and_known_ones_left_out(tmp_path, t):
    post(tmp_path, "private: [x9, x2, x22]\n")
    with pytest.raises(ValueError) as e:
        import_claude_code("a-post", [t], tmp_path)
    assert str(e.value) == "private names x22, x9, which isn't in this post (x1 to x3)"


@pytest.mark.parametrize("front", [
    "private:\n  - x2\n", "private: x2\n", 'private: ["x2"]\n', "private:\n", "private: [x2\n",
    "private:\n  [x2]\n", "private: [X2]\n", "private: [x2] and x3\n", "private: [x1 x2]\n"])
def test_a_private_line_it_cannot_read_is_refused(tmp_path, t, front):
    post(tmp_path, front)
    with pytest.raises(ValueError) as e:
        import_claude_code("a-post", [t], tmp_path)
    assert str(e.value) == "post.md's private line can't be read: write it as private: [x4, x5]"
    assert not path(tmp_path).exists()


def test_an_empty_list_withholds_nothing(tmp_path, t):
    post(tmp_path, "private: []\n")
    assert import_claude_code("a-post", [t], tmp_path) == 3
    assert prompts(trace(tmp_path)) == ["One.", "Secret plan.", "Two."]


def test_an_unreadable_list_in_the_body_is_refused(tmp_path, t):
    post(tmp_path, "", "private: [x2] # kept back")
    with pytest.raises(ValueError, match="can't be read"):
        import_claude_code("a-post", [t], tmp_path)


def test_prose_in_the_body_starting_private_is_text(tmp_path, t):
    post(tmp_path, "", "private: x2 is the one I kept back.")
    assert import_claude_code("a-post", [t], tmp_path) == 3
    assert prompts(trace(tmp_path)) == ["One.", "Secret plan.", "Two."]


@pytest.mark.parametrize("text", [
    "---\ntitle: A post\n---\n\nText.\n\nprivate: [x2]\n",
    "---\ntitle: A post\nprivate: [x2]\n\nText.\n",
    "private: [x2]\n\nText.\n",
    "---\nPrivate: [x2]\n---\n\nText.\n",
    "---\nprivate: [x2]\nprivate: []\n---\n\nText.\n",
    "---\nprivate: []\nprivate: [x2]\n---\n\nText.\n",
])
def test_a_readable_list_counts_wherever_it_is(tmp_path, t, text):
    (tmp_path / "a-post").mkdir()
    (tmp_path / "a-post" / "post.md").write_text(text)
    import_claude_code("a-post", [t], tmp_path)
    assert prompts(trace(tmp_path)) == ["One.", "Two."]


@pytest.mark.parametrize("text", [
    "---\ntitle: A post\nprivate: x2\n\nText.\n", "private: x2\n\nText.\n", "---\nPrivate: x2\n---\n\nText.\n"])
def test_an_unreadable_line_is_refused_without_closed_front_matter(tmp_path, t, text):
    (tmp_path / "a-post").mkdir()
    (tmp_path / "a-post" / "post.md").write_text(text)
    with pytest.raises(ValueError, match="can't be read"):
        import_claude_code("a-post", [t], tmp_path)


def test_an_exchange_already_in_the_trace_is_refused(tmp_path, t):
    post(tmp_path, "")
    import_claude_code("a-post", [t], tmp_path)
    before = path(tmp_path).read_bytes()
    post(tmp_path, "private: [x2]\n")
    with pytest.raises(ValueError) as e:
        import_claude_code("a-post", [t], tmp_path)
    assert str(e.value) == f"private names x2, already written to {path(tmp_path)}: delete that file, then import again"
    assert path(tmp_path).read_bytes() == before


def test_deleting_the_trace_and_importing_again_withholds_it(tmp_path, t):
    post(tmp_path, "")
    import_claude_code("a-post", [t], tmp_path)
    post(tmp_path, "private: [x2]\n")
    path(tmp_path).unlink()
    import_claude_code("a-post", [t], tmp_path)
    assert "Secret plan" not in path(tmp_path).read_text()


def test_an_id_already_withheld_is_fine(tmp_path, t):
    post(tmp_path, "private: [x2]\n")
    import_claude_code("a-post", [t], tmp_path)
    assert import_claude_code("a-post", [t], tmp_path) == 0


def test_a_published_trace_is_not_refused(tmp_path, t):
    post(tmp_path, "")
    publish("a-post", tmp_path, [t])
    post(tmp_path, "private: [x2]\n")
    assert import_claude_code("a-post", [t], tmp_path) == 0


def test_a_revisions_exchange_already_in_the_trace_is_refused(tmp_path, t):
    post(tmp_path, "")
    publish("a-post", tmp_path, [t])
    v1 = path(tmp_path).read_bytes()
    r = transcript(tmp_path / "s2.jsonl", turn("ledger start a-post", 11), turn("Secret revision.", 12), turn("More.", 13))
    import_claude_code("a-post", [t, r], tmp_path)
    post(tmp_path, "private: [x4]\n")
    with pytest.raises(ValueError) as e:
        import_claude_code("a-post", [t, r], tmp_path)
    assert str(e.value) == (f"private names x4, already written to {path(tmp_path)}: "
                            "delete its lines after the last published record, then import again")
    path(tmp_path).write_bytes(v1)
    import_claude_code("a-post", [t, r], tmp_path)
    assert "Secret revision" not in path(tmp_path).read_text()


@pytest.mark.parametrize("front", ["private: [x22]\n", "private: x2\n"])
def test_publish_refuses_and_builds_nothing(tmp_path, t, front):
    post(tmp_path, front)
    with pytest.raises(Refused, match="private"):
        publish("a-post", tmp_path, [t])
    assert not (tmp_path / "docs").exists()


def test_windows_line_endings_are_read(tmp_path, t):
    (tmp_path / "a-post").mkdir()
    (tmp_path / "a-post" / "post.md").write_bytes(b"---\r\ntitle: A post\r\nprivate: [x2]\r\n---\r\n\r\nText.\r\n")
    import_claude_code("a-post", [t], tmp_path)
    assert prompts(trace(tmp_path)) == ["One.", "Two."]
