# paper-figure — round 3: the user's figure-design guide

## Why
The user supplied *AI 科研论文高质量结构图设计指南* (copy: `.superpowers/sources/figure-design-guide.md`, git-ignored)
and chose all four improvement groups from my comparison (2026-11-13). Round 2 made figures reader-first but tested
only the 5-second level; the DT pilot swung to hiding the mechanism, my "loops out of the main drawing" rule
over-corrected the guide's train/infer distinction, and several components and checks the guide names are missing.

## Decisions (user, 2026-11-13)
- Do all four groups below; then rerun GAT, PointNet and Latent Diffusion (paused) with the new skill.
- Unchanged: provenance and facts gate, no generated images, references before the plan, ≤ 3 build rounds.

## What changes
1. **Brief with three reading levels** (guide §1–3, appendix). `figure_plan.json` v2 adds: `problem` (the bottleneck the
   paper addresses), `io` (inputs, outputs), `contributions` (≤ 3: name, `solves`, `shown_by`, ids), `mechanism`
   (≤ 2 zoom-ins: panel id, what it explains, equation ids), `train_only` / `infer_kept` ids, `key_representations`
   (name, ids, one visual + tone), `color_semantics` (tone → meaning), `annotate` (shapes/scales to label), `export`.
   The blueprint gate shows the brief. Critic reader test = three levels: 5 s takeaway, 30 s what is new and why,
   2 min how the key mechanism works; plus "is the main flow readable without the caption".
2. **Training vs inference** (guide §1.2, 2.2, 6.4): replace "loops out of the main drawing" with: training-only
   parts stay *visible and marked* (dashed, light, "training only") when they explain the method; remove only
   loop wiring that wraps around the figure. A training-only input (e.g. a GT mask) must never look like an
   inference input.
3. **Visual grammar lint** (guide §4, 6.3): (a) a key representation keeps one visual and tone everywhere;
   (b) every tone used is declared in `color_semantics`, one meaning per tone; (c) the proposed highlight survives
   grayscale (lightness contrast or a non-colour cue: stroke weight/bold); (d) zoom-ins are ≤ 2, each a panel with
   `detail_of` (the existing callout lint then enforces the visible link).
4. **Component library** (guide §9.1): new glyph visuals — graph (nodes/edges), database, prototype, schematic
   heatmap, segmentation mask, k-space with sampling mask. Schematic glyphs that could pass for results (heatmap,
   mask) carry an "illustrative" marker; lint flags an unmarked one.
5. **Formula as a source** (guide §5): the draft analysis records the contribution's key equations verbatim
   (`equations`, quote-checked); mechanism panels cite them; the critic checks the panel against them.
6. **Caption and export** (guide §7.1, 8): report gains `## Caption draft` (no invented numbers); PDF is scaled to
   the print width (fonts stay embedded); SVG is offered.

## Acceptance
Unit tests per change; restormer/blip2/round-2 corpus lint unchanged unless a new rule fires (then judged); three
blind reruns (GAT, PointNet, LDM) with sheets *original | phase-1 | round 3* on `~/Desktop/paper-figure-phase1-r2/`.
