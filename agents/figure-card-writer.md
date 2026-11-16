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
2. Write `OUT` (schema: `schemas/card.schema.json`) with every field except `measured` filled:
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
   - Optional, only when `insights` / `arrangement` do not already say it (no code reads them): `grouping` — how
     parts are grouped; `shapes_depth` — box style, 3-D or flat, how tensors are drawn; `proposed_highlight` — how
     the paper's own modules stand out.
   - `elements` — from the schema list (`thumbnail`, `icon`, `equation`, `feature-map-3d`, `token-sequence`,
     `shape-labels` for tensor sizes like H/2×W/2×2C, …); `notes` may describe anything the fields do not hold.
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
   - `taxonomy` — the method facets, in `kb/taxonomy.json`'s vocabulary:
     - `family`;
     - `paradigm`, spelled as in `paradigms`, plus `paradigm_source: true` when this paper is that source;
     - `architecture`, `training`, `modality`, `depicts`, `task`;
     - `other` plus a `note` when nothing fits.

     A run finds this figure by these facets (`kb match`), so tag the method the figure draws, not the paper's
     topic.
   - `insights` — one specific sentence each:
     - `structure`: how the parts are arranged and grouped;
     - `data`: how inputs, outputs and intermediates are drawn;
     - `emphasis`: how the contribution stands out;
     - `flow`: reading order and how lines run;
     - `avoid`: a weakness not to copy, or `null`.

     Name what is drawn and where, never "clean design".
   - `structure` — what the figure draws as structure (`references/derive.md`; `kb forms` finds figures by it):
     - `core`: `relation` (the one relation the figure makes visible first — `sequence`, `pairing`, `shared`,
       `streams`, `stages`, `iteration`, `fusion`, `retrieval`, `on-structure`, `zoom`, `alternatives`) and `what`
       (that relation and the form it takes, e.g. "image and text towers face each other across one similarity
       matrix");
     - `relations`: every relation it draws, each with its `form` in one specific clause ("three unrolled phases,
       the k-th opened in a panel below, tied by a dashed callout");
     - `channels`: what `colour`, `shape`, `line`, `frame` mean in this figure ("colour = modality") — say when one
       channel carries two meanings;
     - `quality`: `score` 1–5 judged on derive.md's five principles (5: the core relation is visible as geometry,
       one meaning per channel, the compared representations drawn, space follows novelty, short straight lines),
       `strengths` and `weaknesses` — specific, never "clean".
   - `fetch` — `{"arxiv_id": …, "figure": N}`, or `{"pdf_url": …, "key": …, "figure": N}` for an open-access PDF.
     Add `page` when known. With this, the figure can be downloaded again and no image is stored.
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
   In `MODE=repo`, write `OUT` under `cards/` and run `$PAPERFIG kb validate` instead.

## Never
- Invent colours (the palette comes only from `kb measure`), components, or text you cannot read.
- Paste the caption beyond a few words, or embed or link the crop image in the card.
- Describe the method's content beyond what the drawing shows: the card is about how it is drawn.
