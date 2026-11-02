# slopcheck

slopcheck flags prose that reads like a model wrote it, and AI jargon a reader cannot check. It prints the line, the column, the matched words, and a plain-language fix.

You can run it on a file, a folder, or a pipe. In CI it exits with a non-zero status when the errors pass a threshold you set.

## What it catches

Seven pattern groups, plus a jargon dictionary, plus prose checks for repetition, a brief, rhythm, and edit damage.

**AI-tell words and phrases.** "Delve", "tapestry", "unlock the potential", "let's dive in", "in today's fast-paced world". These show up far more often in model output than in edited prose. The fix is a concrete verb, or a cut.

**Contrast frames.** "Not only X, but Y" and "it isn't X, it's Y". They announce a twist. State the point.

**Reveal fragments.** "The result?", "Here's the thing". Put the finding in the sentence that carries it.

**Summary closers.** "The bottom line", "Ultimately", "In conclusion". Stop on the last useful fact.

**Filler hedges.** "It's important to note", "it's worth noting", "when it comes to". If it matters, say the fact.

**Significance tails.** A comma plus "highlighting", "underscoring", "ensuring", and the same family. End the sentence on the fact. These are warnings.

**Em dashes.** More than two in any 300-word stretch is a warning. The limit is configurable. Periods and commas are enough. A spaced double hyphen (` -- `) counts as one.

**Repeated phrases.** A run of 4 or 5 content words, repeated more than twice in one document. Function words do not count, so a string of "of the" stays quiet. Quoted text and headings are left out. The report gives the phrase, the count, and the locations.

**Near-duplicate sentences.** A sentence or a short passage said again with small changes, including a speech. Headings are left out. Quotes are kept, because the repeated speech is the case this check is for.

**Brief leaks.** Optional. Pass the prompt, outline, or brief with `--brief` (repeatable) or `brief` in the config. A sentence in the draft that copies the brief too closely is a warning. A line the brief marks as an intended quote is allowed. The same check covers a newsletter and a story.

**Rhythm.** The share of sentences at 25 words or more, the mean length, the standard deviation, the coefficient of variation, a run of similar-length sentences, and the share of words inside double quotes when the draft has dialogue. These are warnings, and each threshold is configurable. A flat, uniform rhythm is the one that warns. A short note stays quiet.

**Edit damage.** A sentence that starts with a lowercase letter after `.` `?` or `!`, a doubled word (`the the`), a clause or sentence copied twice in one paragraph, and a dangling comma or quote (`simply, ”`). A missing function word (`the of`) stays off unless you ask for it.

Some of the word hits are warnings rather than errors, because the word is also ordinary English ("robust", "leverage", "moreover"). The new prose checks are warnings too. Errors fail a default run. Warnings are printed and do not fail it unless you ask.

What is on by default, and what is not:

| Check | Default |
|---|---|
| Repeated phrase, near-duplicate | On. Warning. |
| Rhythm (flat, long, similar run) | On. Warning. Thresholds are strict, so a short or varied note stays quiet. |
| Lowercase start, doubled word, duplicated clause or sentence, dangling punctuation | On. Warning. |
| Brief leak | On only when you pass a brief. Warning. |
| Missing function word | Off. `--function-words`, or `edit_damage.missing_function_word: true`. The pattern is narrow and still misfires. |

The jargon file sorts terms into four buckets:

| Bucket | What the checker does |
|---|---|
| Keep | Readers already know the word. "Prompt" and "benchmark" are here. Never flagged. |
| Define | Fine to use, but the first mention needs a short gloss. |
| Replace | Flagged on every use, with plain words to write instead. |
| Cut | Flagged on every use. Delete it, or put a fact in its place. |

A false friend is a word whose everyday meaning misleads: "agent", "harness", "grounding", "tokens", "temperature", "memory", "reasoning", "hallucination", and any entry marked `false_friend: true`. A false friend cannot sit in Keep. It is flagged on first use when that use has no definition beside it. Replace and cut still win when that is the bucket, so "grounding" is flagged every time.

