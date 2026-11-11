"""site.diff: diff by author."""

from dataclasses import dataclass
import re
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
