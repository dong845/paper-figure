# Benchmark runner — one blind run of the skill on one paper

You run the paper-figure skill end to end, in **auto mode**, on one benchmark paper, exactly as a user
would get it — except that nobody answers questions. Read `SKILL.md` (in the skill directory given in the task
message) and follow it step by step. These rules add to it; where they differ, they win.

## Inputs (in the task message)
- `SKILL_DIR`, `PAPERFIG` (= `PYTHONPATH=SKILL_DIR python3 -m paperfig`, typed out in full in every command),
  `CONFIG` (`bench/phase1/<paper>/config.json`).
- `PREP` = `~/.cache/paper-figure/bench/<paper>/` prepared by `paperfig bench prepare`: `method.txt` (blind method
  text), `code/` (the code at a pinned commit), `prepared.json`.
- `MODEL` — the model name to record.

## Blind protocol (a run that breaks it is void)
- Never open `PREP/paper.pdf`, `PREP/original/`, or any PDF, crop or web page of this paper itself. The method text
  and the code are all you get. Do not use what you remember about this paper's figure.
- The reference scout gets `PAPER` = this paper's title and arXiv id, so it is never selected.

## Setup
```
RUN = ~/.cache/paper-figure/runs/bench-<paper>-<YYYYMMDD-HHMM>   (use the expanded path in every command)
$PAPERFIG run init RUN --mode auto --type <figure_type> --venue <venue> --draft PREP/method.txt --code PREP/code \
    --title "<title>" --arxiv <arxiv_id> [--focus "<focus>"] --model MODEL
```
Values come from `CONFIG`. The blueprint uses `figure.venue` = `<venue>` and `figure.width` = `<width>` from `CONFIG`.

## Auto-mode decisions (record each with `$PAPERFIG run decide … --by auto --why "…"`)
- `blueprint`: continue once facts are N/N covered; list discrepancies in the decision.
- `assets`: never run the project's code in a benchmark (no weights, no downloads); use marked placeholders.
- `style`: the design brief's recommendation; the `why` names the cards behind it.
- `delivery`: accept once `$PAPERFIG run check RUN` prints `ok`.

## Delivery
Follow ⑧ with `OUT = RUN/deliver/` (there is no user folder): `run deliver`, `run check`, record `delivery`, then
`$PAPERFIG run check RUN --final` must print `ok`; fix everything it lists. Reply with: `RUN`, the final lint counts, facts covered,
critic scores per round, open issues, and anything in `SKILL.md` that was unclear or did not work (specific).
