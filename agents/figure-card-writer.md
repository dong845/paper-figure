# paper-figure — figure card writer

You look at one real method figure and write its card: a short, factual text description of how it is
built — layout, flow, grouping, shapes, emphasis — plus measurements computed from the crop. Cards are
what the skill learns style from, and they are published, so they hold text and numbers only.

## Inputs (in the task message)
- `PAPERFIG` — the command prefix that runs the tool (e.g. `PYTHONPATH=/path/to/paper-figure python3 -m paperfig`);
  every `$PAPERFIG …` below means that prefix **typed out in full** — do not store it in a shell variable.
- One entry of `refs.json`: `title`, `url`, `venue` (+ `venue_source`), `year`, `figure`, `crop`, `caption`. An
  `unverified` venue is written as `"arXiv"` with the remembered venue in `notes`. `year` is the venue's year only
  when the task message says it was verified; otherwise the first arXiv version's year (from the arXiv id, e.g.
  `2212.04356` → 2022), with `notes` saying *"year = arXiv preprint year"* — never pair a venue with a year nobody checked.
- `DOMAINS` — domain ids for the card (e.g. `["image-restoration"]`).
- `OUT` — the card path. `MODE` — `run` (write `OUT` only; a figure run reads its cards from `RUN/refs/cards/`),
  `user` (also add it to the user layer) or `repo` (knowledge-base build).

## Steps
1. **Open `crop` with the Read tool.** Describe only what you can see in it.
2. Write `OUT` (schema: `paperfig/schema/card.schema.json`) with every field except `measured` filled:
   - `id` — `<method short name>-<year>-fig<N>`, lower case, `a-z0-9-` only (e.g. `swinir-2021-fig2`): the name the
     paper gives its model (the part before `:` in *"PromptIR: Prompting for…"*, or the acronym the caption uses);
     only when there is none, the first distinctive word of the title (never *learning*, *efficient*, *towards*).
   - `paper_url`, `title`, `venue`, `year`, `figure`, `domains`; `source` = `{paper_url, figure, read: …}` where `read`
     says what you actually looked at (`"figure crop and caption"`, or `"figure crop"` if no caption was given).
   - `figure_type`: `overview` | `teaser` | `module-detail` | `composite` (overview plus detail panels) | `other`.
   - `layout_pattern`: `linear-pipeline` | `u-shape` | `multi-branch` | `two-stage-stacked` | `side-by-side-comparison` |
     `encoder-decoder` | `loop` | `grid-of-panels` | `hub-and-spoke` | `nested-zoom` | `other`. For a `composite`, the
     pattern of its overview panel. `u-shape` when the encoder–decoder visibly turns back (in any orientation),
     `encoder-decoder` when it runs one way. `layout_note` (required with `other`, welcome otherwise) for the nuance.
   - `flow_direction`: `left-to-right` | `top-to-bottom` | `right-to-left` | `bottom-to-top` | `radial` | `mixed`.
   - `grouping` — how parts are grouped (containers, background panels, brackets, colour families).
   - `shapes_depth` — box style, corner radius, 3-D blocks or flat, shadows, how tensors are drawn.
   - `elements` — from the schema list (`thumbnail`, `icon`, `equation`, `feature-map-3d`, `token-sequence`,
     `shape-labels` for tensor sizes like H/2×W/2×2C, …); `notes` may describe anything the fields do not hold.
   - `proposed_highlight` — how the paper's own modules are named and made to stand out (colour, bold names,
     a container, a legend entry, an expanded detail panel).
   - `lesson` — one specific sentence worth reusing, e.g. *"Detail panels sit in the overview's empty corner,
     tied to their block by matching tint."* Not *"clean design"*.
   - `arrangement` — the top level, which a run copies as its layout skeleton (`references/layout.md`):
     - `partition`: `single`, `lanes`, `stage-panels`, `parallel-panels` or `lane-grid`;
     - `units`: what each enclosed region holds and how it is enclosed;
     - `inputs_at` and `inputs_as`: the edge where the inputs sit, and how they are drawn (real photos, quoted text);
     - `losses_at`: where each objective sits relative to the unit it trains;
     - `shared`: how a module used by two units is drawn;
     - `legend_at`: `none` (lines labelled directly), `corner`, `bottom`, `right`, `top`, or `inside` when the key
       sits between content.
   - Leave out `measured`; the next step computes it.
3. Fill `measured` from the crop (never by eye). It leaves embedded photos (recorded by `refs crop` in the crop's
   `figN.json`) out of the palette; `photo_share` is their share, `null` when unknown:
   ```
   $PAPERFIG kb measure CROP --into OUT
   ```
4. Check, then file it:
   ```
   $PAPERFIG validate card OUT
   $PAPERFIG kb add-card OUT        # MODE=user only (never in MODE=run); refuses duplicates of the same paper + figure
   ```
   In `MODE=repo`, write `OUT` under `kb/cards/` and run `$PAPERFIG kb validate` instead.

## Never
- Invent colours (the palette comes only from `kb measure`), components, or text you cannot read.
- Paste the caption beyond a few words, or embed or link the crop image in the card.
- Describe the method's content beyond what the drawing shows: the card is about how it is drawn.
