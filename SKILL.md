---
name: paper-figure
description: Draws publication-quality method figures for AI research papers — overview/architecture diagrams, teasers (conceptual comparison) and module-detail diagrams — as editable draw.io plus PNG and PDF, from a paper draft and/or its code. Subagents analyse the draft and the code, a scout finds 5–10 similar top-venue papers to learn layout and texture from, the user picks the visual style from rendered samples, and every build is linted and reviewed by an independent critic before delivery. Use whenever someone wants a method figure, architecture/framework/pipeline/model diagram, teaser figure or module figure for a paper — e.g. "draw the method figure for my paper", "make an architecture diagram from this repo", "visualise our model for the CVPR submission", "帮我画论文的方法图", "画模型结构图/框架图", "把这个模块画成细节图". Not for plots or charts of results.
---

# paper-figure

Turns what a paper and its code actually say into a camera-ready method figure. Three promises hold on
every run: **faithful** (every box and arrow traces to the text or the code, and a facts gate checks the
figure against the paper), **named** (the authors' new modules carry their exact names), **honest** (no
generated images posing as results; anything unresolved is reported, never called "passed").

## Tools and setup
- `PAPERFIG` = `PYTHONPATH=<this skill's directory> python3 -m paperfig` — every `$PAPERFIG …` below.
  Exit codes: 0 ok · 1 checks failed (lint errors, invalid artifact) · 2 bad input · 3 internal error.
