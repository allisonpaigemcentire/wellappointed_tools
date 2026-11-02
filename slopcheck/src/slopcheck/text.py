"""Turn a Markdown file into lines and sentences the checker can point at.

Columns are 1-based character offsets on the line, not bytes. Fenced code,
inline code, URLs, HTML comments, editor-note spans, and double quotes are
blanked before a match, and the blanking keeps the original length so the
column stays put. The URL of a Markdown link or image is blanked too. The
link text stays.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from slopcheck.load import ConfigError

QUOTE_RE = re.compile(r'"[^"\n]*"|“[^”\n]*”')
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
CODE_RE = re.compile(r"`[^`\n]{1,400}`")
URL_RE = re.compile(r"https?://\S+")
FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^#{1,6}\s")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TABLE_RE = re.compile(r"^\s*\|")
HR_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
# A YAML mapping key at the start of a front-matter line: `slug: x` or `"key": x`.
FRONT_KEY_RE = re.compile(r"""^(?:[A-Za-z0-9_][\w .-]*|"[^"]*"|'[^']*')\s*:(?:\s|$)""")
TITLE_RE = re.compile(
    r"^(\s*)(title|subtitle|excerpt|description|summary|preheader|subject)\s*:\s*(.*)$",
    re.I,
)
OPT_RE = re.compile(r"<!--\s*slop(?:check)?-ok:\s*([^>]*?)\s*-->", re.I)
OFF_LINE = re.compile(r"^<!--\s*slopcheck-off\s*-->$", re.I)
ON_LINE = re.compile(r"^<!--\s*slopcheck-on\s*-->$", re.I)
# Opening "[" or "![", the link text, then "](url)". The text is kept.
LINK_RE = re.compile(r"(!?\[)([^\]]*)(\]\((?:[^()\n]|\([^()\n]*\))*\))")
HEADING_PARTS = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# A bracketed editor note: [NAME: ...] with an all-caps label.
DEFAULT_EDITOR_NOTE = re.compile(r"\[[A-Z][A-Z0-9]*(?:[ /-][A-Z0-9]+)*:[^\]]*\]")
DEFAULT_SKIP_HEADINGS = (
    "Claim trace",
    "Claim-trace",
    "Sources (not for publication)",
    "Editor notes",
    "Not for publication",
)
_OPT_NOTES = (
    re.compile(r"\s*\([^)]*\)\s*$"),
    re.compile(r"\s+-\s+.*$", re.S),
    re.compile(r"\s+[—–]\s*.*$", re.S),
)
ABBR = (
    "e.g.", "i.e.", "vs.", "etc.", "Mr.", "Ms.", "Mrs.", "Dr.", "St.",
    "U.S.", "U.K.", "No.", "approx.", "cf.", "al.",
)
SENT_SPLIT = re.compile(r'(?<=[.!?])["”’)\]*_]*\s+(?=["“‘(\[*_`]*[A-Z0-9])')

# Reader-facing title fields. A slug, a date, or a path is not one of these.
TITLE_KEYS = {"title", "subtitle", "excerpt", "description", "summary", "preheader", "subject"}


@dataclass
class ScanConfig:
    """What to leave out of a check, besides code and quotes.

    `editor_notes` are regular expressions for spans on a line. `skip_headings`
    are phrases. A heading is skipped when its text contains one of them,
    ignoring case and treating hyphens like spaces. An empty list turns that
    skip off. HTML comments are always skipped.
    """

    editor_notes: list[re.Pattern] = field(default_factory=lambda: [DEFAULT_EDITOR_NOTE])
    skip_headings: list[str] = field(default_factory=lambda: list(DEFAULT_SKIP_HEADINGS))


def default_scan_config() -> ScanConfig:
    return ScanConfig()


def compile_editor_notes(patterns: object, where: str = "editor_notes") -> list[re.Pattern]:
    if not isinstance(patterns, list):
        raise ConfigError(f"{where} must be a list of regular expressions")
    compiled: list[re.Pattern] = []
    for index, item in enumerate(patterns, 1):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{where}: item {index} must be a regular expression")
        try:
            compiled.append(re.compile(item))
        except re.error as exc:
            raise ConfigError(f"{where}: item {index} is not a valid regular expression: {exc}") from exc
    return compiled


def compile_skip_headings(items: object, where: str = "skip_headings") -> list[str]:
    if not isinstance(items, list):
        raise ConfigError(f"{where} must be a list of phrases")
    phrases: list[str] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{where}: item {index} must be a phrase")
        phrases.append(item.strip())
    return phrases


