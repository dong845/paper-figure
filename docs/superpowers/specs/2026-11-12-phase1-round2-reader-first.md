# paper-figure — phase 1 round 2: reader-first, flexible figures

## Why (user verdict on the phase-1 baseline, 2026-11-12)
- Style is monotonous: every figure is "containers + boxes + bottom legend", although the reference figures show many
  different, learnable styles.
- Figures try to cover every detail, so they are crowded, hard to grasp and badly routed (Decision Transformer,
  ControlNet). Some originals are simple on purpose.
- Data is missing: no input/output images (TransUNet, RAG), no 3-D intermediate feature maps.
- Goal: from the reader's side, a figure that shows the whole method at a glance and highlights the contribution
  enough to help with the details when needed. Flexible design learned from the examples, not a fixed style.

## Decisions (user, 2026-11-12)
- Pilot on **Decision Transformer + TransUNet** first; show the user before rolling out to the other papers.
- Detail trade-off: the figure draws the main line and the contribution; **omitted details are listed (with their
  quotes) at the blueprint gate for the user to confirm**; the faithfulness check covers what is drawn.
- Example images: **code-repository demo images, else one sample of a public dataset (source + licence recorded)**,
  else an image-shaped placeholder. Never generated images for inputs or results.

## What changes
1. **Figure plan before the blueprint** (`RUN/figure_plan.json`, validated by `paperfig validate figure-plan`):
   - `takeaway` — the one sentence a reader should get in 10 seconds;
   - `concepts` — 2–3 candidate figure concepts, each adapted from a named reference card (e.g. *token row under a
     causal transformer*, *U-shape with feature-map stacks and input/output images*), and the `chosen` one with why;
   - `core` — the top-level visual units of the main line (warning above 8), `highlight` — how the contribution is
     shown (expanded panel, colour, name), `data_visuals` — how inputs, outputs and intermediates are depicted
     (image / feature-map stack / token row / text example) and where each image comes from;
   - `omitted` — every fact not drawn, with a reason and where the reader finds it (text, detail panel, other figure).
2. **Facts gate checks the plan, not the whole paper**: facts listed in `omitted` become `fact-omitted` info (shown in
   the report and at the blueprint gate); any other unmet fact is still an error. A fact may be omitted only by the plan.
3. **Per-paper references come before the plan, every time** (never skipped for budget): the scout searches for the
   papers *most similar to this method* — same task **and** similar structure or mechanism (e.g. for Decision
   Transformer: trajectory/sequence models for RL, not RL papers in general) — and the card writers describe how
   those figures are composed. The design brief (these cards + domain conventions) must exist before step ③, and each
   plan concept must name the reference figure it adapts and what it takes from it (layout, data depiction, emphasis).
   At the gate the user sees the references, the concepts and the omitted list.
4. **Data visuals by default**: inputs/outputs/intermediates are drawn as what they are (images, feature-map stacks,
   token rows, text examples). Images: repo demos → public-dataset sample (licence) → image-shaped placeholder.
   Placeholders look like an image frame with a short label; their long spec goes to the report, not the figure.
5. **Engine changes the pilots need**: legend placed in the largest empty area when it fits; ports spread when
   several edges meet one side; short dashed edges stay dashed; min-font judges each text run, not a whole label with a
   subscript; edges may enter a titled group past its title text; `run round` stores absolute paths.
6. **Critic reads as a reader**: states the takeaway it got from the PNG, counts top-level units, flags clutter
   (crossings, bends, parallel lines) and compares against the chosen model card; "draw more" findings must respect
   the plan's `omitted` list.
7. **Blind gap closed**: the scout rejects reference figures that redraw the paper being drawn.

## Acceptance (pilot)
For Decision Transformer and TransUNet, a new blind run each; sheet *original | phase-1 baseline | round 2* on
`~/Desktop/paper-figure-phase1-r2/`. The user judges: graspable at a glance, contribution highlighted, data shown,
clean lines, not the one fixed style. Only then roll out to the other six papers.

## Not now
Graph-node visuals (GAT), alternative-path notation, multi-concept sample renders per run — after the pilot verdict.
