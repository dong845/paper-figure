# Design guide — reader first, layout patterns, emphasis, and what each lint finding means

Read this when you write the figure plan and the blueprint (steps ③–④) and every time a lint report has findings
(step ⑦).

## Reader first (why the figure exists)
A method figure lets a reader grasp the whole method in ~10 seconds and find the contribution when they want the
details. It is not a wiring diagram of the code. Users rejected exhaustive figures — every stated connection drawn,
every sub-block boxed — as crowded, hard to follow and "AI-looking".
- **Draw the main line and the contribution.** Everything else is listed in the plan's `omitted` with where the
  reader finds it (text, caption, a detail panel, another figure). Auxiliary losses, ablation-only paths,
  hyper-parameters and repeated blocks are the usual candidates. Never omit what the takeaway depends on.
- **≤ 8 top-level units** on the main line (collapse repeated blocks into one with `×N`; group a stage into one box).
  How far each proposed module opens is the plan's `depth` (§ How deep the overview goes); reused parts stay
  collapsed.
- **Show data as data.** Inputs, outputs and intermediates are what the paper's readers recognise: images
  (`image`), feature maps (`tensor` / `stack`, sized to suggest resolution and channels), token rows (`tokens`), a
  short text example (`text`). A pipeline of boxes with no data in it is the template look.
- **Three reading levels** (the user's guide): in ~5 s a reader gets the input, the output and the main flow; in
  ~30 s what is new and which problem it solves; in ~2 min how the key mechanism works. Draw for all three — the
  global line collapsed, the contribution salient, and one or two zoom-ins (`detail_of` panels) for the mechanism.
  Simplicity that hides the mechanism fails the 2-minute level as surely as clutter fails the 5-second one.
- **Training vs inference must be visible, not removed.** Training-only parts (a loss, a GT mask, a teacher, an
  auxiliary head) stay in the figure when they explain the method, drawn as training-only: `train_only` edges
  (dashed), a light fill, a "training only" label. A training-only input must never look like an inference input.
  What goes is the *wiring* of procedural loops (a rollout or optimisation loop drawn as lines wrapping around the
  figure): show the loop as one short labelled return arrow, a small side panel, or the caption.
- **Name every unit a reader must recognise.** A run of feature maps, a stack of layers or a stage the paper names
  (e.g. *CNN (ResNet-50)*, *Transformer encoder*) carries that name next to it; an unlabelled group of shapes makes
  the reader guess.
- **Pass-through labels belong on the edge.** A per-token embedding (`E`), a head (`P_a`) or an operation on one
  arrow is the edge's `label`, not a separate node; separate narrow nodes add a stop on every line.
- **Follow the chosen model figure's composition** (the reference the plan's concept adapts): where the input
  enters, how the stages are arranged, how the contribution is set apart, how much text there is. Take its
  structure, not its colours or wording.

