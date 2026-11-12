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
- The tool is a command prefix: `PYTHONPATH=<this skill's directory> python3 -m paperfig`, written `$PAPERFIG` below.
  **Type it out in full in every command** (do not store it in a shell variable — zsh and bash will not run it).
  Exit codes: 0 ok · 1 checks failed (lint errors, invalid artifact) · 2 bad input · 3 internal error.
- Start every run with `$PAPERFIG doctor` (Python packages, poppler, draw.io desktop). If anything is missing, stop
  and tell the user what to install (draw.io: https://www.drawio.com); in auto mode, stop and report the run as void.
- Subagent prompts live in `agents/`. Dispatch each with the Agent tool: *"Read `<skill dir>/agents/<name>.md` and
  follow it exactly"* plus its inputs, always including `PAPERFIG` written out in full. Never paste a prompt from memory.

## Modes
- **interactive** (default): stop at the four confirmation points — `blueprint`, `assets`, `style`, `delivery` — with
  AskUserQuestion (selectable options, the recommended one first) and record the answer:
  `$PAPERFIG run decide RUN --point P --decision "…" --by user --why "…"`.
- **auto** (benchmarks, or the user said not to ask): never ask; take the default stated at each point and record it
  with `--by auto`. Inputs come from the task message (a benchmark gives a config: `venue`, `width`, `figure_type`,
  `focus`, `domain`, `blind`). Every choice below marked **auto:** is the default.

## Start
1. Inputs. Interactive: ask once, only for what you cannot infer — figure type (and the module, for module-detail),
   target venue (sets the print width and font floor), draft and code locations. Auto: from the task message.
2. Paper identity: title = the draft's `\title{…}` / first heading; arXiv id only if the user or config gives one, else
   none. `SLUG` = the model's short name (or the title's first words), lower case with hyphens.
   `DOMAIN` = the closest id in `<skill dir>/kb/domains/` (e.g. `image-restoration`, `diffusion`, `vision-language`),
   else a new short slug (then the brief has cards but no domain conventions; say so in the report).
3. `RUN = ~/.cache/paper-figure/runs/<SLUG>-<YYYYMMDD-HHMM>`, then
   ```
   $PAPERFIG run init RUN --mode interactive|auto --type overview|teaser|module-detail --venue VENUE \
       [--draft PATH] [--code REPO] --title "TITLE" [--arxiv ID] [--focus MODULE] --model <your model id>
   ```
   This creates `inputs/ assets/ refs/ samples/ build/ critic/` and `run.json`; everything the run produces lives in `RUN`.

## ① Read the materials
1. Draft → `$PAPERFIG extract DRAFT --method-only --out RUN/inputs/method.txt` (.tex file or directory, .pdf, .md, .txt,
   .docx; add `--blind` only when the config says `blind: true`). Under ~300 words usually means the method chapter was
   not found: extract without `--method-only` and cut the method part yourself. Code → `$PAPERFIG codemap REPO --out
   RUN/inputs/code_map.json`.
2. Dispatch **draft-analyst** (`METHOD_TEXT`, `FIGURE_TYPE`, `FOCUS`, `BLIND`, `OUT_DIR=RUN`). When its output validates
   (step 3), dispatch **code-analyst** with `DRAFT_ANALYSIS=RUN/analysis.draft.json` (`REPO`, `CODE_MAP`, `FIGURE_TYPE`,
   `FOCUS`, `OUT=RUN/analysis.code.json`) so both use the same ids. With only one input, dispatch only that analyst.
3. Validate yourself — never trust an artifact you did not check:
   ```
   $PAPERFIG validate draft-analysis RUN/analysis.draft.json --text RUN/inputs/method.txt
   $PAPERFIG validate facts RUN/facts.json --text RUN/inputs/method.txt --analysis RUN/analysis.draft.json
   $PAPERFIG validate code-analysis RUN/analysis.code.json --repo REPO
   ```
   On problems, send them back to the same agent (SendMessage) once; if they persist, fix the file yourself from the
   method text and code — never by loosening a quote.
4. Code only (no draft): write `RUN/facts.json` from the code analysis (`quote` = the code line, `ref` = `file:line`)
   and validate it without `--text`; say so in the report.