def scan_config_from(config: dict) -> ScanConfig:
    """Build a scan config. Missing keys keep the defaults. Present keys replace them."""
    notes = (
        compile_editor_notes(config["editor_notes"])
        if "editor_notes" in config
        else [DEFAULT_EDITOR_NOTE]
    )
    headings = (
        compile_skip_headings(config["skip_headings"])
        if "skip_headings" in config
        else list(DEFAULT_SKIP_HEADINGS)
    )
    return ScanConfig(editor_notes=notes, skip_headings=headings)


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _link_mask_spans(text: str) -> list[tuple[int, int]]:
    """Blank the brackets and the URL. Leave the link or alt text in place."""
    spans: list[tuple[int, int]] = []
    for match in LINK_RE.finditer(text):
        spans.append(match.span(1))
        spans.append(match.span(3))
    return spans


def mask_text(text: str, scan: ScanConfig | None = None, *, quotes: bool = True) -> str:
    """Replace skipped spans with spaces of the same length."""
    scan = scan or default_scan_config()
    chars = list(text)
    spans: list[tuple[int, int]] = []
    spans.extend(match.span() for match in COMMENT_RE.finditer(text))
    if quotes:
        spans.extend(match.span() for match in QUOTE_RE.finditer(text))
    spans.extend(match.span() for match in CODE_RE.finditer(text))
    spans.extend(match.span() for match in URL_RE.finditer(text))
    spans.extend(_link_mask_spans(text))
    for pattern in scan.editor_notes:
        spans.extend(match.span() for match in pattern.finditer(text))
    for start, end in spans:
        for index in range(start, min(end, len(chars))):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def _strip_opt_note(payload: str) -> str:
    """Drop a trailing note: `(...)`, ` - ...`, or a spaced em dash / en dash."""
    text = payload.strip()
    while text:
        updated = text
        for pattern in _OPT_NOTES:
            match = pattern.search(text)
            if match and match.start() > 0:
                text = text[:match.start()].rstrip()
                break
        if text == updated:
            return text
    return text


def opt_keys(line: str) -> set[str]:
    keys: set[str] = set()
    for match in OPT_RE.finditer(line):
        payload = _strip_opt_note(match.group(1))
        for part in payload.split(","):
            token = part.strip().lower()
            if token:
                keys.add(token)
    return keys