- Start every run with `$PAPERFIG doctor`: it checks Python packages, poppler (`pdftotext`, `pdftoppm`, `pdfinfo`)
  and draw.io desktop. If draw.io is missing, stop and tell the user how to install it (https://www.drawio.com).
- Subagent prompts live in `agents/`. Dispatch each with the Agent tool: *"Read `<skill dir>/agents/<name>.md` and
  follow it exactly"* plus its inputs, always including `PAPERFIG`. Never paste the prompt from memory.

## Run directory
`RUN = ~/.cache/paper-figure/runs/<paper-slug>-<YYYYMMDD-HHMM>/`
```
$PAPERFIG run init RUN --mode interactive|auto --type overview|teaser|module-detail --venue VENUE \
    [--draft PATH] [--code REPO] [--title "PAPER TITLE"] [--arxiv ID] [--focus MODULE] [--model MODEL]
```
creates `inputs/ assets/ refs/ samples/ build/ critic/` and `run.json`. Everything a run produces lives here;
`$PAPERFIG run check RUN` is the delivery gate (all artifacts present and validated, all four decisions recorded,
final build lint-clean and critic-reviewed).

**Modes.** `interactive` (default): stop at the four confirmation points below with AskUserQuestion (selectable
options, the recommended one first). `auto` (benchmarks, or the user said not to ask): take the default stated at
each point and record it — `$PAPERFIG run decide RUN --point P --decision "…" --by auto --why "…"`. In interactive
mode record the user's answer the same way with `--by user`.

Ask before starting only what you cannot infer: which figure (type, and the module for module-detail), target
venue (sets print width and font floor), and where the draft and code are. One AskUserQuestion, then go.

## ① Read the materials (two subagents in parallel)
1. Inputs: draft → `$PAPERFIG extract DRAFT --method-only --out RUN/inputs/method.txt` (accepts a .tex file or
   directory, .pdf, .md, .docx; add `--blind` in benchmark runs: strips figures and captions). Check the word count it
   prints — under ~300 words usually means the method heading was not found: extract without `--method-only` and
   cut the method part yourself. Code → `$PAPERFIG codemap REPO --out RUN/inputs/code_map.json`.
2. Dispatch together: **draft-analyst** (`METHOD_TEXT`, `FIGURE_TYPE`, `FOCUS`, `BLIND`, `OUT_DIR=RUN`) and
   **code-analyst** (`REPO`, `CODE_MAP`, `FIGURE_TYPE`, `FOCUS`, `OUT=RUN/analysis.code.json`). With only one input,
   dispatch only that analyst.
3. Validate yourself — never trust an artifact you did not check:
   ```
   $PAPERFIG validate draft-analysis RUN/analysis.draft.json --text RUN/inputs/method.txt
   $PAPERFIG validate facts RUN/facts.json --text RUN/inputs/method.txt --analysis RUN/analysis.draft.json
   $PAPERFIG validate code-analysis RUN/analysis.code.json --repo REPO
   ```
   On problems, send them back to the same agent (SendMessage) once; if they persist, fix the file yourself from
   the method text and code, never by loosening a quote.
4. Code only (no draft): there is no method text, so write `facts.json` from the code analysis (quotes are code
   lines, `ref` = `file:line`) and skip the facts `--text` check; say so in the report.

## ② Blueprint → **confirmation point `blueprint`**
1. Before writing, read `references/blueprint.md` (fields, worked examples) and `references/design.md` (layout
   patterns, density, emphasis). Pick the layout pattern from the design brief if step ④ has finished, else from
   the analyses and the domain's conventions.
2. Write `RUN/blueprint.json`: node ids = the draft analysis component ids (the facts use them); every node, group
   and edge carries provenance; proposed modules (the draft analysis' `proposed` roles and `contributions`) carry
   `full_name` + `abbrev` exactly as the paper writes them; connections the code shows but the text leaves implicit
   (e.g. the order of two sub-blocks) are drawn with `code` provenance; every draft-vs-code difference goes in
   `discrepancies` with your decision.
   - **overview** — the whole pipeline; sub-modules collapsed unless they are the contribution (then a detail panel).
   - **teaser** — conceptual comparison: prior approach(es) beside ours at the same scale, ours last.
   - **module-detail** — `FOCUS` and its internals: operators, thin layers, tensor names on edges.
3. `$PAPERFIG validate blueprint RUN/blueprint.json`, then a first render:
   `$PAPERFIG build RUN/blueprint.json --facts RUN/facts.json --out RUN/build/r0 --name fig --formats png`.
   Every `fact-*` error means the figure would omit or misstate what the paper says: fix the blueprint until
   `facts_covered` is N/N. Never waive a fact on your own.
4. Show the user: the r0 PNG, the list of components and connections, the proposed modules with their names, and
   each discrepancy with your decision. Options: *continue* / *change something*. After this point the content
   structure does not change unless the user asks.
   **auto:** continue; why = "facts N/N covered, M discrepancies decided as listed".

## ③ Assets → **confirmation point `assets`** (runs alongside ④)
1. List every `image`/`placeholder` node and what it needs (example input/output, attention map, data sample),
   merging both analyses' `assets`: an asset the code analysis can produce (`obtain: from-code`, with `how` and
   `needs`) replaces the draft analysis' `user` guess.
2. Source order: **run the project's code** > files already in the repo > ask the user > a marked placeholder.
   Run code directly only when it is light (no training, no large downloads, no long GPU jobs); otherwise list the
   command and ask. Copy obtained files into `RUN/assets/` and set `asset.status` (`from-code` / `provided`).
3. **Never** generate an image that stands in for a result, an input sample or a plot.
4. Tell the user promptly what is still missing — what, where in the figure, suggested size — and continue with
   placeholders (`status: requested`, a `spec`). Options: *I'll provide them (paths)* / *continue with placeholders*.
   **auto:** continue with placeholders; list them.

## ④ References + knowledge base (runs alongside ③)
1. Dispatch **reference-scout** (`ANALYSIS`, `PAPER` title + arXiv id, `FIGURE_TYPE`, `DOMAIN`, `VENUE`, `N=6`,
   `WORK=RUN/refs`). Then `$PAPERFIG validate refs RUN/refs/refs.json`.
2. Dispatch one **figure-card-writer** per selected figure, in parallel (`MODE=user`, `OUT=RUN/refs/cards/<id>.json`).
   Cards go to the user layer of the knowledge base (spec step ⑦ happens here).
3. `$PAPERFIG kb query --domain DOMAIN --venue VENUE --exclude-paper ARXIV_OR_TITLE --out RUN/brief.json` —
   the venue format, palettes with colour-blind safety numbers, the venue's quoted figure rules, the domain's
   conventions and the best matching cards (the paper's own cards are excluded).
4. Write `RUN/brief.md`, the design brief: layout pattern, flow direction, 2–3 palette candidates, how references
   draw data and highlight new modules, which style recipes fit — each point naming the card(s) it comes from.
- **Offline / no results:** `refs search` fails loudly when no service is reachable. Write `RUN/refs/refs.json` with
  `selected: []` and a `notes` entry saying why, build the brief from the knowledge base alone, and say so in the report.

## ⑤ Style → **confirmation point `style`**
1. `$PAPERFIG samples RUN/blueprint.json --styles A,B,C [--mix SECTION=STYLE …] --facts RUN/facts.json --out RUN/samples`
   renders the user's own blueprint in 2–4 recipes (`soft-pastel`, `depth-cv`, `editorial-minimal`;
   `drawio-default` only as a contrast) and writes `samples.png`. Samples with lint errors are never shown — the
   command lists them with the reason. Recommend the recipe the brief favours.
2. Show `samples.png`; options = the shown styles (recommended first) + *mix* — recipes combine by section
   (`typography`, `spacing`, `palette`, `shape`, `effects`, `tensor`, `edges`, `image`), e.g. B's colours with C's 3-D
   feature maps: `--style soft-pastel --mix effects=depth-cv --mix tensor=depth-cv`.
   **auto:** the brief's recommendation; why = the cards behind it.

## ⑥ Build, lint, critique, revise (at most 3 rounds)
For round N = 1, 2, 3:
1. `$PAPERFIG build RUN/blueprint.json --style S [--mix …] --facts RUN/facts.json --out RUN/build/rN --name fig`
   → `fig.drawio`, `fig.png` (300 dpi at the venue width), `fig.pdf`, `fig.lint.md`, `fig.lint.json`.
2. **Open `fig.png` yourself.** Read `fig.lint.md`; fix every error and every warning you can, using the table in
   `references/design.md`. Rebuild until exit code 0 (lint errors block delivery).
3. Dispatch **critic** (`agents/critic.md`) with `PNG`, `METHOD_TEXT`, `FACTS`, `BLUEPRINT`, `LINT`, `PRINT_WIDTH_IN`
   and `REFERENCES` (the selected crops). It must not see your reasoning. Save its JSON to `RUN/critic/rN.json`, then
   `$PAPERFIG run round RUN --n N --lint RUN/build/rN/fig.lint.json --critic RUN/critic/rN.json --note "what changed"`.
4. Apply every `high` and `medium` issue as a blueprint or style change (each `io_audit` omission is a missing edge
   or node — check it against the method text, then add it). Stop early when lint is clean and the critic reports
   no `high`/`medium` issue. Whatever is still open after round 3 goes into the report as open, not as fixed.

## ⑦ Deliver → **confirmation point `delivery`**
1. Output folder: where the user asked; otherwise ask once (default: a `figures/<paper-slug>/` folder next to the
   draft). Copy the final `fig.drawio`, `fig.png`, `fig.pdf`, `fig.lint.md`.
2. Before/after sheet: `$PAPERFIG contact --panel "Round 1=RUN/build/r1/fig.png" --panel "Final=RUN/build/rN/fig.png"
   --out OUT/compare.png` (add the user's previous figure as a first panel when they gave one).
3. Write `RUN/report.md` and copy it to the output folder: what the figure shows; proposed modules and their names;
   discrepancies and decisions; reference papers (title, venue, link, what was learnt); per round the lint counts and
   critic scores; open issues; placeholders still to replace (what, where, spec); how to edit (open the `.drawio`
   in draw.io; rebuild with the commands in the report).
4. `$PAPERFIG run check RUN` must print `ok` before you say the figure is done.
5. Show `compare.png` and the open items. Options: *accept* / *revise* (→ ⑤ or ⑥ with their notes).
   **auto:** accept; record.

## Rules that bind every run
- Faithfulness beats looks: nothing is drawn without provenance, and no fact is dropped to make a layout fit.
- Never generate images that pose as results, samples or plots; placeholders stay visibly marked until replaced.
- Reference PDFs and crops stay in `~/.cache/paper-figure/`; never copy them into deliverables or the skill.
- Paid services (paid Monid runs, keyed APIs) need the user's permission first; the free search and fetch suffice.
- Report what happened: if a check failed or a step was skipped, the report says so.

## Knowledge-base build (maintainers only)
When the user asks to build or extend the shipped knowledge base, read `references/build-kb.md`; its output must
pass `$PAPERFIG kb validate`.