## ② References (start now, in the background)
Right after ① validates, dispatch **reference-scout** (`ANALYSIS`, `PAPER` = title + arXiv id or `null`, `FIGURE_TYPE`,
`DOMAIN`, `VENUE`, `N=6`, `WORK=RUN/refs`) and continue with ③ while it works. When it returns:
`$PAPERFIG validate refs RUN/refs/refs.json`, then dispatch one **figure-card-writer** per selected figure, in parallel,
each with its `refs.json` entry (title, url, venue, venue_source, year, figure, crop, caption), `DOMAINS=[DOMAIN]`,
`MODE=user`, `OUT=RUN/refs/cards/<id>.json`. Their cards join the user layer of the knowledge base.
**Offline / nothing found:** the search fails loudly when no service answers. Write `RUN/refs/refs.json` with
`selected: []`, the queries tried and a `notes` entry saying why; the brief then rests on the knowledge base alone.

## ③ Blueprint → **confirmation point `blueprint`**
1. Read `references/blueprint.md` (fields, worked examples) and `references/design.md` (layout patterns, density,
   emphasis) before writing.
2. Write `RUN/blueprint.json`. **Content** — the nodes, edges, names and roles — comes from the analyses: node ids =
   the draft analysis ids (the facts use them); every node, group and edge carries provenance; proposed modules (the
   draft's `proposed` roles and `contributions`) carry `full_name` + `abbrev` exactly as the paper writes them;
   connections only the code shows (e.g. the order of two sub-blocks) carry `code` provenance; every draft-vs-code
   difference goes in `discrepancies` with your decision. Set `figure.venue` and `figure.width` (`double` / `single` /
   inches) — they fix the print width the lint and critic judge. **Layout** — groups' `layout`, cells, panels — is a
   first proposal from `references/design.md` and the domain's conventions; ⑤ may change it.
   - **overview** — the whole pipeline; sub-modules collapsed unless they are the contribution (then a detail panel).
   - **teaser** — conceptual comparison: prior approach(es) beside ours at the same scale, ours last.
   - **module-detail** — `FOCUS` and its internals: operators, thin layers, tensor names on edges.
3. `$PAPERFIG validate blueprint RUN/blueprint.json`, then a first render:
   `$PAPERFIG build RUN/blueprint.json --facts RUN/facts.json --out RUN/build/r0 --name fig --formats png`.
   Every `fact-*` error means the figure would omit or misstate the paper: fix the blueprint until `facts_covered`
   is N/N. Never waive a fact on your own.
4. Show the user the r0 PNG, the components and connections, the proposed modules with their names, and each
   discrepancy with your decision. Options: *continue* / *change something*. From here on the **content** changes only
   when the user asks or when a critic finding is backed by the method text (⑦); layout may change at any time.
   **auto:** continue; why = "facts N/N covered; discrepancies decided as listed".

## ④ Assets → **confirmation point `assets`**
1. List every `image`/`placeholder` node and what it needs (example input/output, attention map, data sample), merging
   both analyses' `assets`: one the code analysis can produce (`obtain: from-code`, with `how`, `needs`) replaces the
   draft analysis' `user` guess.
2. Source order: **run the project's code** > files already in the repo > ask the user > a marked placeholder. Run code
   only when it is light (no training, no large downloads, no long GPU jobs); otherwise list the command and ask.
   Copy obtained files into `RUN/assets/` and set `asset.status` (`from-code` / `provided`) and `asset.path`.
3. **Never** generate an image that stands in for a result, an input sample or a plot.
4. Tell the user promptly what is missing — what, where in the figure, suggested size — and continue with
   placeholders (`status: requested`, a `spec`). Options: *I'll provide them (paths)* / *continue with placeholders*.
   **auto:** never run the project's code; continue with placeholders and list them in the decision.

## ⑤ Design brief and layout
1. Wait for ② (cards written). `$PAPERFIG kb query --domain DOMAIN --venue VENUE --exclude-paper "ARXIV_ID or TITLE"
   --out RUN/brief.json` — the venue format, palettes with colour-blind safety numbers, the venue's quoted figure rules,
   the domain's conventions and the best matching cards (the paper's own are excluded; the new user cards are included).
2. Write `RUN/brief.md`: layout pattern, flow direction, 2–3 palette candidates, how the references draw data and
   highlight new modules, which style recipes fit — each point naming the card id(s) it comes from.
3. Revise the blueprint's layout to follow the brief (content unchanged), validate it and rebuild r0.

