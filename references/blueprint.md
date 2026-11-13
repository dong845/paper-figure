# Blueprint guide

The blueprint (`blueprint.json`) is the single source of what the figure shows. `paperfig build` compiles it
with a style recipe into draw.io XML; nothing in the figure exists unless the blueprint says so.
Schema: `paperfig/schema/blueprint.schema.json` — `$PAPERFIG validate blueprint FILE` reports every problem at once.
Worked examples (both accepted by the user): `bench/phase0/restormer/blueprint.json` (U-shaped overview with two
detail panels, operators, brackets-free) and `bench/phase0/blip2/blueprint.json` (two-stage pipeline with
overlapping stage brackets). Read the one closest to your figure before writing a new blueprint.

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
- `legend_labels` renames legend entries, e.g. `{"proposed": "ours", "control": "attention mask"}`.
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
  optional `"span": [rows, cols]`). `gap`: `tight` | `normal` | `loose`.
- `frame`: `box` (titled container), `dashed`, `none` (layout only, invisible).
- Proposed module: `"role": "proposed", "full_name": "Multi-Dconv Head Transposed Attention", "abbrev": "MDTA"` —
  the name must appear verbatim (lint `proposed-name-missing`).
- `equalize` (grid groups, default `true`): siblings in a grid share the widest box's width — tidy, but one long
  label widens every box; set `"equalize": false` (or shorten the label) when it pushes text below the floor.
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
- `label` markup: `<b> <i> <sub> <sup> <br>`; `&lt; &gt; &amp;`. Keep labels short; long names go in `full_name`.
  Inside parentheses an ASCII `|` is drawn as the conditional bar `∣` (p(z|x) never reads as "zlx"). A `text` node
  takes its `tone`'s font colour; a `glyph` with `"accent": false` keeps the accent colour out of it.
- `visual`:
  | value | use for | extra fields |
  |---|---|---|
  | `box` | modules, layers | — |
  | `trapezoid` | encoders (`taper: "in"`, narrows rightwards) / decoders (`taper: "out"`) | `taper` |
  | `tensor` | a feature map drawn as a 3-D block (size from the style) | optional `size: [w, h]`, taken exactly — use it to taper maps by resolution |
  | `stack` | several stacked feature maps | `sheets` (2–6) |
  | `slab` | a thin layer (1×1 conv, Norm) with a rotated label, inside detail panels | — |
  | `tokens` | a token sequence | `tokens` (count); optional `values` (one number in [0, 1] per token) shades each cell — draw unequal weights (attention α, scores) instead of saying them |
  | `op` | operator circle: `op` = `add`, `mul`, `matmul`, `concat`, `reshape`, `gelu`; label empty | `op` |
  | `image` | a real image (centre-cropped to its box, never stretched) | `asset: {"path", "status": "provided" \| "from-code"}`, optional `size: [max_w, max_h]` |
  | `placeholder` | a missing image, drawn as an empty image frame with its short `label` (e.g. `CT slice`) | `asset: {"status": "requested" \| "placeholder", "spec": "what to supply"}` — the `spec` goes to the report, never into the drawing; `size: [w, h]` gives the frame's size (else ¾ aspect) |
  | `icon` | a vector icon from `assets/icons/` (Lucide, ISC licence; only `snowflake` and `flame` ship today — add the Lucide SVG there before using another name) | `icon` |
  | `text` | a free text label | — |
  | `glyph` | a symbol for what boxes cannot show: `graph` (a node and its neighbours; `nodes` 3–8, centre in the accent), `database` (a store / retrieval index), `prototype` (a learned prototype or query vector), `heatmap` (an attention / similarity map), `mask` (a segmentation label map), `kspace` (k-space with its sampling `pattern`: `cartesian`, `radial`, `random`) | `glyph`; `heatmap`, `mask` and `kspace` are schematic — set `"illustrative": true` (dashed frame; lint `schematic-unmarked` otherwise) and say "schematic" in the caption; a real image of the data goes in an `image` node instead |
- `size` is in final drawing units (the text fit scales fonts and strokes, not sizes you set). Tensors and stacks
  take it exactly; boxes only grow to it (their text must fit); images fit inside it.
- Softmax and other named functions are plain `box` nodes labelled `Softmax` — not operator circles.
- `role`: `proposed`, `reused`, `io`, `data`, `loss`, `op`, `annotation`. Reused parts recede automatically.
- `badges`: `frozen` (snowflake), `trainable` (flame).

## Edges
```json
{"src": "enc1", "dst": "dec1", "kind": "skip", "label": "concat", "src_side": "auto", "dst_side": "auto"}
```
- `kind`: `data`, `skip` (dashed), `loss`, `train_only`, `infer_only`, `grad`, `control` — each drawn differently and
  listed in the legend; never encode a difference by colour alone (lint `edge-kind-color-only`).
- `src_side` / `dst_side` pin the port when the auto choice routes badly.
- `id` (optional, e.g. `"e_rtg"`): give one whenever the figure plan's `drawn_as` names the edge (a component drawn
  as its label); otherwise ids are assigned in order and shift when edges are added.
- `label` reserves space: a label on a horizontal edge widens that gap, on a vertical edge it adds height. Prefer
  short labels (`E`, `concat`, `1×1`); long ones belong in the caption.
- An edge may end on a group (container) — it attaches to the frame; for the facts check, reaching a container
  reaches everything in it.
- Facts follow data-flow kinds (`data`, `skip`, `train_only`, `infer_only`); a fact about a `loss`, `grad` or
  `control` edge must say so with `"kinds": ["loss"]` (etc.) in `facts.json`.

## Annotations
```json
{"id": "stage1", "kind": "bracket", "covers": ["img_enc", "qformer"], "label": "Stage 1: representation learning", "side": "top"}
```
Brackets may overlap (two training stages sharing a module); a facts `scope` may name a bracket.
