---
name: paper-figure
description: Draws publication-quality method figures for AI research papers — overview/architecture diagrams, teasers (conceptual comparison) and module-detail diagrams — as editable draw.io plus PNG and PDF, from a paper draft and/or its code. Subagents analyse the draft and the code, a scout finds 5–10 similar top-venue papers to learn layout and texture from, the user picks the visual style from rendered samples, and every build is linted and reviewed by an independent critic before delivery. Use whenever someone wants a method figure, architecture/framework/pipeline/model diagram, teaser figure or module figure for a paper — e.g. "draw the method figure for my paper", "make an architecture diagram from this repo", "visualise our model for the CVPR submission", "帮我画论文的方法图", "画模型结构图/框架图", "把这个模块画成细节图". Not for plots or charts of results.
---

# paper-figure

Turns what a paper and its code actually say into a camera-ready method figure. Three promises hold on
every run: **faithful** (every box and arrow traces to the text or the code, and a facts gate checks the
figure against the paper), **named** (the authors' new modules carry their exact names), **honest** (no
generated images posing as results; anything unresolved is reported, never called "passed").

## Cost (keep it proportionate)
Tokens go to subagents: the two analysts, one scout (which also writes the reference cards, reusing existing ones),
and one critic round. Everything else is deterministic tooling. Do not add agents, extra critic rounds or extra
searches beyond what a step asks; reuse cards (`kb find`, `kb harvest`) and let the user review instead of looping.

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
   $PAPERFIG validate facts RUN/facts.json --text RUN/inputs/method.txt --analysis RUN/analysis.draft.json [--repo REPO]
   $PAPERFIG validate code-analysis RUN/analysis.code.json --repo REPO
   ```
   With both a draft and code, a fact whose `ref` is `file:line` quotes the code and is checked there (add
   `--repo`); every other fact quotes the method text. When the draft barely describes the architecture (a short or
   table-heavy method text — `run init` warns), add the code's main flows as `file:line` facts so the gate checks them.
   On problems, send them back to the same agent (SendMessage) once; if they persist, fix the file yourself from the
   method text and code — never by loosening a quote.
4. Code only (no draft): write `RUN/facts.json` from the code analysis (`quote` = the code line, `ref` = `file:line`)
   and `$PAPERFIG validate facts RUN/facts.json --repo REPO --analysis RUN/analysis.code.json` (every quote is
   checked at its file:line). Later steps then use `RUN/analysis.code.json` wherever they name
   `analysis.draft.json`, and the critic's `METHOD_TEXT` is the code map plus the code analysis — say so in the
   report.

## ② References and design brief (every run — never skipped)
Looking at how the most similar papers draw *their* methods is how a figure avoids a house style, so the search
runs on every paper, before any plan or layout. Adapting what was found is a choice, not a duty: when no reference
fits this method (after looking at them), design from the material and the target venue's conventions instead
(`adapts: "none"` in the plan).
1. As soon as the draft analysis validates (in parallel with the code analyst — the scout needs only the draft
   analysis), dispatch **reference-scout** (`ANALYSIS`, `PAPER` = title + arXiv id or `null`,
   `FIGURE_TYPE`, `DOMAIN`, `VENUE`, `N=6`, `WORK=RUN/refs`). It ranks by method-structure similarity (same task
   **and** similar architecture or mechanism) and rejects figures that redraw this paper. Read
   `references/design.md` while it works.
2. `$PAPERFIG validate refs RUN/refs/refs.json`. The scout has written (or reused, `kb find`) one card per selected
   figure in `RUN/refs/cards/` following `agents/figure-card-writer.md` (a reused card is copied in with
   `kb copy-card`) — no per-figure agents, which is where most of a run's tokens used to go. Read the cards; open
   only the crop(s) of the reference you consider adapting (the scout has already looked at every crop).
3. `$PAPERFIG kb query --domain DOMAIN --venue VENUE --run-cards RUN/refs/cards --exclude-paper "ARXIV_ID or TITLE"
   [--exclude-paper ID …] --out RUN/brief.json` — repeat `--exclude-paper` for every figure the scout rejected as a
   redraw or extension of this paper. The brief holds the venue format, palettes with colour-blind safety numbers, the
   venue's quoted figure rules, the domain's conventions and the best matching cards (this run's first).
   `$PAPERFIG kb coverage` shows how much the knowledge base knows: when this paper's domain is `THIN`, has no
   domain volume, or has no card of this `FIGURE_TYPE`, say so at the blueprint gate and lean on this run's own
   references (and `kb harvest` afterwards, so the next paper finds them).
4. Write `RUN/brief.md`: for each selected reference, what its figure does well (composition, how data is drawn, how
   the contribution is set apart); flow direction; 2–3 palette candidates; which style recipes fit — each point
   naming the card id(s) it comes from.
**Offline / nothing found:** the search fails loudly when no service answers. Write `RUN/refs/refs.json` with
`selected: []`, the queries tried and a `notes` entry saying why; the brief and the plan then rest on the
knowledge base's cards alone — say so at the blueprint gate.

## ③ Figure plan — the design Brief
Write `RUN/figure_plan.json` (schema `paperfig/schema/figure_plan.schema.json`, `"brief_version": 2`) before any
blueprint. It is the user's design-guide Brief: a reader gets the whole method in ~5 s, the contribution and the
problem it solves in ~30 s, the key mechanism in ~2 min. Fill it from the analyses (`contributions`,
`train_vs_infer`, `equations`) and the brief, not from taste — and pick how each contribution is shown from
`references/design.md` § From contribution to composition.
- **What the reader gets:** `takeaway` (one sentence, ~10 s); `problem` (the bottleneck addressed); `io` (`inputs`,
  `outputs` as the reader should see them).
- **Contribution (30 s):** `contributions` — at most 3: `name` (the paper's), `solves`, `shown_by` (the technique
  that makes it salient), `ids` (nodes, groups or brackets). Several contributions read as one story — connect them
  through the representation they share. `highlight` — how the contribution stands out overall.
- **Mechanism (2 min):** `mechanism` — 1–2 entries: `explains`, `ids` where it is drawn, the zoom-in `panel` (a
  group with `detail_of`) when it is expanded beside the overview — leave `panel` out when the mechanism is drawn
  in place inside its module — and the `equations` it follows (the ids of the draft analysis' `equations`, e.g.
  `eq_enc` — not "Eq. (1)").
- **Composition:** `concepts` — 2–3 genuinely different candidates; each `adapts` a selected reference (arXiv id),
  a card id (knowledge base or this run) or `"none"`, and says what it `takes` (composition, data depiction,
  emphasis — or, for `none`, the material and venue conventions it follows). `chosen` + `why` (best for this method
  and reader, not easiest to draw). `core` — the main line's top-level units (overview/teaser: at most 8).
- **Data:** `data_visuals` — how each input, output and key intermediate is drawn (`image`, `feature-map`, `tokens`,
  `text-example`, …) and where each image comes from (`source`: `repo` demo file → `dataset` = one sample of the
  paper's public dataset → `public-sample` = another licence-permitting public sample, both with `url` + `licence`
  → `thumbnail` = a data-thumbnail glyph, schematic and marked `illustrative` → `placeholder`). **Never** a generated
  image.
- **Grammar:** `train_only` / `infer_kept` ids; `key_representations` (a recurring representation: `ids`, one
  `visual` and `tone`); `color_semantics` (blueprint tone name → meaning, one meaning per tone — the tone names, not the colours a style paints them in); `annotate` (shapes/scales to
  label); `export` (width, formats).
- **What is not drawn:** `drawn_as` — components drawn as part of something else (`{"ids": [...], "on_edge": "<edge
  id>", "how": "label E"}` for a label on an arrow; `{"ids": [...], "into": "<node>", "how": "merged"}` merged into
  a box; `"into": [nodes]` one copy per timestep) — their facts are checked through what is drawn; use it, not `omitted`, for anything that
  *is* drawn. `omitted` — every fact (by id) not drawn, with `reason` and `where` the reader finds it (`text`,
  `caption`, `detail-panel`, `other-figure`); `omitted_details` — the same for non-fact details. Omit details,
  never the main line or the contribution: omitting every fact is an error, more than half a warning.
