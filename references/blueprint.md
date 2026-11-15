# Blueprint guide

The blueprint (`blueprint.json`) is the single source of what the figure shows. `paperfig build` compiles it
with a style recipe into draw.io XML; nothing in the figure exists unless the blueprint says so.
Schema: `schemas/blueprint.schema.json` — `$PAPERFIG validate blueprint FILE` reports every problem at once.
Worked examples (both accepted by the user): `examples/restormer.blueprint.json` (U-shaped overview with two
detail panels, operators, brackets-free) and `examples/blip2.blueprint.json` (two-stage pipeline with
overlapping stage brackets). Read the one closest to your figure before writing a new blueprint. They predate the
v2 Brief and show few data visuals — do not copy their box-heavy look; `examples/restormer.figure_plan.json`
is a worked v2 Brief for the Restormer blueprint (the plan you write before a blueprint).

## Top level
```json
{"schema_version": 1,
 "figure": {"type": "overview", "venue": "cvpr", "width": "double", "style": "soft-pastel",
            "legend": "auto", "legend_notes": ["Dconv = depth-wise conv"], "label_language": "en"},
 "root": {group}, "edges": [edge, …], "annotations": [bracket, …], "discrepancies": [ … ], "notes": "…"}
```
- `venue` — a key of `kb/formats.json` (`cvpr`, `iccv`, `eccv`, `neurips`, `icml`, `iclr`, `acl`, `emnlp`, `naacl`,
  `ijcai`, `ieee-conference`, `acm-sigconf`, `lncs`, `nature`, …); `width` — `"double"` (text width), `"single"`
  (column width) or a number of inches. Lint checks font sizes at this printed width.
- `highlight`: `"fill"` (default: the contribution gets its tinted fill) or `"outline"` (white with a heavy accent
  outline — for figures whose data or images should carry the colour).
  `"ring"`: every box keeps its semantic fill (the modality: image side, text side) and the proposed parts get a
  heavy outline in the accent — for multi-modal models whose fills encode the modality (plan `color_by: "modality"`).
- `legend_labels` renames legend entries, e.g. `{"proposed": "ours", "control": "attention mask"}`; keys are the
  kind names, plus `loss:end` for one-sided loss edges (`heads: "end"`).
- `"tone_legend": true` adds a swatch per tone the figure uses, named by the plan's `color_semantics` — use it when
  colours carry meaning the labels do not say (a learned vs a closed-form step); the reader cannot see the plan.
- `legend_at`: where the key sits — `auto` (a free corner of the figure, else a right column or a bottom band),
  `corner`, `bottom`, `right`, `top`. Never a hole between content; the plan's `layout.legend_at` names the same.
  Prefer `legend: "none"` with direct labels on lines and regions when there are only a few codes
  (`references/layout.md` § 6).
- `legend: "auto"` lists what the figure's visual codes mean (proposed, frozen, edge kinds, operators used);
  `legend_notes` adds abbreviation lines.
- `discrepancies` — every draft-vs-code difference you found and how it was resolved
  (`{"what": "…", "draft": "…", "code": "…", "decision": "…"}`); shown to the user at the blueprint gate.

## Ids and provenance
- Use the **draft analyst's component ids** as node ids; the facts file refers to them.
- Every node, group and edge carries `"provenance": [{"source": "draft"|"code"|"user", "ref": "Sec. 3.1" | "arch.py:66"}]`.

## Groups (containers)
```json
{"id": "enc", "title": "Encoder", "role": "reused", "frame": "box", "tone": "blue",
 "layout": {"type": "column", "gap": "normal", "align": "center", "equalize": true}, "children": [ … ]}
```
- `layout.type`: `row` (left→right), `column` (top→bottom), `grid` (children give `"cell": [row, col]`,
  optional `"span": [rows, cols]`). `gap`: `tight` | `normal` | `loose`. In a grid a span gives a child room but
  does not stretch a group: the group keeps its own width, centred in the span (framed or not). To line children
  up under the columns above, put them in the grid themselves, or use a `canvas`.
- `layout.order`: `auto` (default) lets the engine reorder a row/column of plain blocks to cross fewer lines,
  never reversing two connected siblings (the flow keeps its direction) and never moving panels; lint info
  `auto-order` says what moved. `fixed` keeps your order (a sequence whose order means something).
- `frame`: `box` (titled container), `dashed`, `none` (layout only, invisible).
- Proposed module: `"role": "proposed", "full_name": "Multi-Dconv Head Transposed Attention", "abbrev": "MDTA"` —
  the name must appear verbatim (lint `proposed-name-missing`) — a group's in its title, or in the label of a
  bracket that covers it (keeps the frame top free for edges entering from above).