def _heading_key(text: str) -> str:
    text = text.casefold().replace("—", " ").replace("–", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def heading_matches(title: str, phrases: list[str]) -> bool:
    haystack = _heading_key(title)
    if not haystack:
        return False
    for phrase in phrases:
        needle = _heading_key(phrase)
        if needle and needle in haystack:
            return True
    return False


def suppressed(keys: set[str], *, rule_id: str, category: str, bucket: str | None) -> bool:
    if not keys:
        return False
    if "*" in keys or "all" in keys:
        return True
    if rule_id.lower() in keys or category.lower() in keys:
        return True
    if bucket and (bucket.lower() in keys or "jargon" in keys):
        return True
    return False


@dataclass
class LineInfo:
    number: int
    text: str
    kind: str  # front, title, body, code
    title_value: str | None = None
    title_column: int | None = None
    keys: set[str] = field(default_factory=set)


@dataclass
class Sentence:
    """A jargon unit. `text` still has quotes; `masked` blanks them."""

    kind: str  # front or body
    line: int
    text: str
    masked: str
    origins: list[tuple[int, int]]


def title_span(line: str) -> tuple[str, int] | None:
    """Return (unwrapped value, 1-based column) for a title-like front-matter line."""
    match = TITLE_RE.match(line)
    if not match or match.group(2).lower() not in TITLE_KEYS:
        return None
    raw = match.group(3)
    lead = len(raw) - len(raw.lstrip())
    value = raw.lstrip().rstrip()
    column = match.start(3) + lead + 1
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
        column += 1
    return value, column


def _blank(line: str, start: int, end: int) -> str:
    """Replace line[start:end] with spaces, keeping the column of everything after it."""
    return line[:start] + " " * (end - start) + line[end:]


def _closes_ahead(lines: list[str]) -> list[bool]:
    """For each index i, whether `-->` comes in lines[i:] before a blank line ends the paragraph.

    Built once, back to front, so a page full of stray openers stays linear.
    """
    ahead = [False] * (len(lines) + 1)
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if not line.strip():
            ahead[index] = False
        elif "-->" in line:
            ahead[index] = True
        else:
            ahead[index] = ahead[index + 1]
    return ahead


def mask_comment_lines(
    line: str,
    in_comment: bool,
    closes_later: bool = False,
) -> tuple[str, bool]:
    """Blank the parts of `line` inside an HTML comment that spans lines.

    Returns the line with those parts replaced by spaces of the same length,
    and whether a comment is still open at the end of the line. A comment
    that opens and closes on one line is left for `mask_text`.

    `closes_later` says whether a `-->` comes on a later line of the same
    paragraph. As in CommonMark, a `<!--` at the start of a line opens a comment block
    that runs to `-->` or the end of the file. A `<!--` later in a line is a comment only when `-->` follows
    before the paragraph ends. Otherwise it is literal text, so a stray
    `<!--` in prose does not hide the rest of the page.
    """
    cursor = 0
    if in_comment:
        close = line.find("-->")
        if close < 0:
            return " " * len(line), True
        line = _blank(line, 0, close + 3)
        cursor = close + 3
    code = [match.span() for match in CODE_RE.finditer(line)]
    while True:
        start = line.find("<!--", cursor)
        if start < 0:
            return line, False
        if any(low <= start < high for low, high in code):
            cursor = start + 4
            continue
        close = line.find("-->", start + 4)
        if close >= 0:
            cursor = close + 3
            continue
        lead = line[:start]
        block = not lead.strip() and len(lead) <= 3
        if block or closes_later:
            return _blank(line, start, len(line)), True
        cursor = start + 4


def _looks_like_front_matter(body: list[str]) -> bool:
    """True when every line between the `---` fences could be YAML.

    A page that opens with a thematic break (`---`) and a paragraph is not
    front matter, and its prose must still be checked.
    """
    for line in body:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[:1] in (" ", "\t"):
            continue
        if stripped.startswith("- ") or stripped == "-":
            continue
        if FRONT_KEY_RE.match(line):
            continue
        return False
    return True


def classify_lines(text: str, scan: ScanConfig | None = None) -> list[LineInfo]:
    """Label each line as front, title, body, code, or skip. Lines inside a multi-line HTML comment are skipped or blanked."""
    scan = scan or default_scan_config()
    lines = normalize(text).split("\n")
    front_end = None
    # A byte order mark before the opening fence still starts front matter.
    if lines and lines[0].lstrip("\ufeff").strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                if _looks_like_front_matter(lines[1:index]):
                    front_end = index
                break
    ahead = _closes_ahead(lines)
    info: list[LineInfo] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    skip_level: int | None = None
    marker_off = False
    in_comment = False
    for index, line in enumerate(lines):
        number = index + 1
        keys = opt_keys(line)
        if front_end is not None and index <= front_end:
            title = title_span(line) if index != 0 and index != front_end else None
            if title:
                value, column = title
                info.append(LineInfo(number, line, "title", value, column, keys))
            else:
                info.append(LineInfo(number, line, "front", keys=keys))
            continue
        if in_comment or not in_fence:
            was_open = in_comment
            line, in_comment = mask_comment_lines(line, in_comment, ahead[index + 1])
            if was_open and not line.strip():
                info.append(LineInfo(number, line, "skip", keys=keys))
                continue
        marker = FENCE_RE.match(line)
        if marker:
            token = marker.group(1)
            if not in_fence:
                in_fence = True
                fence_char = token[0]
                fence_len = len(token)
            elif token[0] == fence_char and len(token) >= fence_len:
                in_fence = False
            info.append(LineInfo(number, line, "code", keys=keys))
            continue
        if in_fence:
            info.append(LineInfo(number, line, "code", keys=keys))
            continue
        stripped = line.strip()
        is_off = bool(OFF_LINE.match(stripped))
        is_on = bool(ON_LINE.match(stripped))
        if is_off:
            marker_off = True
        heading = HEADING_PARTS.match(line)
        if heading:
            level = len(heading.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and heading_matches(heading.group(2), scan.skip_headings):
                skip_level = level
        skipped = marker_off or skip_level is not None or is_off or is_on
        if is_on:
            marker_off = False
        kind = "skip" if skipped else "body"
        info.append(LineInfo(number, line, kind, keys=keys))
    return info


def _join(parts: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int]]]:
    text: list[str] = []
    origins: list[tuple[int, int]] = []
    for index, (number, line) in enumerate(parts):
        if index:
            text.append(" ")
            origins.append((number, 1))
        for offset, char in enumerate(line):
            text.append(char)
            origins.append((number, offset + 1))
    return "".join(text), origins


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Return [start, end) spans of sentences inside `text`.

    The spans cover the stripped sentence, so a caller can slice `text`
    and a parallel origin map with the same indexes.
    """
    protected = text
    for abbr in ABBR:
        protected = protected.replace(abbr, abbr.replace(".", "\0"))
    bounds: list[tuple[int, int]] = []
    cursor = 0
    for match in SENT_SPLIT.finditer(protected):
        bounds.append((cursor, match.start()))
        cursor = match.end()
    if protected[cursor:].strip():
        bounds.append((cursor, len(protected)))
    spans: list[tuple[int, int]] = []
    for start, end in bounds:
        raw = text[start:end]
        lead = len(raw) - len(raw.lstrip())
        core = raw.strip()
        if core:
            spans.append((start + lead, start + lead + len(core)))
    return spans


def _append_sentence(
    sentences: list[Sentence],
    line_text: str,
    origins: list[tuple[int, int]],
    start: int,
    end: int,
    scan: ScanConfig | None,
) -> None:
    raw = line_text[start:end]
    core = raw.strip()
    if not core:
        return
    lead = raw.find(core)
    origin_start = start + max(lead, 0)
    sentences.append(Sentence(
        kind="body",
        line=origins[origin_start][0],
        text=core,
        masked=mask_text(core, scan),
        origins=origins[origin_start:origin_start + len(core)],
    ))


def body_sentences(lines: list[LineInfo], scan: ScanConfig | None = None) -> list[Sentence]:
    """Body sentences in reading order.

    A heading or a table row is one unit, so a gloss in the next paragraph
    can still count as the next sentence. List items and prose are split
    into sentences. Wrapped prose lines in one paragraph are joined first.
    """
    sentences: list[Sentence] = []
    prose: list[tuple[int, str]] = []

    def flush() -> None:
        if not prose:
            return
        text, origins = _join(prose)
        for start, end in split_sentences(text):
            _append_sentence(sentences, text, origins, start, end, scan)
        prose.clear()

    for line in lines:
        if line.kind != "body":
            flush()
            continue
        stripped = line.text.strip()
        if not stripped or HR_RE.match(stripped) or _is_table_rule(line.text):
            flush()
            continue
        origins = [(line.number, offset + 1) for offset in range(len(line.text))]
        if HEADING_RE.match(line.text) or (TABLE_RE.match(line.text) and not _is_table_rule(line.text)):
            flush()
            _append_sentence(sentences, line.text, origins, 0, len(line.text), scan)
            continue
        if LIST_RE.match(line.text):
            flush()
            spans = split_sentences(line.text) or [(0, len(line.text))]
            for start, end in spans:
                _append_sentence(sentences, line.text, origins, start, end, scan)
            continue
        prose.append((line.number, line.text))
    flush()
    return sentences


def _is_table_rule(line: str) -> bool:
    return bool(re.match(r"^\s*\|?[\s:|-]+\|?\s*$", line)) and "-" in line


def is_structural_line(text: str) -> bool:
    """A heading, list marker, table row, or rule. Not a prose paragraph line."""
    stripped = text.strip()
    if not stripped:
        return True
    if HEADING_RE.match(text) or LIST_RE.match(text) or TABLE_RE.match(text) or HR_RE.match(stripped):
        return True
    return _is_table_rule(text)


def prose_paragraphs(lines: list[LineInfo]) -> list[list[LineInfo]]:
    """Body paragraphs. Headings, lists, tables, code, and skipped sections stay out."""
    groups: list[list[LineInfo]] = []
    current: list[LineInfo] = []
    for line in lines:
        if line.kind != "body" or is_structural_line(line.text):
            if current:
                groups.append(current)
                current = []
            continue
        current.append(line)
    if current:
        groups.append(current)
    return groups


def prose_sentences(lines: list[LineInfo], scan: ScanConfig | None = None) -> list[Sentence]:
    """Sentences from prose paragraphs only."""
    sentences: list[Sentence] = []
    for group in prose_paragraphs(lines):
        parts = [(line.number, line.text) for line in group]
        text, origins = _join(parts)
        for start, end in split_sentences(text):
            _append_sentence(sentences, text, origins, start, end, scan)
    return sentences


def line_suppressed(lines: list[LineInfo], number: int, *, rule_id: str, category: str) -> bool:
    for line in lines:
        if line.number == number and suppressed(line.keys, rule_id=rule_id, category=category, bucket=None):
            return True
    return False


def any_line_suppressed(lines: list[LineInfo], numbers: set[int], *, rule_id: str, category: str) -> bool:
    for number in numbers:
        if line_suppressed(lines, number, rule_id=rule_id, category=category):
            return True
    return False


def front_sentences(lines: list[LineInfo], scan: ScanConfig | None = None) -> list[Sentence]:
    sentences: list[Sentence] = []
    for line in lines:
        if line.kind != "title" or line.title_value is None or line.title_column is None:
            continue
        value = line.title_value
        origins = [(line.number, line.title_column + offset) for offset in range(len(value))]
        sentences.append(Sentence(
            kind="front",
            line=line.number,
            text=value,
            masked=mask_text(value, scan),
            origins=origins,
        ))
    return sentences
