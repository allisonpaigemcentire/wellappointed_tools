# Bench

`slopcheck bench` measures two different things.

The clean folder is short public-domain prose. The number that matters there is false flags per 1,000 words. A hit on this prose is a false flag.

The labeled folder plants problems on purpose and lists the rule ids in `manifest.yaml`. The number that matters there is recall. These files are synthetic. Recall on them is higher than you should expect on a real draft.

Run your own drafts, and leave them outside git:

```bash
slopcheck bench --clean ~/drafts
slopcheck bench --labeled ~/labeled --clean ~/drafts
```

A labeled folder needs a `manifest.yaml` with a `cases` list. Each case names a `file`, an `expect` list of rule ids, and optional `briefs`. Set `missing_function_word: true` on a case to turn on that opt-in check. A `quiet` entry (`line` and `rule`) must not be flagged. That is how an intended quote is checked.