`$PAPERFIG validate figure-plan RUN/figure_plan.json --facts RUN/facts.json --refs RUN/refs/refs.json --analysis RUN/analysis.draft.json`.
A worked example: `references/examples/restormer.figure_plan.json`. Then **choose by looking**: write each concept as
a skeleton (`RUN/concepts/<id>.json`: top-level units and main edges only) and
`$PAPERFIG sketch RUN/concepts/*.json --out RUN/concepts`; open `sketches.png` and confirm or change `chosen`
(`references/design.md` § Choosing the composition by looking).

## ④ Blueprint → **confirmation point `blueprint`**
1. Read `references/blueprint.md` (fields, worked examples) before writing.
2. Write `RUN/blueprint.json` drawing the **chosen concept**: its composition (from the adapted reference, or from
   the material and the venue's conventions), the `core` units, the `data_visuals` as real visuals (`image`,
   `stack`/`tensor`, `tokens` with `values`, `glyph`, `text`), the highlight. Know the engine's limits first
   (`references/blueprint.md` § Known engine limits) so the layout does not fight them.
   **Content** comes from the analyses: node ids = the draft analysis ids (the facts use them); every node, group
   and edge carries provenance; proposed modules (the draft's `proposed` roles and `contributions`) carry
   `full_name` + `abbrev` exactly as the paper writes them; connections only the code shows carry `code`
   provenance; every draft-vs-code difference goes in `discrepancies` with your decision. Set `figure.venue` and
   `figure.width` (`double` / `single` / inches) — they fix the print width the lint and critic judge. An overview
   is **wide** (full text width, main line horizontal, w/h ≈ 2–3 like the references; `references/design.md` §
   Width and aspect); use a single column only when the user asks for one.
   - **overview** — the main pipeline; sub-modules collapsed unless they are the contribution (then a detail panel).
   - **teaser** — conceptual comparison: prior approach(es) beside ours at the same scale, ours last.
   - **module-detail** — `FOCUS` and its internals: operators, thin layers, tensor names on edges.
3. `$PAPERFIG validate blueprint RUN/blueprint.json`;
   `$PAPERFIG validate figure-plan RUN/figure_plan.json --facts RUN/facts.json --refs RUN/refs/refs.json --blueprint RUN/blueprint.json --analysis RUN/analysis.draft.json`;
   then a first render: `$PAPERFIG build RUN/blueprint.json --facts RUN/facts.json --out RUN/build/r0 --name fig --formats png`
   (the plan next to the blueprint is applied). A fact in `omitted` is reported as `fact-omitted` (info); every
   other `fact-*` error means the figure misstates the paper or leaves out something the plan did not decide to
   leave out: fix the blueprint, or add the fact to `omitted` with its reason. Never waive a fact silently.
4. Show the user: the r0 PNG; the selected reference crops and the concepts (which one was chosen and why); the
   Brief (problem, I/O, contributions → what each solves, mechanism and its zoom-in, training-only parts, colour
   semantics); **the omitted list — each fact's quote, reason and where the reader finds it**; the proposed modules
   with their names; each discrepancy with your decision. Options: *continue* / *draw some omitted facts* /
   *change something*. From here on the **content** changes only when the user asks or when a critic finding is
   backed by the method text and not deliberately omitted (⑦); layout may change at any time.
   **auto:** continue; why = "facts N/N covered or planned-omitted (list ids); discrepancies decided as listed".

## ⑤ Assets → **confirmation point `assets`**
1. List every `image`/`placeholder` node and what it needs, from the plan's `data_visuals` and both analyses'
   `assets` (one the code analysis can produce, `obtain: from-code`, replaces the draft analysis' `user` guess).
2. Source order: **a demo image already in the repository** (README figures excluded — they may be the paper's own
   figure) > **one sample of the public dataset the paper uses**, downloaded only if its licence allows reuse (CC0,
   CC BY, CC BY-SA, public domain, MIT/Apache; record `url` + `licence` in the plan) > running the project's code when
   it is light (no training, no weights, no large downloads) > asking the user > a data-thumbnail `glyph`
   (`pointcloud`, `waveform`, `spectrogram`, `trajectory`, `molecule`, `plot`; `"illustrative": true`, and the
   caption says "schematic") where the data has one > an image-shaped placeholder. A real sample always beats a
   thumbnail: the thumbnail only shows what kind of data flows, never what this paper's data looks like.
   Copy obtained files into `RUN/assets/`, set `asset.status` (`from-code` / `provided`) and `asset.path`, and the
   plan entry's `source`/`path`.
3. **Never** generate an image that stands in for a result, an input sample or a plot. The one exception is a
   **concept illustration** of a scene, actor or environment the method works in or with **and that the paper or
   code describes as visual** (a robot arm over a tabletop, a road scene from the ego car, a rendered 3-D simulator)
   when a reader grasps it faster as a picture than as an icon. The scene comes from the source, never from you:
   `asset: {"status": "generated", "spec": "<only what the quote states>", "grounds": {"ref", "quote"}}` and
   `"illustrative": true`, then `$PAPERFIG illustrate RUN/blueprint.json --style S --out RUN/assets --text
   RUN/inputs/method.txt [--repo CODE]` — it refuses a quote the source does not contain, and `run check` repeats
   that. A text, API, unit-test or database environment (a text game, Wikipedia search, a code executor) is never
   illustrated: name it on an icon or a text card (a kitchen drawn for a text-game agent is invented — user,
   2026-11-14). `--dry-run` shows the prompts first. The render mode, the figure's palette, a white background and "no text" travel inside the
   prompt; look at every picture before using it, give it room (a scene the size of an icon adds nothing), and say
   in the caption that it is an illustration. Record each in the plan's `annotate` list. **auto:** allowed for
   scene/actor elements only, never in a benchmark run.
4. Tell the user promptly what is missing — what, where in the figure, suggested size — and continue with
   placeholders (`status: requested`, a `spec`). Options: *I'll provide them (paths)* / *continue with placeholders*.
   **auto:** never run the project's code; repo files and one licensed public-dataset sample are allowed; otherwise
   placeholders, listed in the decision.
   Then revise the blueprint's layout if the brief or the assets call for it (content unchanged), validate and
   rebuild r0.

## ⑥ Style → **confirmation point `style`**
Style is open — the shipped recipes are starting points, not limits; a research figure should also be beautiful.
1. Derive a candidate from the references' measured colours:
   `$PAPERFIG style derive --base B --from-cards RUN/refs/cards [--cards ID,…] --out RUN/style.json` with `B` the
   recipe whose shapes and depth best match the brief (`soft-pastel` flat rounded, `depth-cv` 3-D blocks and shadow,
   `editorial-minimal` thin outlines) — derive replaces only the colours
   (`--cards` = the adapted reference alone when its look is the one to follow). You may also hand-edit a copy of
   any recipe into `RUN/style.json` when the brief calls for a look none of them has; every path that takes a style
   name also takes such a file. Tones keep their semantic names, so nodes with an explicit `tone` keep their meaning.
2. `$PAPERFIG samples RUN/blueprint.json --styles RUN/style.json,A,B --facts RUN/facts.json --out RUN/samples`
   renders the user's own blueprint in 2–4 styles (recipes: `soft-pastel`, `depth-cv`, `editorial-minimal`;
   `drawio-default` only as a contrast) and writes `samples.png`. Samples with lint errors are never shown — the
   command lists them with the reason.
3. Show `samples.png`; options = the shown styles (the brief's favourite first) + *mix*. Recipes combine by section
   (`typography`, `spacing`, `palette`, `shape`, `effects`, `tensor`, `edges`, `image`): for a mix, render it first with
   `samples --styles BASE --mix SECTION=STYLE … --out RUN/samples/mix` and show it before recording.
   **auto:** look at `samples.png` and pick the one that best serves the Brief (contribution salient, data
   readable, colours meaningful) — the derived style when it is at least as good, since its colours come from the
   references; why = what you saw and the cards behind it. Never pick a style unseen.

## ⑦ Build, lint, one critique, one fix build
A critic round costs a fresh subagent; the user's eye is the faster and more decisive review (user, 2026-11-13:
fewer critic rounds). So: **round 1** = build + lint + one critic; **round 2** (only if that critic reports
`high`/`medium` issues) = apply them, rebuild, lint, look — no second critic; then deliver and let the user review.
Run another critic only when the user asks for one.
For round 1 (and the fix build, round 2):
1. `$PAPERFIG build RUN/blueprint.json --style S [--mix SECTION=STYLE …] --facts RUN/facts.json --out RUN/build/rN --name fig`
   → `fig.drawio`, `fig.png` (300 dpi at the print width), `fig.pdf` (vector, page = print width, fonts embedded),
   `fig.lint.md`, `fig.lint.json`; add `--formats png,pdf,svg` when the Brief's `export` asks for SVG.
2. **Open `fig.png` yourself.** Read `fig.lint.md`; fix every error and every warning you can with the table in
   `references/design.md`, rebuilding until the exit code is 0 (lint errors block delivery). A `split-suggested`
   `min-font` below the floor, in order of cost: shorten labels → `--mix spacing=compact` (tighter gaps and
   padding; at any width) → `--mix spacing=compact --mix typography=compact` (body-size small text) → fewer
   top-level units per row; a `split-suggested`
   warning (overview + detail panels below 7 pt) is the user's call — one figure or two: show them its numbers and
   the options *split into overview + module figure* / *keep one figure, regroup* (`references/blueprint.md`
   "Overview + detail"); **auto:** keep one figure unless the overview alone reaches 7 pt, and say so in the report.
3. Round 1 only — dispatch **critic** (`agents/critic.md`) with `PNG=RUN/build/rN/fig.png`, `METHOD_TEXT`, `FACTS`, `BLUEPRINT`,
   `PLAN=RUN/figure_plan.json`, `EQUATIONS` = `equations` of `RUN/analysis.draft.json`, `MODEL` (when one is adapted) = the crop of the
   reference the chosen concept adapts,
   `LINT=RUN/build/rN/fig.lint.md` and `PRINT_WIDTH_IN` = `print_width_in` from that lint report (no other crops —
   its criteria do not use them). It must not see your reasoning. Its JSON must carry the reader test (`reader`, with the three
   `levels` and `caption_free` for a v2 Brief), or `run round` refuses it. Save its JSON to `RUN/critic/rN.json`, then
   `$PAPERFIG run round RUN --n N --lint RUN/build/rN/fig.lint.json --critic RUN/critic/rN.json --note "what changed"`.
4. Stop when lint is clean and the critic reports no `high`/`medium` issue. Otherwise apply every `high` and
   `medium` issue as a blueprint or style change, build `RUN/build/r2`, fix its lint, **open its PNG and check each
   applied issue yourself**, and record it as the fix build:
   `$PAPERFIG run round RUN --n 2 --lint RUN/build/r2/fig.lint.json --critic-of 1 --note "applied: i1, i2; open: i3 (why)"` — every high/medium issue id appears (checked).
   If the critic's reading differs from the plan's, fix the picture (emphasis, order, data visuals), not the plan. An `io_audit` omission backed by a quote from the
   method text and **not** in the plan's `omitted` is a faithfulness correction: add the node/edge and its fact —
   a new component also goes into `analysis.draft.json` with its verbatim quote (the facts validator checks ids
   against it); re-validate both — and list it in the report. One in `omitted`/`omitted_details` stays out unless the
   critic shows its absence misleads: the plan, not the analyst's depth rule or the critic, decides the depth.
   A style fix (e.g. `--mix edges=…`) is recorded with another `run decide --point style`. Remove approved
   content only with the user. `low` issues and anything you could not apply go into the report as open; the user
   decides at delivery whether another round (with a critic) is worth it.

## ⑧ Deliver → **confirmation point `delivery`**
1. `OUT` = the folder the user named; otherwise ask once (default: a `figures/<SLUG>/` folder next to the draft).
   **auto:** `RUN/deliver/`.
2. Before/after sheet: `$PAPERFIG contact --panel "Round 1=RUN/build/r1/fig.png" --panel "Final=RUN/build/rN/fig.png"
   --out RUN/compare.png` (add the user's previous figure as the first panel when they gave one).
3. Write `RUN/report.md` with exactly these sections: `## Figure` (what it shows; proposed modules and their names;
   discrepancies and decisions; the takeaway and the chosen concept with the reference it adapts), `## Omitted`
   (each planned-omitted fact and detail, its reason and where the reader finds it; the `drawn_as` mappings),
   `## References` (title, venue, link, what
   was learnt from each), `## Rounds` (lint counts, critic scores and the critic's takeaway per round; what
   changed), `## Open issues`, `## Placeholders` (what, where, spec — or "none"; dataset samples with url and
   licence), `## Caption draft` (v2 Brief: one paragraph the author can adapt — what the figure shows, the codes a
   reader cannot infer (dashed = training only, the highlight colour), "schematic" for illustrative glyphs, the
   sources of sample images/text; only names and numbers the method text states). The figure must stay readable
   without it — the caption supplements, it does not explain the main flow. End with how to edit (open the
   `.drawio` in draw.io; the rebuild command).
4. `$PAPERFIG kb harvest RUN` keeps this run's new cards in the user layer (dedupes; the next paper reuses them
   instead of paying for them again). Benchmark runners skip it — the orchestrator harvests after the run.
   `$PAPERFIG run deliver RUN --out OUT` copies the last round's files, `report.md` and `compare.png`; then
   `$PAPERFIG run check RUN` must print `ok` (artifacts, quotes, decisions so far, final round lint-clean and reviewed).
5. Show `compare.png` and the open items. Options: *accept* / *revise* (→ ③, ④, ⑥ or ⑦ with their notes). A user
   revision is one more build round, recorded with `run round RUN --n N --lint … --by-user --note "<what the user
   asked>"` (a critic only if the user asks), then deliver again. If the user edited the delivered `.drawio` by hand
   (moved boxes, retyped labels), first `$PAPERFIG absorb RUN/blueprint.json EDITED.drawio --style S` so the rebuild
   keeps those edits, and tell them what it could not absorb. Record the
   decision, then `$PAPERFIG run check RUN --final` must print `ok` before you call the figure done.
   **auto:** accept and record.

## Rules that bind every run
- Faithfulness beats looks: nothing is drawn without provenance. A fact is left out only through the plan's
  `omitted` list (reason + where the reader finds it), shown to the user — never silently to make a layout fit.
- Reader first: the figure delivers the plan's takeaway at a glance; each paper gets its own design — adapted from
  a reference that fits, or built from the material and the venue's conventions — never one house style.
- Beautiful, not only correct: a research figure is also judged by its look. Style is open (⑥): the recipes are
  starting points, not limits.
- Never generate images that pose as results, samples or plots; placeholders stay visibly marked until replaced.
- Reference PDFs and crops stay in `~/.cache/paper-figure/`; never copy them into deliverables or the skill.
- Paid services (paid Monid runs, keyed APIs) need the user's permission first; the free search and fetch suffice.
- Report what happened: if a check failed or a step was skipped, the report says so.

## Knowledge-base build (maintainers only)
When the user asks to build or extend the shipped knowledge base, read `references/build-kb.md`; its output must
pass `$PAPERFIG kb validate`.