- `equalize` (grid groups, default `true`): siblings in a grid share the widest box's width — tidy, but one long
  label widens every box; set `"equalize": false` (or shorten the label) when it pushes text below the floor.
- `layout.type: "cycle"`: the children are a loop (agent act → observe → think, a training feedback loop) — placed
  clockwise around a rectangle (top row left→right, bottom row right→left); `layout.hub` names a child placed inside
  the loop (the LLM the loop revolves around). Draw the loop's edges child-to-next-child; give no `cell`s. A ring
  of 4 is about square, so in a wide overview prefer a `grid` (2 rows: the loop as top row → down → bottom row
  back, the environment or outside world in the end column) and keep `cycle` for a loop that is the whole panel.
- `layout.type: "canvas"` (optional `cols`, default 12): free composition on equal columns — each child's `cell`
  [row, col] and `span` [rows, cols] say where it sits and what share of the width it takes (a hero block over 8 of
  12 columns, satellites over 2). Boxes, trapezoids, text cards and framed groups fill their span; data-shaped
  visuals (tensors, icons, glyphs, images) keep their size, centred in it. Rows still follow their content. A gutter
  an edge crosses gets the full gap (and a label's room); others are narrow. All columns are as wide as the most
  demanding child needs per column (lint info `canvas-pitch` names it): give wide content more columns, or the
  whole figure widens and its text shrinks. Use a canvas when rows/columns/grid would force an unnatural
  composition; a plain pipeline stays a `row`.
- `layout.gap: "none"` glues children (chips).
- `axis_of: "<descendant id>"` — aligns the group on that child's centre line (straight main path). A group's
  default axis is the middle of its content *including labels hanging below*, so a row of images with captions sits
  a few px off a sibling box: set `axis_of` to one of its members.
- Detail panel: a group with `"detail_of": "<node id>"` draws a callout from that node to the panel; put the
  panel in a grid cell with `"place": "free"` to use empty space without resizing the grid.
- `title_align`: `center` (default) or `left`.

## Nodes
```json
{"id": "mdta", "label": "MDTA", "role": "proposed", "visual": "box", "tone": "orange", "badges": ["trainable"]}
```
- `label` markup: `<b> <i> <sub> <sup> <br> <small>`; `<small>` is secondary text inside a box (dimensions, settings, a symbol line under the name) — 80 % size, muted grey, still held to the 7 pt print floor; `&lt; &gt; &amp;`; TeX math between `$…$` (see Known engine limits). Keep labels short; long names go in `full_name`. Placeholder labels take the same markup. At a narrow venue width (LNCS 4.8 in, a column) a `<small>` line is what sets the print floor — drop it or move it to the caption before shrinking anything else.
  Inside parentheses an ASCII `|` is drawn as the conditional bar `∣` (p(z|x) never reads as "zlx"). A `text` node
  takes its `tone`'s font colour; a `glyph` with `"accent": false` keeps the accent colour out of it.
- `visual`:
  | value | use for | extra fields |
  |---|---|---|
  | `box` | modules, layers | — |
  | `trapezoid` | encoders (`taper: "in"`, narrows rightwards) / decoders (`taper: "out"`); in a vertical flow `taper: "down"` narrows downwards, `"up"` upwards | `taper` |
  | `tensor` | a feature map drawn as a 3-D block (size from the style) | optional `size: [w, h]`, taken exactly — use it to taper maps by resolution |
  | `stack` | several stacked feature maps | `sheets` (2–6) |
  | `slab` | a thin layer (1×1 conv, Norm) with a rotated label, inside detail panels | — |
  | `tokens` | a token sequence | `tokens` (count); optional `values` (one number in [0, 1] per token) shades each cell — draw unequal weights (attention α, scores) instead of saying them; an exact 0 is an empty cell (sparse codes after thresholding) |
  | `op` | operator circle: `op` = `add`, `mul`, `matmul`, `concat`, `reshape`, `gelu`; label empty | `op` |
  | `image` | a real image (centre-cropped to its box, never stretched) | `asset: {"path", "status": "provided" \| "from-code"}`, optional `size: [max_w, max_h]` ; a concept illustration of a scene the source describes as visual: `status: "generated"` + `spec` (only what the quote states) + `grounds: {"ref", "quote"}` + `"illustrative": true`, made by `$PAPERFIG illustrate … --text METHOD [--repo CODE]` (refuses a quote the source lacks) |
  | `placeholder` | a missing image, drawn as an empty image frame with its short `label` (e.g. `CT slice`) | `asset: {"status": "requested" \| "placeholder", "spec": "what to supply"}` — the `spec` goes to the report, never into the drawing; `size: [w, h]` gives the frame's size (else ¾ aspect) |
  | `icon` | any Lucide vector icon (ISC licence, pinned version): common ones ship in `icons/` (user, bot, wrench, search, globe, code, terminal, database, brain, image, video, mic, camera, car, …), any other name is fetched on first use and cached — find names with `$PAPERFIG icon search game controller` (Lucide's own tags). Use an icon for an actor, tool, modality, action or environment a reader recognises faster as a picture; never as decoration | `icon` |
  | `text` | a free text label | — |
  | `textcard` | an example message, prompt, thought or tool call — left-aligned text in a card (agents, LLM papers: show one real short example, not a box called "data") | `card_style`: `plain`, `code` (monospace, for code / call syntax), `bubble` (a speech bubble, for dialogue; tint it with the speaker's `tone`), `quote` (a real input sentence: dashed card in its source's `tone`, label `<i>“…”</i><br><small>caption · 1 per image</small>` — one tone per kind of text input) |
  | `chip` | a piece as small as its text, for glued inputs like [d &#124; x] — put chips in a row with `gap: "none"` | — |
  | `glyph` | a symbol for what boxes cannot show: `graph` (a node and its neighbours; `nodes` 3–8, centre in the accent; to explain a message-passing method on the graph itself: `variant` `neighbourhood` (a two-hop toy neighbourhood), `khop` (hop rings, the sampled neighbours and edges in the accent tint, the rest faint), `aggregate` (only the sampled part, messages flowing toward the centre), `subgraph` (an induced subgraph picked out in a toy graph — subgraph or cluster sampling, no centre node), `layers` (a GCN unrolled over the subgraph: every node in each layer, fed by its neighbours below) — give it a `size` of about 110×100 so it reads as the panel's subject), `database` (a store / retrieval index), `prototype` (a learned prototype or query vector), `heatmap` (an attention / similarity map), `mask` (a segmentation label map), `kspace` (k-space with its sampling `pattern`: `cartesian`, `radial`, `random`), `ellipsis` (three dots, no box: "and so on" between unrolled stages or copies — a text node "⋯" prints tiny and takes a grid column; link it with `heads: "none"` on the way in), natural images without a licensed sample: `natural-image` (`variant` `clean`, or `degraded` for a measured / undersampled one); MRI data without a licensed sample: `mr-image` (the modified Shepp-Logan phantom; `variant` `clean`, or `aliased` for an undersampled input with fold-over ghosts), `sampling-mask` (the undersampling mask; `pattern` as for `kspace`), `coil-maps` (a stack of coil sensitivity maps), `documents` (stacked text pages: an agent's memory of reflections, a log, a retrieved corpus — text, where `database` is an index and `stack` reads as feature maps); data thumbnails that show what the data looks like instead of a grey placeholder: `pointcloud` (`variant`: `chair`, `airplane`, `blob`, `scene`), `waveform`, `spectrogram`, `trajectory` (a path with start and goal), `molecule` (ball-and-stick, element colours), `plot` (`variant`: `decay` loss, `rise` score, `bell` density, `schedule` noise schedule); structure glyphs that draw what a representation is (not data — no `illustrative` needed): `onehot` (a categorical latent: `grid` [rows, classes], one class on per row), `vector` (a bracketed column of `nodes` cells: an embedding, a state, proprioception), `patches` (an image in patches and attention windows: `grid` [rows, cols], `variant` `regular` or `shifted`), `pair-matrix` (a contrastive objective drawn as CLIP draws it: rows × columns with the positive pairs filled blue (their own code, never the contribution accent); `variant` `one-to-one` (diagonal), `many-to-one` (rows share a column: a class sentence), `many-to-many` (rows share column sets: concepts); `grid` [rows, cols]; rows take the node's `tone`, columns `col_tone`; label it with the objective and its pairing, e.g. "L<sub>lab</sub><br>image ↔ label · N:1"; `positives: [[1,1],[2,1],[3,2]]` sets the filled cells (1-based [row, col]) when the pattern carries meaning or two copies must match — otherwise the variant draws its own; `axes: ["z", "t"]` names the header cells z₁…, t₁… as the author's own figure does — the glyph grows to hold them at the label size and lint holds them to the 7 pt floor) | `glyph`; `variant`, `grid` where listed; `heatmap`, `mask`, `kspace` and every data thumbnail are schematic — set `"illustrative": true` (dashed frame; lint `schematic-unmarked` otherwise) and say "schematic" in the caption; a real image of the data goes in an `image` node instead |
- `size` is in final drawing units (the text fit scales fonts and strokes, not sizes you set) — so a size chosen to
  make two lines meet straight breaks when the fit scale changes (VS-Net blind run); straighten with `align_x/y`. Tensors and stacks
  take it exactly; boxes only grow to it (their text must fit); images fit inside it.
- Edge `"curved": true` draws that edge as a smooth curve through the router's own bends (same path, same
  obstacle checks): use it for a feedback loop or a long link between panels, so it reads as a return or a
  jump rather than one more pipe; keep the main line straight.
- Edge `"heads": "none"` draws a plain link with no arrowhead (a toy graph's edges drawn as elements).
- Edge `"heads": "end"` draws one arrowhead, at the target only. A `loss` edge otherwise has two heads and the
  legend reads "compares both ends"; use `end` for a one-sided penalty on its target (an entropy hinge or a
  regularizer on the policy). The legend then adds "loss (one-sided)". An arrow that feeds a loss box (prediction ->
  loss) is also one-sided: give it `heads: "end"` (two heads into a box read as ambiguous — VS-Net critic).
- Edge `"bundle": "<name>"` on a fan-out (edges sharing a source) or a fan-in (sharing a target): one port, one
  trunk, then a branch per edge — the bus convention, instead of N separate arrows leaving from different sides.
  Applied only when every other end lies on one side and no branch crosses an element; otherwise the edges keep
  their own routes and lint info `bundle-skipped` says why.
- `pin: [dx, dy]` — a hand move: the element (and everything in it) shifts after layout. Written by
  `$PAPERFIG absorb BLUEPRINT EDITED.drawio --style S` from a figure the author moved or retyped in draw.io
  (moves → pins, label text → labels; resizes, edge reroutes and deletions are listed, not absorbed). A pin onto a
  neighbour or out of its frame stops the build with the reason.
- `stub: {"side": "right", "label": "to decoder"}` on any node draws a short outgoing arrow with no drawn target (a
  detail panel's output); its label sits above a horizontal stub (from its root outward) or beside a vertical one.
  Point a stub at free space — lint `stub-overlap` (error) reports an arrow or label that runs into a neighbour.
- Softmax and other named functions are plain `box` nodes labelled `Softmax` — not operator circles.
- `role`: `proposed`, `reused`, `io`, `data`, `loss`, `op`, `annotation`. Reused parts recede automatically.
- `badges`: `frozen` (snowflake), `trainable` (flame).

## Edges
```json
{"src": "enc1", "dst": "dec1", "kind": "skip", "label": "concat", "src_side": "auto", "dst_side": "auto"}
```
- `kind`: `data`, `skip`, `loss`, `train_only`, `infer_only`, `grad`, `control` — every kind has the same stroke width;
  the meaning is the pattern (solid / dashed / dotted / dash-dot) or a clearly different colour, and the legend
  lists the kinds used. In the shipped styles: data solid dark, control solid light grey, skip dashed grey, loss
  dashed red, train-only dotted, infer-only dash-dot dark, gradient dash-dot red. Lint `edge-kind-color-only`
  warns when two kinds in a figure look alike, or differ by colour only and merge in grayscale print; colour-only
  differences that survive grayscale are fine (info).
- `src_side` / `dst_side` pin the port when the auto choice routes badly.
- `tone` (optional): colours this one path with a tone — for a path that means something specific (the action path
  vs the feedback path of an agent); declare the meaning in the plan's `color_semantics`.
- `id` (optional, e.g. `"e_rtg"`): give one whenever the figure plan's `drawn_as` names the edge (a component drawn
  as its label); otherwise ids are assigned in order and shift when edges are added.
- `label` reserves space: a label on a horizontal edge widens that gap, on a vertical edge it adds height. Prefer
  short labels (`E`, `concat`, `1×1`); long ones belong in the caption.
- An edge may end on a group (container) — it attaches to the frame; for the facts check, reaching a container
  reaches everything in it, and an edge leaving a group carries what leaves its members that have no outgoing
  edge of their own (its exit points). In a loop every node reaches every other, so a fact reached only around
  the loop while the figure draws the opposite arrow is `fact-reversed` (draw it, or omit it in the plan). A component drawn
  several times (`drawn_as` copies) is reached at any copy, but each step of a `via` fact starts from the copy the step
  before reached: one chain of drawn arrows, never a jump between copies.
- Facts follow data-flow kinds (`data`, `skip`, `train_only`, `infer_only`); a fact about a `loss`, `grad` or
  `control` edge must say so with `"kinds": ["loss"]` (etc.) in `facts.json`.

## Annotations
```json
{"id": "stage1", "kind": "bracket", "covers": ["img_enc", "qformer"], "label": "Stage 1: representation learning", "side": "top"}
```
Brackets may overlap (two training stages sharing a module); a facts `scope` may name a bracket. `placement:
"inner"` names an inner row in place (e.g. "trainable copy" over the second row) instead of the outer lane.

## Typeface
`figure.font`: `"sans"` (default — the style's Helvetica) or `"serif"` (Times New Roman everywhere, measured with
its own metrics) to match a serif body. Nature asks for sans-serif lettering, one font in all figures (lint
`font-family`); a paper's figures share one `font` (split parts inherit it). Hierarchy inside a figure: group titles
> box names > `<small>` secondary lines and edge labels — not more sizes than that.

## Overview + detail, one figure or two
When an overview with `detail_of` panels prints below 7 pt, lint `split-suggested` builds both alternatives and
reports each one's print size. If the module figures gain but the overview alone stays small, the overview row is
too wide for the width (the message says so) — widen to the double column or regroup; splitting will not fix it.
`$PAPERFIG split BLUEPRINT --out DIR` writes `DIR/overview/` (the expanded node reads "(Fig. 2)") and one
`DIR/module-<panel>/` per panel, each with its own facts (a fact scoped to the panel scopes the whole module
figure), plan drawn_as / omitted and analyses. Module figures are numbered in the panels' (a), (b) order, take
the column width when their text holds 7 pt there (else the page width), and keep only the legend notes for what
they draw. Build and check each part like any blueprint.

## Known engine limits (design around them; do not fight them for long)
- Nodes in different framed groups are laid out independently. To line one up with a node elsewhere, give it (or
  its group — the group's `axis_of` child is what lines up) `"align_x": "<node id>"` / `"align_y"`: after layout it
  shifts, with everything in it; a shift that would leave its parent or hit a sibling stops the build with the
  reason. For a vertical link into an aligned group, a centred frame title sits in the way (lint
  `align-title-blocks`): use `frame: "none"` and name the row with an inner bracket.
- An arrow entering a framed group from the top passes its title; enter from the side, or title the group `left`.
- A label on a vertical edge reserves the whole gap between its rows; a label on a horizontal edge widens its gap.
- Brackets sit in the outer top/bottom lane by default; `"placement": "inner"` puts one right above (or below) what
  it covers, between rows — give that row gap room (`gap: "loose"`); without room lint reports the overlap.
- At single-column width only about 4 boxes fit per row at the 7 pt floor (`min_node_w` scales with the text).
- Math: write TeX between dollars — `$\alpha_{ij}$`, `$\mathrm{softmax}(QK^\top/\sqrt{d})$` — and draw.io's
  MathJax typesets it at export (vector in the PDF); `\$` is a literal dollar. Use it for the variables and short
  operator names the paper writes in math (`$z_q$`, `$\bar r_I$`, `soft$(\cdot,\theta)$`); plain names stay
  plain text. A block carries a name and at most the variable it produces — never a whole formula (lint
  `formula-in-block`; the equation belongs to the paper and the caption). Outside math, a `|` inside parentheses is drawn as `∣`.
- `bundle` (one trunk with branches) needs every branch end on one side of the shared end; with ends on different
  sides it is skipped (info `bundle-skipped`) and drawn as separate arrows — a side signal into two consumers far
  apart is better written as a label at each consumer (`references/derive.md` principle 5).
- A `trapezoid`'s slanted sides bend lines that enter them (a text-encoder drop into a slanted top kinks): use a
  trapezoid where lines enter its flat ends only, or a box.
- `glyph` `ellipsis` still needs `"label": ""`, and give it the `tone`/`role` of what it stands for (it is not a
  module: without one it counts as a `reused` box in the colour checks).
- `axis_of` is a group field (beside `layout`, not inside it): the child the group lines up by.
- Text cards and icon / glyph / tensor labels use the style's `small_size`, so they set the font floor first: a
  worked-example row of text cards (long code lines) fixes how wide the drawing may be before the 7 pt floor is
  crossed (lint `min-font`). Keep example lines short (≈ 30 characters), at most 3–4 cards per row; an icon's
  label is a word or two.

