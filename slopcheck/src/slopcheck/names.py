"""Decide which capitalised words are names.

A capital at the start of a sentence is not enough. The word counts as a name
when the same spelling also appears capitalised later in a sentence, or when
it is on the known-names list. Acronyms in all capitals are left alone: the
jargon file already matches those by case.
"""

from __future__ import annotations

import re

from slopcheck.load import packaged_text
from slopcheck.tokens import is_stopword, norm_token

_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
# A quoted sentence starts at an opening quote. That word is sentence-initial.
_QUOTE_OPEN = re.compile(r"""(?:^|[\s(\[])[“"‘]\s*$""")
_SENT_END = re.compile(r"""[.!?…]["”’']*\s+$""")


def is_title_case(word: str) -> bool:
    """True for "Foster", false for "foster", "FOSTER", and "RAG"."""
    letters = [char for char in word if char.isalpha()]
    if len(letters) < 2:
        return False
    if not letters[0].isupper():
        return False
    return all(char.islower() for char in letters[1:])


def load_known_names() -> set[str]:
    """Lowercased names shipped in data/names.txt. Blank lines and # comments drop out."""
    names: set[str] = set()
    for line in packaged_text("names.txt").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(norm_token(line))
    return names


def _sentence_initial(text: str, word_start: int) -> bool:
    prefix = text[:word_start]
    if not prefix.strip():
        return True
    if _SENT_END.search(prefix):
        return True
    if _QUOTE_OPEN.search(prefix):
        return True
    return False


def names_in_sentence(sentence: str) -> set[str]:
    """Title-case words that are not the first word of a sentence or a quote."""
    found: set[str] = set()
    for match in _WORD.finditer(sentence):
        word = match.group(0)
        if not is_title_case(word) or is_stopword(word):
            continue
        if _sentence_initial(sentence, match.start()):
            continue
        found.add(norm_token(word))
    return found


def confirmed_names(sentences: list[str], known: set[str] | None = None) -> set[str]:
    """Names for one document: the known list, plus mid-sentence capitals."""
    names = {norm_token(name) for name in (known or set())}
    for sentence in sentences:
        names.update(names_in_sentence(sentence))
    return names


def match_is_confirmed_name(matched: str, names: set[str]) -> bool:
    """True when every word in the match is a confirmed name and one is title case.

    A lowercase "foster" still matches the verb. "Foster" does not, once the
    document has shown that Foster is a name.
    """
    tokens = _WORD.findall(matched)
    if not tokens or not names:
        return False
    if not any(is_title_case(token) for token in tokens):
        return False
    return all(norm_token(token) in names for token in tokens)


def first_word_span(text: str) -> tuple[int, int] | None:
    match = re.match(r"""[\"“‘'(\[\*_ ]*([A-Za-z][A-Za-z'’-]*)""", text)
    if not match:
        return None
    return match.span(1)


def is_unconfirmed_sentence_start(text: str, start: int, matched: str, names: set[str]) -> bool:
    """True when `matched` is a title-case word only because the sentence starts."""
    span = first_word_span(text)
    if span is None or start != span[0]:
        return False
    token_match = _WORD.match(matched.strip())
    if not token_match:
        return False
    token = token_match.group(0)
    if not is_title_case(token):
        return False
    return norm_token(token) not in names
