"""Word tokens and function words shared by the prose checks.

A content word is a token that is not a function word. Repeated-phrase and
brief-leak checks count content words, so a run of "of the" does not register.
"""

from __future__ import annotations

import re

# Letters, digits, and internal apostrophes or hyphens. A straight or curly
# apostrophe stays inside the token so "don't" is one word.
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")

# Function words. Kept in the source so the check has no word-list dependency.
# The set is closed-class words, not a stoplist of ordinary nouns.
STOPWORDS = frozenset(
    """
    a an the of to and or in on for with from by at as is are was were be been
    being it this that these those i you he she we they them him me us my your
    his her its our their not no nor but if so than then too very just also
    into over after before about up down out off which who whom whose what
    when where why how there here can could should would will may might must
    shall do does did done doing have has had having am let's lets
    than onto upon within without across against between under above below
    again further once each few more most other some any both own same such
    because until while during per via than ever never always
    i'm you're we're they're that's it's i've you've we've they've i'll you'll
    he'll she'll we'll they'll i'd you'd he'd she'd we'd they'd don't doesn't
    didn't can't couldn't won't wouldn't shouldn't isn't aren't wasn't weren't
    haven't hasn't hadn't
    """.split()  # noqa: SIM905 -- a word block is easier to read and edit than a 169-item list
)


def norm_token(word: str) -> str:
    return word.casefold().replace("’", "'")


def is_stopword(word: str) -> bool:
    key = norm_token(word)
    if key in STOPWORDS:
        return True
    return key.endswith("'s") and key[:-2] in STOPWORDS


def is_content_word(word: str) -> bool:
    """A content word is not a function word. Digits count. One-letter words do not."""
    if word.isdigit():
        return True
    if is_stopword(word):
        return False
    letters = [char for char in word if char.isalpha()]
    return len(letters) >= 2


def tokenize(text: str) -> list[re.Match[str]]:
    return list(TOKEN_RE.finditer(text))


def content_words(text: str) -> list[str]:
    words: list[str] = []
    for match in TOKEN_RE.finditer(text):
        word = match.group(0)
        if is_content_word(word):
            words.append(norm_token(word))
    return words


def word_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))
