# Contributing

Bugs, pattern tweaks, and dictionary entries are welcome.

## Setup

Run these from the `slopcheck/` directory:

```bash
pip install -e ".[dev]"
pytest
```

Python 3.11 or newer.

## Patterns

Built-in patterns live in `src/slopcheck/data/rules.yaml`. Each one needs an `id`, a `category`, a `severity` (`error` or `warning`), a Python regular expression, and a `suggestion` written in plain words.

Match case-insensitively. Keep the expression narrow. A warning is the right severity when the word is also ordinary English.

## Jargon

Built-in terms live in `src/slopcheck/data/jargon.yaml`.

1. Delete the term. If no real claim remains, the bucket is `cut`.
2. Will readers meet it again in a tool, a vendor doc, or a meeting? The bucket is `define`. The plain field is the short gloss to put on first use.
3. If they will not meet it again, the bucket is `replace`. The plain field is what to write instead.
4. Would nearly every reader already know it, and is it not a false friend? The bucket is `keep`.

Set `false_friend: true` when the everyday meaning misleads. A false friend cannot be `keep`. Give at least one alias or one regex. Use `(?-i:...)` when an acronym must keep its case, as with `RAG`.

Do not put an em dash in an entry. The loader rejects it.

## Tests

Add a case next to the category you touched. `pytest` runs the suite. A new pattern should have one line that flags and one line that should stay quiet.

## Tone of the docs

Plain words. No hype. No em dashes. Quote a term when you are talking about the term.