## The overview, step by step (how a designer composes it)
An overview is one level of abstraction: every unit on it is something the reader names in one breath ("the
encoder", "the fusion module"), and what is inside a unit is shown somewhere else or not at all. Compose it in this
order; each step names the section that works it out.
1. **Spine.** The main line runs left → right at one height: inputs at the left edge as data, outputs at the right
   edge, ≤ 8 units on it (Width and aspect). A longer line becomes two bands, each left → right, handed over by one
   `wide` arrow — never a snake or a tower.
2. **Where the contribution sits.** On the spine, near the middle, and the largest or most saturated unit there
   (`derive.md` principle 4). A reused backbone around it is compact and muted.
3. **How deep each proposed module opens** — one decision per module (§ How deep the overview goes, below).
4. **Side inputs** (conditions, queries, a target branch, training signals) enter the spine from above or below,
   perpendicular to it, at the unit that uses them.
5. **Zoom-ins** sit in one band under the spine, side by side in the text's order, or beside the spine in the empty
   quadrant nearest their source — never stacked into a tower, never two levels deep.
6. **Space and colour** last: gaps that nest, no blank region (§ Space), and a hue hierarchy inside every module
   (§ Colour inside a module). The key goes at an edge.

## How deep the overview goes (one decision per proposed module)
The authors' new modules are why the figure exists, but drawing every one of them fully in the overview is how
figures get crowded: an attention module is a part of a block, the block is a part of the network, and all three
levels at once leave no level readable. So the plan's `depth` gives every outermost proposed module one of four
levels — every proposed module the analysis gives parts to, at every level (validator: required in an overview /
teaser; the blueprint must draw what it says):

| `as` | when | how it is drawn |
|---|---|---|
| `inline` | it *is* a step of the main line and has ≤ 3 parts (`inner_parts` in the analysis) — e.g. a two-branch fusion | its parts on the spine inside its own tinted frame; nothing else opens it |
| `box` | the reader needs what it does, not how (it is not the 2-minute mechanism), or the paper already has a figure of it (`existing_figures`) | one named box (`full_name` / `abbrev`) with one line under the name from the analysis' `details` ("channel attention · linear cost"); the internals stay in the text |
| `inset` | it is the mechanism the 2-minute reader needs, with up to about 8 parts — at most two insets per figure | a named box on the spine + one `detail_of` panel in this figure (below) |
| `own-figure` | more than about 8 parts, or the text gives it a subsection with its own equations, or a third mechanism, or an inset would push the text under the floor, or it holds a proposed module of its own that also needs opening | a named box reading "(Fig. N)" + a module figure of its own, made by the build (`paperfig split`), numbered as the paper will number it (`figure`) and drawn for the subsection it accompanies (`section`) |

- **Siblings get the same depth.** Two new modules at the same level — the two halves of one block, MDTA and
  GDFN — are both opened in this figure or both given figures of their own; one inset beside one split-off figure
  has no logic a reader can follow (validator). When they do not fit as insets, both go. When only one of the
  siblings is the authors' (the other a standard layer), only that one is opened — a standard part's internals
  are not drawn beside the new one's (validator).
- **One zoom level per figure** (lint `zoom-nested`). Overview → panel is read; overview → panel → panel is
  lost. A proposed module inside another (an attention inside a Transformer block) is opened once, from the box on
  the spine. Restormer's authors (card restormer-2021-fig2) open one of the U's Transformer Blocks in place — its
  two new parts, MDTA and GDFN, as two small boxes inside that block — and zoom each into panel (a) / (b), tinted
  in that box's own colour: the block is `inline`, its parts are `inset`, and there is still one zoom level. Not a
  separate "Transformer Block" panel with panels of its own, and not a panel floating with no line to the
  overview. When the inner module needs more room, it gets its own figure.
- **The inset is tied to its box three ways:** the callout cone from the box (engine), the box's hue on the panel's
  border and title, and the same name — titled as the paper names it, "(a) Multi-Dconv Head Transposed Attention
  (MDTA)". Its first and last element take the box's input and output (an `X` in, `X̂` out), so the reader matches
  the arrows. Panels side by side share their height (engine); order them as the text describes them.
- **The box at the overview level carries a name and a job, not its parts:** `<b>MDTA</b><br><small>attention across
  channels</small>`. A bare abbreviation makes the reader look it up; three lines of internals turn the box into
  a panel nobody asked for.
- **Own figures follow the text.** A module figure is the module-detail figure of the subsection that introduces
  the module: the same tones as the overview (the reader recognises it), its operators and tensor names as
  `module-detail` asks (SKILL.md ④). The build makes it beside the overview (`fig-<panel>.*`) whenever the plan
  says `own-figure`; the report says which section each figure belongs to.
- **Moving detail is not dropping it.** What leaves the overview is drawn in the inset or the module figure, so
  depth is not the "merge to save space" that `layout.md` § 0 forbids; what § 0 forbids still holds at every
  depth — encoders are not merged, method-defining losses not collapsed, inputs not dropped.

## From contribution to composition (how published figures express each kind of idea)
First derive the structure (`references/derive.md`: relations → forms); this table is the evidence of how published
figures drew particular relations, for calibrating a derived design — not where a design starts. Pick the technique
for what the paper contributes — the Brief's `contributions[].shown_by` names it. Each row cites knowledge-base cards
that do it (`kb query` shows their full `lesson`); combine techniques when a paper has several contributions, and
derive one from the principles when none fits — these are patterns that work, not a menu to obey.
| contribution | technique | evidence |
|---|---|---|
| a new space or representation (latent, discrete codes, tokens) | draw the representation as data and give it one motif and colour everywhere it travels; spaces as regions | vqgan-2020-fig2, vq-diffusion-2022-fig1, knn-lm-2020-fig1 |
| a new module inside a known backbone | backbone collapsed and muted; the module on its own tint, expanded once in a detail panel tied by matching tint | transbts-2021-fig1, dpt-2021-fig1, pointmlp-2022-fig2, t2i-adapter-2023-fig3 |
| a new conditioning / control path | the added signal enters from the side on its own bus at every block it feeds, in its own colour | ip-adapter-2023-fig2, gligen-2023-fig3 |
| a trainable copy / frozen base | trainable vs frozen encoded twice (fill + flame/snowflake or a margin note) | gligen-2023-fig3, best-rq-2022-fig1, emdr2-2021-fig1 |
| sequence modelling | one token row under one wide model bar, the predicted row above, shifted one slot | trajectory-transformer-2021-fig1, vima-2023-fig3 |
| retrieval / memory | the store, the top-k items as data in their own colour, and how they merge | retro-2021-fig2, replug-2023-fig2, murag-2022-fig4 |
| contrastive / multi-positive pretraining (CLIP family) | image tower and text tower facing each other, one similarity matrix per objective between them showing which pairs are positive (diagonal, shared column, shared sets); real image samples and real quoted sentences at the inputs; fills by modality, the contribution ringed | CLIP (Radford et al. 2021, fig. 1); the user's own paper figure (comparison 2026-11-15) |
| multi-stage training or a cascade | one full-width band per stage; a reused module keeps shape and fill in every band | wuerstchen-2024-fig3, muse-2023-fig3, realm-2020-fig2 |
| a training signal or target branch | the target generator as a separate side branch in its own colour family, dashed | hubert-2021-fig1, audioldm-2023-fig1 |
| typed entities (node types, modalities) | one colour per type, repeated on everything that belongs to it | hgt-2020-fig2, retro-2021-fig2 |
| multi-scale encoder–decoder | U laid sideways or as columns with scale labels on the skips, mirrored sizes in the margins | unetr-2022-fig2, swin-unet-2021-fig1, pointnet-plus-plus-2017-fig2 |
| an unrolled / physics-guided reconstruction (data consistency) | draw it compact first, then unrolled (first, a middle, last iteration with ellipses); the measured data as one bus under the cascade tapping every DC step; FT/IFT on the arrows between real image and k-space stacks (`kspace` glyph when no real data) | modl-2017-fig1, cascade-cnn-2017-fig4, e2e-varnet-2020-fig1, dudornet-2020-fig1 |
| dual-domain processing (k-space + image) | colour names the domain, and every feed line takes the colour of the domain it enters | dudornet-2020-fig1, e2e-varnet-2020-fig1 |
| a world model / recurrent latent model (RL, video) | unroll 2–3 time steps as columns of the same unit (h over z), the categorical latent as a `onehot` glyph, the action as an icon (`joystick`, `hand`…) with a_t, the observation as an image + `vector` pair, prediction heads as small coloured arrows out of each step; imagination continues the row without encoders | iris-2022-fig1, muzero-2019-fig1; written after the user compared the DreamerV3 original (arXiv 2301.04104 — a blind rerun of it is not fully blind here) |
| window / patch attention (vision transformers) | the image as a `patches` glyph, regular and `shifted` windows side by side in the block detail | swinmr-2022-fig1; written after the Swin run (arXiv 2103.14030 — not fully blind for it) |
| an agent loop (reason → act → observe) | the environment as its own box, action and feedback on two labelled paths (`tone` per path); a 2-row `grid` loop (top row out, bottom row back; `cycle` with the LLM as `hub` only when the loop is the whole panel — a ring is square); worked steps as `textcard`s in call syntax; agents as icons (`bot`, `user`), tools as icons (`wrench`, `search`, `terminal`) | reflexion-2023-fig2, swe-agent-2024-fig1, react-2023-fig1, voyager-2023-fig2 |
| self-reflection / memory for agents | a second loop that writes back into the agent's memory, the store drawn differently from operations (`documents` glyph for text memory, `database` for an index) | generative-agents-2023-fig5, reflexion-2023-fig2, self-refine-2023-fig1 |
| multi-agent conversation | one colour per role carried from its icon to every message bubble (`textcard` bubble with the role's `tone`); a double-headed link between conversing agents | camel-2023-fig1, autogen-2023-fig2, metagpt-2023-fig2 |
| a training / alignment pipeline (SFT → RM → RL) | stages as headed columns, data and steps in different shapes, one short real example per stage; the RL loop curved or dashed, one-pass steps straight | llama-2-2023-fig4, self-instruct-2023-fig2, dpo-2023-fig1 |
| mixture of experts / routing | a row of identical numbered experts, the router below with its score bars, the chosen experts outlined | switch-transformer-2022-fig2, deepseekmoe-2024-fig2 |
| a cheaper or simpler alternative (teaser) | prior method and ours side by side in one vocabulary, ours last; what is removed or shared made visible by colour or size | dpo-2023-fig1, qlora-2023-fig1, prefix-tuning-2021-fig1 |
| set prediction / object queries | one colour per query carried to its predicted box on the photo; empty slots shown | detr-2020-fig2, maskformer-2021-fig1 |
| promptable / open-vocabulary perception | the prompt written out at the input (words, points, boxes drawn literally); text×region score grid | sam-2023-fig1, owl-vit-2022-fig1, glip-2021-fig2 |
| a design choice among variants | the chosen variant in full colour, the rejected ones at the same size faded | dit-2022-fig3 |

## Edge economy (every arrow must earn its place)
Messy figures are mostly too many arrows. Before adding one, ask what the reader learns from it.
- An overview shows the data path and its representations; the objective is said once. Draw the prediction
  outputs (x̂, r̂, ĉ …) where they leave the model and let them stand for their losses; keep a loss box only for a
  loss that is a contribution (in the plan's `contributions`), and put training details (free bits, return
  normalisation, EMA targets) in labels or the caption (lint `loss-heavy`; the STORM and DreamerV3 blind runs drew
  5 and 3 loss boxes with 9 and 8 loss arrows where the authors drew none — arXiv 2310.09615, 2301.04104: not fully
  blind for them).
- A recurrent or sequential method (world model, RNN, video model, an agent over steps) is unrolled over 2–3 steps
  in the overview — one column per step, the same unit repeated — rather than drawn as one cell with a loop.
- One flow, one arrow: two arrows between the same pair become one labelled arrow (lint `edges-parallel`).
- No wrap-arounds: an arrow longer than about twice the straight distance (lint `edge-detour`) means the order is
  wrong — reorder siblings, move a node, or show the loop as one short labelled return arrow; a feedback loop that
  *is* the method gets a `cycle` layout instead.
- Fan-in and fan-out through one bus (`bundle` on the edges) or one labelled bundle, not N separate lines (cards: cascade-cnn-2017-fig4,
  ip-adapter-2023-fig2).
- Training vs inference: draw one path solid; mark the other with its kind once, not by duplicating the pipeline.
- Between panels, refer — don't wire. A module that a later stage uses is named by its `marker` letter there (a
  table row led by disc C), not by a line across the figure; keep the cross-panel lines to the trunk (input →
  model, a stage → the next; a stage handing its result to the next panel is one `wide` arrow across the gap
  between them, not thin wires). Two siblings that both feed one box are framed together (`frame: "dashed"`) and one
  line leaves the frame. Arrows are thin, neutral and few; colour on a line means something (Nature Methods,
  Points of View "Arrows", 2011: arrowheads for direction or sequence only). VERA (arXiv 2611.22815, Fig. 2) draws
  five panels with almost no line between them.

## Panel figures (the VERA look; style `friendly`)
- The panel carries the hue (pale fill, thin stroke, a large title in its colour, a letter disc); the boxes inside
  are white with a light edge and dark text. Give a box a `tone` only to stress it (the output a stage hands on).
- Type in three steps: panel titles clearly larger, box names bold, the line under a name regular — at the same
  size, because the smallest text sets the print floor (5.5 pt for a full-width overview).
- Fill a panel with the method, not with air: a tool is a tile (`icon` + `icon_at: "top"`), a data image gets the
  size the picture deserves (two rows when a row is full), a short phrase under a name says what it does. Siblings
  stack where width is short and height is free (the tallest panel sets the band's height anyway).
- One line of math under a block's name is fine (its update rule); a second line, or a formula standing alone in a
  box, is not (lint `formula-in-block`). A yes/no step is a `decision` diamond or a box with labelled exits.

## Choosing the composition by looking
Text concepts hide what a layout will look like. Before the blueprint, write each concept as a skeleton (top-level
units and main edges only, no provenance) and render them side by side:
`$PAPERFIG sketch RUN/concepts/c1.json RUN/concepts/c2.json --out RUN/concepts` → `sketches.png` with each one's
w/h. Choose the one that reads fastest and is wide enough; keep the others' lessons for the details.

**The concepts differ in form, not only in layout** (the user: "放开思路，不要套模版"). Judge them by what a
reader understands in 30 s, how clearly the contribution stands out, and how it looks — not by how many components
they list. Forms to weigh:
- **on the data itself** — when the method acts on a structure (a graph, a point cloud, image patches, a sequence,
  k-space), draw the operation on a small instance of it: GraphSAGE's own figure samples a node's neighbours on a
  toy graph, aggregates them, then predicts — far more explanatory than a block pipeline of the same steps (the
  blind run drew the pipeline; the user preferred the original). Use `graph`, `pointcloud`, `patches`, `kspace`,
  `mr-image` glyphs, and draw the toy instance's nodes and edges as the figure's own elements when they carry the
  explanation (the sampled neighbours highlighted, the aggregation arrows in the accent colour);
- **pipeline** — when the story is a sequence of transformations between modules;
- **before / after or ours / theirs** — when the contribution is a change to an existing scheme;
- **a mix** — a small on-the-data panel beside a compact pipeline.
At least one concept takes the on-the-data form whenever the input is such a structure.

**Show data as data.** Inputs, outputs and auxiliary data (images, masks, coil maps, k-space, graphs) are pictures,
not boxes with a name: a licensed real sample, else a procedural glyph marked `illustrative` (`mr-image` with
`variant: "aliased"` for an undersampled input, `sampling-mask`, `coil-maps`, `kspace`, `pointcloud`, …); a
placeholder only when no glyph fits (VS-Net blind run: input, mask and coil maps as placeholder boxes).

**Symbols only where they help.** Label an edge with a variable (m^k, u^{k+1}, x_i) only when the caption or the
text relies on that name, or when two flows would otherwise be confused; an unrolled method's intermediate
variables on every arrow read as clutter (user on VS-Net). Lint info `symbol-heavy` counts them.

**Losses only when they are the point — and the supervision structure always is.** A conventional loss *term*
(MSE, L1, cross-entropy, a standard KL, a reconstruction term) is said in the caption, not drawn. Draw a loss when it
is new or part of the contribution (list it in the plan's `contributions`); then give it its own visual weight. But
separate the loss *formula* from the *supervision structure*: when the method trains with two or more contrastive or
matching objectives, **what is a positive for each** (each image with its own caption 1:1, images sharing a class
sentence N:1, images sharing concept sentences N:M) is the method itself, even when every term is a standard InfoNCE.
Draw it the way the paradigm's source figure does — CLIP's image × text similarity matrix, one `pair-matrix` glyph
per objective (`variant` one-to-one / many-to-one / many-to-many, rows in the image tone, `col_tone` the text tone)
with the objective's name and its pairing ("image ↔ label · N:1") under it — and list the ids in the plan's
`supervision` (validator: required with ≥ 2 contrastive objectives in the analysis). *Why:* on the user's own contrastive-pretraining paper the blind run
put the four objectives in the caption as "routine"; the author drew four matrices, and the reader sees that the
supervision goes beyond one caption per image — the paper's claim — in one glance. Lint `loss-conventional` names drawn losses that are
neither contributions, supervision, nor a stream's own losses (plan `layout.units[].losses`). Each stream the text
trains shows its **method-defining** losses (contrastive / matching, new, supervision) in its own unit, each as its
own element (`references/layout.md` § 2); conventional objectives (reconstruction, KL, actor-critic) may stay in the
caption.

**Borrow the paradigm's picture of the mechanism.** The scout selects the source figure of the method family
(`role: "paradigm"` — CLIP, U-Net, Transformer, DDPM …) and one concept adapts it (validator). Take its depiction of
the core mechanism (CLIP's matrix, the Transformer's stacked encoder/decoder columns, U-Net's U); take layout
details from the neighbours. Readers decode the source figure's vocabulary instantly.

**A module with a figure of its own is one box.** When the text shows a module in another figure ("as illustrated
in Fig. 3"), the overview draws it as one named box and leaves the internals there (validator, from the analysis'
`existing_figures`; keep it expanded only with `expanded_despite_figure` and a reason). On the user's
own paper the blind run expanded such a module's three steps into the overview, which pushed the text to 6.2 pt;
the author kept one box.

**Colour by modality in a multi-modal model.** In a two-tower or multi-modal model (image / text, audio / text,
vision / action) the reader's first question is which side a box belongs to, so fills encode the modality —
image-side encoders and embeddings in one tone, text-side in another, a third for a derived representation
(prototypes, patch embeddings) — and the contribution is marked by a ring, not a hue: `figure.highlight: "ring"`
keeps each box's modality fill and draws the proposed parts with a heavy outline in the accent (the caption says what the ring
marks; the key does not). Lay the towers out facing each other (image encoder left, text encoder right, the objectives
between) as CLIP does. The plan states the choice in `color_by` (validator, brief v2).

## Against the "AI look"
| looks generated | looks designed |
|---|---|
| a container (frame) around every group | frames only where grouping carries meaning (a stage, the expanded module); others `frame: "none"` |
| every node the same rounded pastel box | box shapes follow meaning: trapezoids for encoders/decoders, stacks for features, images for data, ops as glyphs |
| every block the same pale/white fill (reads as white) | the guide's colour system: a neutral backbone (reused parts), one strong accent for the contribution, a secondary accent for interaction (attention, conditioning), and one semantic tone per kind of representation (features, prototypes, latents) used everywhere it appears; areas (frames) a lighter tint than the elements inside |
| a different colour for every module | one colour = one meaning (`color_semantics`); top-venue overview figures use ≈4–6 colours with a stated meaning each (lint `palette-busy` above the references' 75th percentile) |
| a tinted backdrop over most of the figure | colour on the parts that carry meaning; a panel that covers most of the figure keeps a coloured border and a near-white fill (the engine does this; lint `ink-heavy` when the figure is inked beyond the references' 75th percentile) |
| a legend band explaining every code | a small legend in empty space, only for codes a reader cannot infer (the engine tries an empty spot, then a right-hand column when the figure is narrower than ≈2.3:1 and the fonts allow, then a band below; `legend: "none"` moves the codes to the caption) |
| long labels inside boxes | 1–3 word labels; names in `full_name`, explanations in the caption |
| many parallel lines and detours | few edges, straight runs; side inputs from above/below; reorder siblings before adding bends |

## Width and aspect (the user: "正常文章的整体结构图应该是扁长的")
Overview and teaser figures are **wide**: the knowledge base's measured overview figures have median w/h ≈ 2.3 and
three in four are wider than ≈ 1.5–1.7 (lint `aspect-tall` reads the live numbers). So:
- an overview spans the full text width (`figure.width: "double"`, a `figure*`) unless the user asks for a column;
- the main line runs horizontally — input left, contribution centre, output right (guide §3.1); a U-shape is laid
  sideways, two stages are two rows side by side, not a column;
- zoom-ins sit beside the main line or in one band under it spanning the width — never stacked into a tower;
- at single-column width only about 4 boxes fit per row at the 7 pt floor: collapse to ≤ 4 top-level units per row
  rather than adding rows, and build with `--mix spacing=compact,typography=compact` (tight gaps, smaller minimum
  boxes, body-size small text). There the goal is "not a tower" (lint `aspect-tall` flags w/h < 0.8 at single width);
  when the venue allows, propose a `figure*` (double width) version to the user.

## Layout patterns (pick from the design brief's cards; the domain volume says which are customary)
| pattern | blueprint shape | keep in mind |
|---|---|---|
| linear pipeline | root `row`; one `axis_of` child per stage so the main path is a straight line | side inputs (text, queries, conditions) enter from above/below, never through another box |
| U-shape (encoder–decoder with skips) | root `grid`: encoder levels down column 0, decoder levels up column 2, bottleneck at the bottom, `skip` edges across rows | input/output images at the top corners; skip labels (`concat`, `1×1`) on the skip edges |
| two stages sharing modules | one pipeline + overlapping `bracket` annotations (`side: top` / `bottom`) | do not duplicate the shared module; facts `scope` the stage brackets |
| overview + detail panels (composite) | grid with the overview in cells; detail groups `place: "free"` in empty cells, `detail_of` the block they expand | panels are flat and tinted like their source; zoom lines must not cross titles or nodes |
| teaser / comparison | root `row` of 2–3 groups at the same scale; the proposed approach last (rightmost) | equal box sizes across groups (`equalize`) so the comparison is fair |
| module detail | one group; operators as `op` nodes; thin layers as `slab`; tensor names as edge labels | operator glyph circles stay small; named functions (`Softmax`) are plain boxes |

## Space — neither crowded nor empty (the user's most-cited pain point: "过紧过松都不好")
- **Gaps nest.** Readers group by distance before they see any frame (Gestalt proximity), so the gaps must say the
  hierarchy: parts of one module closest, modules in a stage further apart, stages and panels furthest. An inner gap
  wider than the gap around its group regroups the figure wrongly. `gap` is the knob: `tight` for operator chains
  inside a detail panel, `normal` for modules, `loose` only between top-level stages. Uneven sibling gaps trigger
  `gap-uneven`.
- **Space follows the reader's questions** (the plan's `structure.budget`): the contribution and the data the
  reader studies (images, matrices, token rows) take the room; routine parts stay compact. A figure that is
  uniformly dense has no focus; one that is uniformly airy has no content.
- **No blank region.** A large empty rectangle (lint `hole`: over 10 % of the figure, not a thin band at an edge)
  reads as a missing part and makes the rest look crowded by contrast. Fix it in this order: move something that
  belongs there into it (an inset next to its source, the key, a data image); let the neighbour take the room (a
  larger image or matrix, a second line under a name); re-arrange so the bands close up (a short bottom row centred
  under a long one, or an inset moved beside the spine); make the band that sets the width narrower. Never pad
  with decoration, and never stretch boxes to fill it.
- **Even rhythm.** Peers are the same size with equal gutters (the engine), panels side by side share their height,
  and a panel whose foot is empty (`panel-sparse`) gets content or a shorter neighbour.
- The build scales all ink (text, strokes, arrows, images) up to 1.6× to reach a readable print size. If
  `min-font` still fires, the layout is too wide for the column: move to `width: "double"` when the venue and the
  user allow it; at a fixed single column use `--mix spacing=compact,typography=compact`, turn a long row into a
  grid, shorten labels (full names go in `full_name` and the legend), or split detail into panels.
- Empty quadrants are space for detail panels (`place: "free"`), not padding.

## Colour inside a module
Colour inside a module answers one question: does a part need to be told apart? Decide it there, not by habit.
- **One fill for parts of equal rank is fine.** TransUNet's authors draw LN, MSA, LN, MLP in one colour: the layer
  is one standard thing, and nothing in it is the point. Re-colouring such a module adds codes, not meaning.
- **Set a part apart only when the text does:** the operation the paper introduces inside a module (Restormer's
  transposed-attention map) may take the accent; the routine parts around it then stay as they are.
- **Colour by kind of operation only when the kind recurs and the reader must tell the kinds apart** (Restormer's
  1×1 / depth-wise / norm layers, repeated across both panels) — at most three kinds per module, the same kind in
  the same colour everywhere.
- **The ground never fights the parts.** A zoom-in panel sits on a near-white tint of its source's hue (the
  engine, 80 % toward white), so coloured parts stay legible on it; a strong tint under several foreign hues is the
  thing to avoid.
- **One element, one colour, at every depth:** the box on the spine, its inset and its module figure use the same
  tone, so the reader matches them without reading.
- **Parts stand apart from their area by lightness** as well as hue (a grayscale print keeps the structure), and
  text stays dark or in the hue's own dark shade (`text-contrast`).

## What the key is for
The key decodes what a reader cannot read off the figure where it is drawn: line styles (skip, training only),
operator glyphs (⊕, ⊗, Ⓡ), badges (frozen), abbreviations ("Dconv = depth-wise conv"), and colour categories
spread over many unlabelled elements (modalities, token kinds). Of the knowledge base's 441 cards, keys describe
lines and arrows most, then colour categories, then operators; none keys "proposed / ours". So:
- no entry for a box that is already labelled — a swatch named "MDTA" beside a box reading MDTA says nothing;
- no "ours" entry: the authors' names on the boxes and the caption say what is new (the engine adds none);
- a colour category goes in the key only when its elements do not say it themselves (`tone_legend`, blueprint.md);
- no entry twice ("Norm = LayerNorm" and a "LayerNorm" swatch); few codes → no key at all, labels in place.

## Emphasis
- The author's modules carry `role: "proposed"` and their exact names (`full_name` + `abbrev`); the style gives
  them a warm container. Reused parts are muted automatically — do not add extra colour to them.
- One accent family for proposed parts, neutral tones for the rest (in a multi-modal model the fills mean modality
  and the accent is a ring instead — see "Colour by modality"); `tone` names come from the style recipe
  (`blue`, `green`, `orange`, `purple`, `pink`, `red`, `teal`, `yellow`, `gray`). Two different kinds of thing never share a tone.
- `badges: ["frozen"]` / `["trainable"]` when the text says a part is frozen or trained.

## Lint findings → usual fix
Errors block delivery; warnings must be fixed or explained in the report; info is for the critic and the user.
| finding | means | usual fix |
|---|---|---|
| `coverage-missing` / `coverage-extra` | the drawing and the blueprint disagree | engine bug — report it, do not hand-edit the XML |
| `proposed-name-missing` | a proposed module's name is not on its node/container | set `full_name`/`abbrev` or make the label contain the name |
| `text-overflow` | a label or title does not fit | shorten the label or break it with `<br>`; boxes size to their text, so a persisting overflow is an engine bug — report it |
| `overlap`, `child-outside-parent` | boxes collide | different `cell`s, a larger `gap`, or a free panel moved to an empty cell |
| `badge-overlaps-text` | badge icon sits on the label | shorten the label |
| `callout-missing` / `callout-crosses-node` / `callout-crosses-title` | detail-panel zoom lines | move the panel next to its source; `title_align: "left"` |
| `bracket-coverage` / `bracket-spans-uncovered` | a bracket does not span what it claims, or spans extra boxes | reorder children so the covered ids are contiguous |
| `edge-through-node` / `edge-through-title` / `edge-through-legend` / `edge-through-annotation` | an arrow crosses something | reorder children, set `src_side`/`dst_side`, or move the node |
| `edge-crossings`, `edge-overlap` | arrows cross or run on top of each other | reorder siblings so connected parts are adjacent; route side inputs from another side |
| `edge-parallel` | two lines side by side (or one over another) read as one thick line | the engine spaces ports two arrowheads apart and grows the block or gap; if it remains, move one input to another side or reorder siblings |
| `edge-head-run` | an arrowhead with no straight line behind it, or butting its label | the engine reserves 2.5 arrowheads at every head; if it remains, the two parts are too close — loosen that gap (`gap`), or move the label's edge |
| `edge-through-label` | a line through text: another edge's label, a name below a shape, a label on a frame border | the engine moves names beside narrow shapes and labels off borders; if it remains, reroute by side pins or move the part |
| `edge-jog`, `edge-diagonal` | small kinks | align ports: same row/column for both ends, or `axis_of` |
| `edge-hugs-border` | an arrow runs along a container edge | change the side of one end or the gap |
| `edge-label-overlap` | edge label sits on a box | shorter label, or move it to a node |
| `min-font` | text prints below the venue's floor at its width: the venue's stated minimum (Nature 5 pt), else 7 pt (error below 6 pt; 5.5 pt for a full-width overview, as dense published ones print) | see Density above |
| `gap-uneven`, `density` | rhythm or ink ratio off (provisional thresholds) | equalise gaps; compact or loosen the grid |
| `text-contrast` | text unreadable on its fill | different tone or style |
| `tone-confusable` | two tones collapse for colour-blind readers | change one tone |
| `gray-confusable` (info) | two tones look alike in grayscale | fine if they never sit side by side; else change one |
| `edge-kind-color-only` | two edge kinds differ only by colour | engine/style issue — report it |
| `asset-pending` | placeholder images remain | a repo demo image or a public dataset sample (step ⑤); else list in the report |
| `fact-omitted` (info) | the plan leaves this fact out on purpose | nothing — it is shown at the blueprint gate and in the report |
| `facts-all-omitted` / `fact-omitted-majority` | the plan leaves out every / most stated facts | keep the main line's facts; map edge-label or merged components with `drawn_as` |
| `key-rep-inconsistent` | a recurring representation is drawn in different ways | one `visual` + `tone` for all its `ids` |
| `tone-undeclared` / `tone-two-meanings` | a tone has no stated meaning, or marks the contribution and something else | declare it in `color_semantics`; give the contribution its own tone |
| `gray-highlight` | the contribution differs from reused parts by hue only | a fill of different lightness, a heavier outline or a bold name |
| `proposed-mismatch` (error) / `proposed-name` | a module the analysis calls proposed is drawn as reused, or without the paper's name | role `proposed`, `full_name` / `abbrev` as the paper writes them |
| `edge-unstated` | a drawn data edge between analysed components that no analysis states | check the paper; add the flow to the analysis with its quote, or remove the edge |
| `fact-waived` | a fact was waived in facts.json instead of being omitted by the plan | move it to the plan's `omitted` (shown to the user) |
| `edge-detour` / `edges-parallel` | an arrow wraps around, or two arrows join the same pair | see Edge economy |
| `stub-overlap` (error) | a stub arrow runs into a neighbour | a looser gap on that side, or another side |
| `align-title-blocks` | an aligned, titled frame blocks its own straight link | `frame: "none"` + an inner bracket for the name, or enter from the side |
| `schematic-unmarked` | a heatmap / mask / k-space glyph could be read as a result | `"illustrative": true`, and "schematic" in the caption |
| `aspect-tall` | an overview/teaser taller than three in four top-venue overview figures | horizontal main line, zoom-ins beside it, full text width (see Width and aspect) |
| `palette-washed` | every fill is near-white | give the contribution its accent and each representation its semantic tone |
| `zoom-ins-many` | more than two detail panels | expand only the one or two mechanisms the 2-minute reader needs; give the next one `depth` `own-figure` |
| `zoom-nested` | a zoom-in opens a box inside another zoom-in, or inside a panel no line ties to the overview | open the module once from the spine box (its parts as panels (a), (b)), or `own-figure` for the inner one (§ How deep the overview goes) |
| `hole` | a blank region over 10 % of the figure | § Space: move a part into it, let a neighbour take it, re-arrange the bands, or narrow the band that sets the width |
| `png-mismatch` | the PNG is stale or the wrong shape | rebuild; never deliver a stale PNG |
| `fact-missing` / `fact-out-of-scope` / `fact-unknown-id` | the blueprint lacks a connection the paper states | add the edge (or the node); never waive a fact without the user |
| `png-margin` | the exported PNG has a wide blank strip on one side — draw.io's bounds run past the drawing | find the cell: usually a no-wrap label whose raw TeX is longer than its rendering, or a hidden cell |
| `fact-reversed` | in a loop, the fact is reached only the long way round while the figure draws the opposite arrow | draw the stated arrow, or list the fact in the plan's `omitted` |
| `fact-omitted-drawn` | the plan omits a fact the figure does draw | drop it from `omitted`, or check the path really shows that flow |
