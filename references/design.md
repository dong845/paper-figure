# Design guide — layout patterns, emphasis, and what each lint finding means

Read this when you write the blueprint's structure (step ②) and every time a lint report has findings (step ⑥).

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
| `asset-pending` | placeholder images remain | ask the user / run the code (step ③); list in the report |
| `png-mismatch` | the PNG is stale or the wrong shape | rebuild; never deliver a stale PNG |
| `fact-missing` / `fact-out-of-scope` / `fact-unknown-id` | the blueprint lacks a connection the paper states | add the edge (or the node); never waive a fact without the user |
