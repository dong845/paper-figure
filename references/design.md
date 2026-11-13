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
  The contribution may get an expanded detail panel; reused parts stay collapsed.
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

## From contribution to composition (how published figures express each kind of idea)
Pick the technique for what the paper contributes — the Brief's `contributions[].shown_by` names it. Each row
cites knowledge-base cards that do it (`kb query` shows their full `lesson`); combine techniques when a paper has
several contributions, and invent when none fits — these are patterns that work, not a menu to obey.
| contribution | technique | evidence |
|---|---|---|
| a new space or representation (latent, discrete codes, tokens) | draw the representation as data and give it one motif and colour everywhere it travels; spaces as regions | vqgan-2020-fig2, vq-diffusion-2022-fig1, knn-lm-2020-fig1 |
| a new module inside a known backbone | backbone collapsed and muted; the module on its own tint, expanded once in a detail panel tied by matching tint | transbts-2021-fig1, dpt-2021-fig1, pointmlp-2022-fig2, t2i-adapter-2023-fig3 |
| a new conditioning / control path | the added signal enters from the side on its own bus at every block it feeds, in its own colour | ip-adapter-2023-fig2, gligen-2023-fig3 |
| a trainable copy / frozen base | trainable vs frozen encoded twice (fill + flame/snowflake or a margin note) | gligen-2023-fig3, best-rq-2022-fig1, emdr2-2021-fig1 |
| sequence modelling | one token row under one wide model bar, the predicted row above, shifted one slot | trajectory-transformer-2021-fig1, vima-2023-fig3 |
| retrieval / memory | the store, the top-k items as data in their own colour, and how they merge | retro-2021-fig2, replug-2023-fig2, murag-2022-fig4 |
| multi-stage training or a cascade | one full-width band per stage; a reused module keeps shape and fill in every band | wuerstchen-2024-fig3, muse-2023-fig3, realm-2020-fig2 |
| a training signal or target branch | the target generator as a separate side branch in its own colour family, dashed | hubert-2021-fig1, audioldm-2023-fig1 |
| typed entities (node types, modalities) | one colour per type, repeated on everything that belongs to it | hgt-2020-fig2, retro-2021-fig2 |
| multi-scale encoder–decoder | U laid sideways or as columns with scale labels on the skips, mirrored sizes in the margins | unetr-2022-fig2, swin-unet-2021-fig1, pointnet-plus-plus-2017-fig2 |
| an unrolled / physics-guided reconstruction (data consistency) | draw it compact first, then unrolled (first, a middle, last iteration with ellipses); the measured data as one bus under the cascade tapping every DC step; FT/IFT on the arrows between real image and k-space stacks (`kspace` glyph when no real data) | modl-2017-fig1, cascade-cnn-2017-fig4, e2e-varnet-2020-fig1, dudornet-2020-fig1 |
| dual-domain processing (k-space + image) | colour names the domain, and every feed line takes the colour of the domain it enters | dudornet-2020-fig1, e2e-varnet-2020-fig1 |
| a design choice among variants | the chosen variant in full colour, the rejected ones at the same size faded | dit-2022-fig3 |

## Against the "AI look"
| looks generated | looks designed |
|---|---|
| a container (frame) around every group | frames only where grouping carries meaning (a stage, the expanded module); others `frame: "none"` |
| every node the same rounded pastel box | box shapes follow meaning: trapezoids for encoders/decoders, stacks for features, images for data, ops as glyphs |
| every block the same pale/white fill (reads as white) | the guide's colour system: a neutral backbone (reused parts), one strong accent for the contribution, a secondary accent for interaction (attention, conditioning), and one semantic tone per kind of representation (features, prototypes, latents) used everywhere it appears; areas (frames) a lighter tint than the elements inside |
| a different colour for every module | one colour = one meaning (`color_semantics`); top-venue overview figures use ≈4–6 colours with a stated meaning each |
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
  rather than adding rows.

## Layout patterns (pick from the design brief's cards; the domain volume says which are customary)
| pattern | blueprint shape | keep in mind |
|---|---|---|
| linear pipeline | root `row`; one `axis_of` child per stage so the main path is a straight line | side inputs (text, queries, conditions) enter from above/below, never through another box |
| U-shape (encoder–decoder with skips) | root `grid`: encoder levels down column 0, decoder levels up column 2, bottleneck at the bottom, `skip` edges across rows | input/output images at the top corners; skip labels (`concat`, `1×1`) on the skip edges |
| two stages sharing modules | one pipeline + overlapping `bracket` annotations (`side: top` / `bottom`) | do not duplicate the shared module; facts `scope` the stage brackets |
| overview + detail panels (composite) | grid with the overview in cells; detail groups `place: "free"` in empty cells, `detail_of` the block they expand | panels are flat and tinted like their source; zoom lines must not cross titles or nodes |
| teaser / comparison | root `row` of 2–3 groups at the same scale; the proposed approach last (rightmost) | equal box sizes across groups (`equalize`) so the comparison is fair |
| module detail | one group; operators as `op` nodes; thin layers as `slab`; tensor names as edge labels | operator glyph circles stay small; named functions (`Softmax`) are plain boxes |

## Density (the user's most-cited pain point: "过紧过松都不好")
- `gap` is the knob: `tight` for operator chains inside a detail panel, `normal` for modules, `loose` only
  between top-level stages. Uneven sibling gaps trigger `gap-uneven`.
- The build scales all ink (text, strokes, arrows, images) up to 1.6× to reach a readable print size. If
  `min-font` still fires, the layout is too wide for the column: move to `width: "double"`, turn a long row into
  a grid, shorten labels (full names go in `full_name` and the legend), or split detail into panels.
- Empty quadrants are space for detail panels (`place: "free"`), not padding.

## Emphasis
- The author's modules carry `role: "proposed"` and their exact names (`full_name` + `abbrev`); the style gives
  them a warm container. Reused parts are muted automatically — do not add extra colour to them.
- One accent family for proposed parts, neutral tones for the rest; `tone` names come from the style recipe
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
| `edge-jog`, `edge-diagonal` | small kinks | align ports: same row/column for both ends, or `axis_of` |
| `edge-hugs-border` | an arrow runs along a container edge | change the side of one end or the gap |
| `edge-label-overlap` | edge label sits on a box | shorter label, or move it to a node |
| `min-font` | text prints below 7 pt (error below 6 pt) at the venue width | see Density above |
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
| `schematic-unmarked` | a heatmap / mask / k-space glyph could be read as a result | `"illustrative": true`, and "schematic" in the caption |
| `aspect-tall` | an overview/teaser taller than three in four top-venue overview figures | horizontal main line, zoom-ins beside it, full text width (see Width and aspect) |
| `palette-washed` | every fill is near-white | give the contribution its accent and each representation its semantic tone |
| `zoom-ins-many` | more than two detail panels | expand only the one or two mechanisms the 2-minute reader needs |
| `png-mismatch` | the PNG is stale or the wrong shape | rebuild; never deliver a stale PNG |
| `fact-missing` / `fact-out-of-scope` / `fact-unknown-id` | the blueprint lacks a connection the paper states | add the edge (or the node); never waive a fact without the user |