Replace and cut are also checked in titles: a Markdown heading, and front-matter fields named title, subtitle, excerpt, description, summary, preheader, or subject. A slug is left alone.

## Why these rules

Plain language is easier to act on. The GOV.UK style guide tells writers to cut "in order to", "going forward", and "utilise", and to use the short word ([A to Z style guide](https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/style-guides/a-to-z-style-guide/)). Nielsen Norman Group makes the same case for expert readers: plain language is for people who know the field, too ([Plain Language Is for Everyone, Even Experts](https://www.nngroup.com/articles/plain-language-experts/)).

The buckets follow a practical test. If readers will meet the term in a tool or a vendor doc, define it once by what it does. An agent (a model that uses tools, checks the result, and picks the next step) is the sense Anthropic spells out in [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents). If they will not meet the term again, write what the thing does. Vibe coding (building software with AI without reading the code it writes) needs that narrow gloss, which is the point of Simon Willison's note, [Not all AI-assisted programming is vibe coding](https://simonwillison.net/2025/Mar/19/vibe-coding/). If the term has no claim under it, cut it. Agent washing (selling an ordinary chatbot or script as an agent) is the pattern in Gartner's [June 2025 press release](https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027).

## Install

Python 3.11 or newer.

The package is named `wellappointed-slopcheck`. The command you run and the module you import are still `slopcheck`. The name `slopcheck` on PyPI belongs to a different project, so `pip install slopcheck` installs someone else's code and a different `slopcheck` command. `wellappointed-slopcheck` is not on PyPI yet. Install from this repository instead:

```bash
pip install "wellappointed-slopcheck @ git+https://github.com/allisonpaigemcentire/wellappointed_tools#subdirectory=slopcheck"
```

The term suggester is optional:

```bash
pip install "wellappointed-slopcheck[suggest] @ git+https://github.com/allisonpaigemcentire/wellappointed_tools#subdirectory=slopcheck"
```

From a clone of the repository root, `pip install ./slopcheck` does the same. If you installed an earlier copy from this repository under the old package name, run `pip uninstall slopcheck` first, so two packages do not claim the same files.

From a checkout of this directory (`slopcheck/` in [wellappointed_tools](https://github.com/allisonpaigemcentire/wellappointed_tools)):

```bash
pip install -e ".[dev]"
pytest
```

## Usage

```bash
slopcheck path/to/file.md
slopcheck docs/
slopcheck --json post.md
cat post.md | slopcheck
slopcheck --fail-on warning post.md
slopcheck --max-errors 0 --max-warnings 10 post.md
slopcheck --suggest-terms post.md
slopcheck --brief outline.md draft.md
slopcheck --baseline old.md new.md
slopcheck diff old.md new.md
slopcheck --show-rhythm draft.md
slopcheck bench
slopcheck bench --clean ~/drafts
```

A text report looks like this:

```text
post.md:3:8: error: ai-tell: "delve": Use a plain verb such as look at, examine, or cover.
post.md:4:5: warning: jargon/define: "RAG": Define it on first use: The AI looks up relevant documents first, then answers from them.
```

`--json` prints one object with `findings`, `summary`, and `ok`. Each finding has the path, line, column, severity, category, matched text, and suggestion. Jargon findings also have `bucket` and `false_friend`. When the draft has prose sentences, the object also has `rhythm`: sentence count, mean, population standard deviation, coefficient of variation, the long-sentence share, the longest similar run, and dialogue share. `--show-rhythm` prints those numbers in the text report even when they stay under the warning line. A diff adds `fixed`, the findings the edit removed. They use severity `fixed` and do not fail the run.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Under the threshold |
| 1 | Over the threshold |
| 2 | Bad arguments, a broken rules file, or `--suggest-terms` without wordfreq |

By default only errors fail the run. `--max-errors` defaults to 0. `--max-warnings` defaults to no limit. `--fail-on warning` treats any warning as a failure. `--fail-on none` always exits 0 on findings.

A line can silence a hit. The comment takes a pattern id, a category, a jargon term, `jargon` for every jargon hit on the line, or `*`. Free text after that list is a note, not another id. Put the note in parentheses, or after a spaced hyphen, or after a spaced em dash or en dash. `slopcheck-ok` and `slop-ok` both work.

```markdown
The team likes to delve. <!-- slopcheck-ok: delve -->
The vendor calls it agentic. <!-- slop-ok: jargon (approved wording) -->
Let's dive in. <!-- slopcheck-ok: lets-dive-in - kept on purpose -->
```

Quoted text, fenced code, and inline code are not scanned. Double quotes count, straight or curly. A title wrapped in YAML quotes is still checked: the quotes are the file format, and the words inside are the title.

HTML comments are not scanned. A bracketed editor note is not scanned either. The default shape is `[NAME: ...]`, where `NAME` is all capitals and a colon. `[EDITOR: a private remark]` drops out. `[AI champions](https://example.com)` does not, because the label is not an all-caps name. Only the link text is checked. The URL of a link or an image is not a gloss, and it is not searched. The alt text of an image is checked, the same way as link text.

## Sections you can skip

A heading is left out, along with everything under it, when its text contains one of these phrases. Case does not matter, and a hyphen is treated like a space. The skip stops at the next heading of the same level or a higher one. A deeper heading stays inside the skip.

- Claim trace
- Claim-trace
- Sources (not for publication)
- Editor notes
- Not for publication

Two markers, each on its own line, skip a stretch that is not a heading:

```markdown
<!-- slopcheck-off -->

This stretch is not checked.

<!-- slopcheck-on -->
```

A marker inside a fenced code block does not toggle the checker. A marker has to be the whole line.

## Configuration

A file named `.slopcheck.yaml` in the current directory is read when it exists. `--config PATH` points somewhere else. `--no-config` ignores it.

```yaml
max_errors: 0
max_warnings: 5
fail_on: error          # error, warning, or none
disable_patterns:
  - robust
disable_terms:
  - autonomous
  - uv / pip
exclude_categories: []
no_emdash: false
em_dash:
  severity: warning
  max_per_window: 2
  window_words: 300
rules: ./extra-rules.yaml
jargon: ./extra-jargon.yaml
# A prompt, outline, or brief. A string or a list.
brief:
  - ./outline.md
baseline: ./previous.md
known_names:
  - Holmes
repetition:
  more_than: 2          # flag a content phrase used more than this many times
  min_ngram: 4
  max_ngram: 5
  near_threshold: 0.86
rhythm:
  long_words: 25
  long_share: 0.70
  cv_below: 0.15         # coefficient of variation under this is flat
  min_sentences: 8
  run_length: 5
  run_span: 3
edit_damage:
  missing_function_word: false
brief_check:
  overlap: 0.72
  ngram: 5
# Replace the defaults. An empty list turns that skip off.
skip_headings:
  - Claim trace
  - Internal only
editor_notes:
  - '\[[A-Z][A-Z0-9]*(?:[ /-][A-Z0-9]+)*:[^\]]*\]'
```

`--rules` and `--jargon` on the command line override those paths for one run. `--emdash-max`, `--emdash-window`, and `--no-emdash` override the density check.

## Extending the rules

A user pattern file merges into the built-in list. The same `id` replaces that pattern. `replace: true` drops the built-ins.

```yaml
disable:
  - moreover
em_dash:
  max_per_window: 1
patterns:
  - id: circle-back
    category: filler-hedge
    severity: error
    pattern: '\bcircle back\b'
    suggestion: Say when you will reply.
```

A jargon file merges by term name. Omitted fields stay as they are, so you can change a bucket without copying the aliases.

```yaml
disable:
  - temperature
entries:
  - term: workspace
    bucket: define
    plain: the folder and tools a coding agent can see
    false_friend: false
    aliases:
      - workspace
```

Aliases are case-insensitive. A hyphen and a space are interchangeable, and a plural `s` or `es` is allowed. A `regex` list holds anything an alias cannot express. `(?-i:\bRAG\b)` keeps the acronym in that case, so the ordinary word "rag" stays quiet.

`replace: true` at the top of a jargon file uses only your entries. Markdown works too, if the entries sit in a fenced yaml block between `<!-- jargon-data:start -->` and `<!-- jargon-data:end -->`.

Buckets are `keep`, `define`, `replace`, and `cut`. An entry needs `term`, `bucket`, `plain`, `false_friend`, and at least one alias or regex. Do not put an em dash in an entry.

### When a first use counts as defined

For a Define term, and for a false friend, only the first use in the body matters. Later uses need no gloss. The checker looks in that sentence and the next one.

After the term, any of these counts: a parenthesis, a colon with a space after it, a spaced hyphen, "X, meaning", "X, which", "X, or", "X, a" or "X, an", "X, that is", "X, i.e.", "X, short for", "X is a", "X means", "X refers to", "X stands for".

Before the term: "what we call X", "called X", "known as X", or "(X)".

The next sentence counts when it opens with "That is", "In other words", "This means", "It is", and the same family, or when the term shows up again there with one of the markers above.

```text
RAG (a lookup before the answer) keeps the draft honest.
A widget is a small part.
The team added a widget. That is, a small part that holds the door.
```

```text
The widget broke. We waited. A widget is a small part.
```

The third sentence is too late. The first use still warns.

This is a heuristic. "The agent is a mess" looks defined, because "is a" is one of the markers. Read the gloss.

## Suggest unfamiliar terms

`--suggest-terms` lists words whose English Zipf score in wordfreq is under 3, and that are not already in the jargon dictionary. A Zipf score under 3 is rare in ordinary English. Words shorter than four letters are skipped. The list is a hint for the dictionary. It does not change the exit code.

```bash
slopcheck --suggest-terms draft.md
```

Install wordfreq with the `suggest` extra, or the run exits with status 2.

## Pre-commit and GitHub Actions

This directory ships `.pre-commit-hooks.yaml`. pre-commit loads that file from the root of a git repository. In [wellappointed_tools](https://github.com/allisonpaigemcentire/wellappointed_tools) the package is `slopcheck/`, so a remote hook for the whole repository will not install it. Install from this directory, then use a local hook:

```yaml
repos:
  - repo: local
    hooks:
      - id: slopcheck
        name: slopcheck
        entry: slopcheck
        language: system
        types_or: [markdown, text, rst]
```

`examples/pre-commit-config.yaml` is that sample. A sample workflow that installs `./slopcheck` and checks a docs folder is in `examples/github-action.yml`. The tests for this repository run from `.github/workflows/ci.yml` at the repository root. Install from this directory with `pip install .`, or from git as in Install, and call `slopcheck` the same way. Do not use `pip install slopcheck`: that PyPI name is a different project.

## Before and after

Before:

```text
In today's rapidly evolving landscape, it's important to note that agentic workflows aren't just automation, they're a paradigm shift. The result? Teams can unlock the potential of AI. Ultimately this changes delivery, highlighting the role of guardrails.
```

After:

```text
The deploy script asks a person before it pushes to production. Last week that check blocked two force-pushes. The team still writes the prompt and the tests.
```

The same pair is in `examples/sample-before.md` and `examples/sample-after.md`.

## Names and sentence starts

A capital letter at the start of a sentence is not a name. The word counts as a name only when the same spelling also appears capitalised later in a sentence, or it is on the known-names list (`data/names.txt`, `known_names` in the config, or `--known-name`).

That rule is used in two places. A pattern hit whose words are all confirmed names is skipped, so "Foster" the person is quiet and "foster" the verb is not. A sentence that starts with "Copilot" is the generic noun, not the product, unless the document also capitalises it mid-sentence or you add the name to the list. "GitHub Copilot" is unchanged: the capital is not the first word.

The rhetorical opener ("Have you ever", and the same family) matches the start of a sentence. A wrapped line that continues the sentence above does not count. "in today's" is bounded so it does not fire inside a longer word.

`--suggest-terms` still lists a rare word that is capitalised only because the sentence starts. A confirmed name is left off that list.

## Briefs

`--brief PATH` can be repeated. The config keys `brief` and `briefs` take a path or a list. Every draft in the run is compared with those files.

Two markers in the brief are the allowlist:

```markdown
The east pier stays open until the lamp is repaired.
<!-- slopcheck-quotes -->
This sentence is meant to be copied.
<!-- /slopcheck-quotes -->

This one is meant to be copied too. <!-- slopcheck-quote -->
```

A draft sentence is a leak when it shares a 5-word content run with a brief sentence, or when its content-word overlap is at least 0.72 and it has at least 6 content words. Both numbers are `brief_check.ngram`, `brief_check.overlap`, and `brief_check.min_content_words`. An allowed sentence is not a leak.

## Before and after

`slopcheck diff OLD NEW` and `--baseline PATH` compare findings, not lines. A hit that is still the same phrase after the edit is neither new nor fixed. Rhythm warnings are compared by rule, because the numbers move when the prose moves.

The text report lists new findings first. Fixed findings follow, marked `fixed`. The exit code uses only the new findings. A fixed error does not fail the run.

A directory is paired by relative path. A file that exists only in the edit is all new. A file that exists only in the baseline is all fixed.

## Bench

`slopcheck bench` measures the shipped corpus. `--clean DIR` measures a folder of your own drafts and does not copy it into git. `--labeled DIR` reads a `manifest.yaml` of planted problems. See [bench/README.md](bench/README.md).

On the shipped corpus, this is the measured result:

Clean corpus: 6 files, 1148 words, 0 findings, 0.00 false flags per 1,000 words. Labeled corpus: 11 of 11 planted hits, recall 1.00.

The clean files are short public-domain excerpts (Austen, Carroll, Thoreau, Doyle, Shelley, Lincoln), with the source named in each file. Two of them stop before an em dash in the transcription, so this run does not exercise the em-dash rule. Zero false flags on 1,148 words is not a promise about a novel or a newsletter. Point `--clean` at your own folder.

The labeled files plant the problems and then ask the checker to find them. Recall of 1.00 on that set overstates accuracy on a real draft. A unit test is not this measurement. The sentence above is the output of `slopcheck bench`.

## Limits

The checker is a set of regular expressions, a dictionary, and counts over words and sentences. It does not call a model.

A gloss two sentences later does not count. A comma plus "or" does count, so a weak line can pass. "X is a mess" looks defined.

Patterns do not cross a line break. Jargon can, when the break is inside one paragraph. A blank line starts a new sentence.

"Token", "temperature", "inference", "autonomous", "uv", and "pip" are in the dictionary because drafts use them in an AI sense. A security credential, a statistics paper, or a package install can trip them. Disable the term, or put `<!-- slopcheck-ok: jargon -->` on the line, when the everyday meaning is the one you mean.

Rhythm warnings wait until a document has enough sentences, and the flat-rhythm bar is strict. A careful essay can still trip a long-sentence warning if you lower `rhythm.long_share`. Dialogue share counts words inside straight or curly double quotes on one paragraph. It does not cross a blank line, and it is not itself a warning.

The checker does not flag a mental-state verb ("the model wants"). That call needs more context than a regex.

A skip phrase matches when the heading contains it, so a heading that merely mentions one of those phrases is left out too. Set `skip_headings` to change the list.

`--suggest-terms` misses a multi-word coinage unless it is hyphenated, and it will surface rare but innocent words. A confirmed name is skipped. A capital that exists only because the sentence starts is not skipped.

## License

MIT. See [LICENSE](LICENSE). Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md).

Allison McEntire, an AI Enablement Lead, wrote the rules this tool started from and released them for general use.