## ⑥ Style → **confirmation point `style`**
1. `$PAPERFIG samples RUN/blueprint.json --styles A,B,C --facts RUN/facts.json --out RUN/samples` renders the user's own
   blueprint in 2–4 recipes (`soft-pastel`, `depth-cv`, `editorial-minimal`; `drawio-default` only as a contrast) and
   writes `samples.png`. Samples with lint errors are never shown — the command lists them with the reason.
2. Show `samples.png`; options = the shown styles (the brief's favourite first) + *mix*. Recipes combine by section
   (`typography`, `spacing`, `palette`, `shape`, `effects`, `tensor`, `edges`, `image`): for a mix, render it first with
   `samples --styles BASE --mix SECTION=STYLE … --out RUN/samples/mix` and show it before recording.
   **auto:** the brief's recommendation, no mix; why = the cards behind it.

## ⑦ Build, lint, critique, revise (at most 3 rounds)
For round N = 1, 2, 3:
1. `$PAPERFIG build RUN/blueprint.json --style S [--mix SECTION=STYLE …] --facts RUN/facts.json --out RUN/build/rN --name fig`
   → `fig.drawio`, `fig.png` (300 dpi at the print width), `fig.pdf`, `fig.lint.md`, `fig.lint.json`.
2. **Open `fig.png` yourself.** Read `fig.lint.md`; fix every error and every warning you can with the table in
   `references/design.md`, rebuilding until the exit code is 0 (lint errors block delivery).
3. Dispatch **critic** (`agents/critic.md`) with `PNG=RUN/build/rN/fig.png`, `METHOD_TEXT`, `FACTS`, `BLUEPRINT`,
   `LINT=RUN/build/rN/fig.lint.md`, `PRINT_WIDTH_IN` = `print_width_in` from that lint report, and `REFERENCES` = the
   selected crops. It must not see your reasoning. Save its JSON to `RUN/critic/rN.json`, then
   `$PAPERFIG run round RUN --n N --lint RUN/build/rN/fig.lint.json --critic RUN/critic/rN.json --note "what changed"`.
4. Stop when lint is clean and the critic reports no `high`/`medium` issue. Otherwise, before the next round apply
   every `high` and `medium` issue as a blueprint or style change. An `io_audit` omission backed by a quote from the
   method text is a faithfulness correction: add the node/edge and its fact, and list it in the report. Remove approved
   content only with the user. Issues found in round 3 are **not** applied unbuilt — they go into the report as open.

## ⑧ Deliver → **confirmation point `delivery`**
1. `OUT` = the folder the user named; otherwise ask once (default: a `figures/<SLUG>/` folder next to the draft).
   **auto:** `RUN/deliver/`.
2. Before/after sheet: `$PAPERFIG contact --panel "Round 1=RUN/build/r1/fig.png" --panel "Final=RUN/build/rN/fig.png"
   --out RUN/compare.png` (add the user's previous figure as the first panel when they gave one).
3. Write `RUN/report.md` with exactly these sections: `## Figure` (what it shows; proposed modules and their names;
   discrepancies and decisions), `## References` (title, venue, link, what was learnt from each), `## Rounds` (lint
   counts and critic scores per round; what changed), `## Open issues`, `## Placeholders` (what, where, spec — or
   "none"); end with how to edit (open the `.drawio` in draw.io; the rebuild command).
4. `$PAPERFIG run deliver RUN --out OUT` copies the last round's files, `report.md` and `compare.png`; then
   `$PAPERFIG run check RUN` must print `ok` (artifacts, quotes, decisions so far, final round lint-clean and reviewed).
5. Show `compare.png` and the open items. Options: *accept* / *revise* (→ ⑤, ⑥ or ⑦ with their notes). Record the
   decision, then `$PAPERFIG run check RUN --final` must print `ok` before you call the figure done.
   **auto:** accept and record.

## Rules that bind every run
- Faithfulness beats looks: nothing is drawn without provenance, and no fact is dropped to make a layout fit.
- Never generate images that pose as results, samples or plots; placeholders stay visibly marked until replaced.
- Reference PDFs and crops stay in `~/.cache/paper-figure/`; never copy them into deliverables or the skill.
- Paid services (paid Monid runs, keyed APIs) need the user's permission first; the free search and fetch suffice.
- Report what happened: if a check failed or a step was skipped, the report says so.

## Knowledge-base build (maintainers only)
When the user asks to build or extend the shipped knowledge base, read `references/build-kb.md`; its output must
pass `$PAPERFIG kb validate`.
