# Arrangement — how strong method figures are laid out

Read this before writing the plan's `layout` (step ③) and again before the blueprint (step ④). It is what the
skill learned when the user compared a blind run with their own figure for their (unpublished) two-stream
pretraining paper (2026-11-15). The run's figure could be understood, but it lost on arrangement, and each loss
came from one decision:
- **Streams were not panels.** The text trains two streams. The author drew them as (a) and (b), each a closed
  panel holding its own inputs, encoders and losses. The run put one stream in a band and left the other unframed.
- **A stream's losses were not drawn in it.** In the text, every term of the first stream also trains the second
  (its total-loss equation and loss table say so). The run drew them once, in one stream.
- **Lines crossed between units.** They ran from one stream into the other stream's objectives, and the text
  encoder's line looped over the top into a panel.
- **The key sat in the middle.** The legend was placed in a hole between the two parts.
- **Inputs were grey boxes.** They sat partway into the figure. The author put real photos and quoted sentences at
  the outer edge.

The rules below come from three sources:
- **15 published figures, studied for this:** ALBEF, BLIP, BLIP-2, MGCA, CycleGAN, UniCL, DreamBooth, BYOL,
  data2vec, GLIP, DETR, CoCa, ImageBind, MedCLIP and CLIP. Their cards now record an `arrangement`.
- **Perception research:** Bang Wong's Nature Methods *Points of View* on Gestalt principles and alignment.
- **Three automatic-figure papers:**
  - **PaperBanana (2026):** reference figures raised readability more than any other part, and random references
    helped nearly as much as well-matched ones. Structure transfers across topics.
  - **SciFig (2026):** a layout stage plus a layout critic raised structural consistency from 6.0 to 8.6 out of 10.
  - **AutoFigure (ICLR 2026):** a critic that checks alignment, balance and overlap.

**Why learn arrangement from a reference rather than invent it:** without references, PaperBanana's planner "defaults
to verbose, exhaustive descriptions", and our blind runs did the same with layout. A composition invented each time
has no reason behind its partition, so the content's own structure (streams, stages, objectives) gets lost. The rule:
copy a published figure's top-level arrangement, put this paper's content into it, and depart from it only where
the content demands.

## 0. Size is not the limit — detail and clarity are
The user's words (review of the v3 run, 2026-11-15): "don't take the easy way; make the figure bigger to expand the
detail; the figure's size is never the limit; what matters is that it is intuitive, easy to understand, and keeps
the detail." The 7 pt floor holds at print width, so when content does not fit, the figure grows: more rows,
taller lanes, a full-width figure, a bigger matrix. It never shrinks by merging components, collapsing losses into
one box, dropping inputs, or deleting secondary text. `aspect-tall` is not reported for `lanes` / `lane-grid`.

**But the page is a limit.** A figure must fit on a page: lint `page-overflow` (error) above ~8.5 in printed
height, `page-share` (warn) above ~6 in. The next run read "size is not the limit" as "no limit" and stacked every
matrix in a column: 14 in tall. The author's own figure holds the same content at ~4.8 in by its arrangement.
When the figure is too tall, rearrange in this order before cutting anything:
1. **Matrices in a row, under a horizontal text-encoder bar.** This is CLIP's form and the author's: the text
   encoder is a full-width bar above, with a short drop into each matrix's column header; the image side enters
   from the left. One row of four matrices costs the height of one matrix. A column of four costs four.
2. **Units side by side** when each is narrow (BLIP, UniCL, CycleGAN).
3. **Split:** the overview in this figure, a mechanism in its own figure (`paperfig split`). The overview keeps
   every stream and every method-defining loss.
The validator also refuses two shortcuts the run took:
- **one box standing for several of a stream's method-defining losses** ("L_fdn as in (a)");
- **two components merged into one box** in one place ("F_I, F_T (shared)") while the figure draws them apart
  elsewhere. Two towers stay two towers in every unit.

## 0b. Each panel has a job: teach the vocabulary once, then extend it (the author's draft, studied 2026-11-15)
Six runs (v1–v6) of the same two-stream paper each lost to the author's own draft; the user asked to study why the
draft is drawn as it is. The draft is not one recipe applied twice. Its two panels do different jobs and use
different pictures:

| | panel (a), the base stream | panel (b), the stream that extends it |
|---|---|---|
| its job | **teach** what each objective is | **show what is new** (a retrieval step, an aggregation module, a new loss) and that every earlier objective still trains |
| objectives drawn as | full `pair-matrix` glyphs, 5×5, rows and columns named, positives meaningful | **small loss boxes** ("L<sub>cap</sub> · 1:1") — the reader learnt the matrices in (a) |
| geometry | CLIP's: images enter the rows from the **left**, texts drop into the columns from the **top** (a text-encoder bar with each text card above the matrix it feeds) | a **butterfly**: image tower on the left, text tower on the right, the **loss boxes in one central column**, each loss box fed by one arrow from each side |
| inputs | images at the left edge, quoted cards along the top | the query image and the retrieved samples at the left edge, quoted cards at the right edge, each card at the height of the embedding it produces |

What makes it read so easily, and what the runs did instead:
1. **The arrangement is the pairing.** A contrastive loss pairs an image-side embedding with a text-side one. In
   (b) the two sides face each other and meet in the middle, one row per loss, so each loss is literally between
   its two inputs. The runs put the image encoder under and the text encoder over a row of matrices, so every
   pairing became two long vertical lines (and the image-side ones kinked round the matrix names).
2. **Teach once, then abbreviate — but never hide.** Every loss of (b) is still its own box with its own two
   arrows (nothing like "as in (a)"), yet it costs one row, not one 5×5 matrix. The runs read "draw every loss in
   every stream" as "repeat every matrix", so (b) became a second copy of (a) with the new parts squeezed in. Space
   goes to what the panel is about: in (b) the retrieval step, the retrieved samples and the aggregation module.
3. **Embeddings are drawn between encoder and loss** — z (CLS), h (patch-level), t (captions), y (class sentence),
   c (attribute sentences), a query embedding, a pooled prototype. They are what the loss compares. The runs wrote "z: projected [CLS] token · H: patch
   tokens" inside the encoder box and ran lines from the encoder straight to the losses, so the reader never saw
   what is being paired. Show a readout's recipe where it is defined ("patch tokens → mean → MLP → h" in (a)).
4. **One embedding box spans the losses it feeds.** z (CLS) feeds three losses, so it is one tall box covering
   those three rows; each arrow is a short horizontal line. Encoders in the butterfly are tall bars spanning every
   row. In a `grid`, a box whose `span` covers several rows is stretched to cover them (engine).
5. **Colour means the kind of embedding,** the same in both panels and in the matrix headers: image / CLS green,
   patch-level orange, text purple, pooled prototype yellow, losses white or grey; the key at the bottom lists
   those kinds plus positive / negative pair. Text *cards* may differ in tint per kind of text, but the embeddings
   they produce take the text colour. The v6 run coloured every text kind differently all the way into the matrix
   headers: 8 colours, `palette-busy`, and colour no longer said what kind of vector a row is.
6. **One plain line style.** The lines into objectives are ordinary data arrows — the box or matrix at the end says
   "loss". A figure whose every arrow into an objective is red-dashed is loud everywhere and the red means nothing
   (v6: ~20 red dashed lines).
7. **No long detours.** A readout that feeds the second matrix of a row cannot reach its row names from the left
   without passing the first matrix. Put that readout under the first matrix and let it enter the second from
   below (the engine lands a line from below on the row-name column, beside the matrix name); feed the first
   matrix from the left.

8. **A side signal is written where it is used.** A value a module consumes from far away (retrieval scores, a
   temperature, a mask) is a label on the consumer ("k × e<sub>i</sub>, s<sub>i</sub>"), not a line across the
   panel: v7 ran its scores along two panel margins into the aggregators. The draft draws none.
9. **Short titles, a key, one meaning per hue.** Panel titles name the unit as the text does ("(a) Base stream ·
   training only"); loss sums go in the caption — v7's titles were the widest lines in the figure and cost it the
   7 pt floor (lint `title-long`). With matrices drawn, keep the key: it lists positive / negative pair at the
   edge (lint `matrix-unkeyed`). The hue that rings the contribution fills nothing else (lint `ring-hue-reused`):
   v7 filled the patch readout in the ring's orange.
10. **Lines continue straight through an element.** card → encoder bar → matrix is one straight line; the engine
   puts both on one coordinate when both ends allow it, and lint `through-offset` reports a near miss.

**How to use this on any paper:** for each panel, write its job in the plan (`units[].job`: "teach the objectives"
/ "show the new path"). A panel whose job is to extend an earlier one reuses the earlier vocabulary in
compact form and spends its space on the new parts. A two-tower method with several objectives per stream is a
butterfly in the panel where the objectives are not the subject.

## 1. Partition first: the top level is the text's own structure
Decide the partition before placing anything. The figure's first level of enclosed regions mirrors the method's first
structural split, named as the text names it ("(a) Online branch", "Stage 1: …").

| the text has | partition | exemplars (card ids) | how it looks |
|---|---|---|---|
| two or more **streams / branches** trained side by side (alternating steps, teacher / student, two views, two data sources) | `lanes` | `dreambooth-2022-fig3`, `glip-2021-fig2` | one horizontal band per stream, stacked; each band runs left to right from its inputs to its own losses |
| streams **and** stages | `lane-grid` | `byol-2020-fig2`, `data2vec-2022-fig1` | rows = streams, columns = stages; the same stage sits in the same column in every row |
| **stages** run one after another (pretrain → finetune, coarse → fine, backbone → heads) | `stage-panels` | `detr-2020-fig2`, `blip-2-2023-fig2`, `clip-2021-fig1` | one framed panel per stage, left to right, titled at its top |
| several **objectives or variants** with the same skeleton | `parallel-panels` | `blip-2022-fig2`, `unicl-2022-fig3`, `cyclegan-2017-fig3`, `coca-2022-fig1` | identical panels side by side, one per objective; only what differs is drawn differently |
| one pipeline, nothing to separate | `single` | `albef-2021-fig1`, `mgca-2022-fig2`, `reflexion-2023-fig2` | one composition; sub-groups for modules |

- **A unit is an enclosed region:**
  - its forms: a frame (box or dashed), a tinted band, or a panel set off by a thin rule;
  - its title, as the text names it;
  - (a), (b) in the text's order.
  - *Why:* enclosure is the strongest grouping cue. It beats similarity, proximity and connection (Wong, Gestalt
    part 1). A unit without one is read as part of its neighbour.
- **The hierarchy has three levels:**
  - units (streams, stages);
  - sub-groups (one module and its parts);
  - leaves.
  - Interior frames are lighter than unit frames. SciFig's planner uses the same three levels.
- **Each unit reads on its own.** A reader should understand stream (b) without tracing a line from stream (a).
  Lint `unit-crossing` warns on any line between units that the plan does not declare in `layout.links`.

## 2. Each unit owns its losses
- **A loss sits at the end of the unit it trains:**
  - at the top of its tower (BLIP, ALBEF);
  - at the right edge of its lane (GLIP);
  - as a dashed arc along that lane's outer edge (DreamBooth: one loss along the top, the other along the bottom).
- **Which losses must be drawn** (user's choice, 2026-11-15):
  - **must:** losses that define the method — contrastive or matching objectives (what is a positive is the
    supervision), the paper's own new losses, and the plan's `supervision` ids. They are drawn in every stream
    that optimises them, each as its own element.
  - **may go to the caption:** conventional objectives the field draws without (reconstruction, KL, actor-critic
    losses). DreamerV3's authors drew none, and a blind run that boxed them all came out busier than the original.
- **A term that trains two streams is drawn in both,** for example when the text's total loss for stream (b) adds
  terms to stream (a)'s. Read the total-loss equation and any loss table, not only the paragraph that introduces the
  stream. The analysis records this as `stages[].losses`. The validator checks that every listed loss is drawn
  inside its stream's unit, or that `layout.not_drawn` gives the reason it is not.
- **A loss that compares two streams is drawn once, where the streams meet.** BYOL draws its loss at the right end,
  between the online and target rows. Declare it in `layout.links`.
- **Objectives that differ only in their positive pattern use identical panels.** Draw one `pair-matrix` per
  objective, all the same size, side by side or in a column (UniCL, CLIP, the author's figure). Only the blue cells
  differ.
- **Full matrices once, compact loss boxes after (§ 0b).** The panel that teaches the objectives draws them as
  matrices. A later panel that reuses them draws each as its own small loss box (`role: "loss"`, "L<sub>cap</sub>
  <br>1 : 1") with one arrow from each side — every loss still present and still fed by its own inputs, at one row
  each. Repeating every matrix in every panel is not what "draw each loss in each stream" means.

## 3. Shared modules: one copy per unit, not one box serving two units
When both streams use the same encoder, draw it in each unit, in the same column, and mark it "shared" in its
label or `<small>` line. DreamBooth joins its two copies with a short "Shared Weights" double arrow. The tempting
alternative is one box with lines from both streams running into it. That alternative produces the crossing lines
and the unreadable middle. A copy costs one box; a crossing costs the reader the partition.

## 4. Inputs at the outer edge, as the data
- **Where inputs go:** at the edge where the flow starts. That is the left for left-to-right figures, or the bottom
  for towers that rise (BLIP, ALBEF, CoCa).
- **Where the text input goes in a two-tower figure:**
  - on its own side;
  - or above the text encoder, as in CLIP (text encoder above the image encoder), GLIP (text lane on top) and the
    author's figure (a horizontal text-encoder bar above the matrices, dropping an arrow into each matrix's
    column header).
  - **When matrices stand in a row under the text-encoder bar, each text card stands above the matrix it feeds**
    (caption over L<sub>cap</sub>, label sentence over L<sub>lab</sub>, concept sentence over L<sub>con</sub>), all
    in one row above the bar, so card → bar → matrix is one vertical line per kind of text. Don't stack the cards
    in a column at the side and join them with a trunk (v6): the reader then has to match colours to find which
    text feeds which matrix. Build it as a row of cards whose children `align_x` to their matrices, or as columns
    of [card, matrix] pairs with the bar spanning them.
- **Text inputs are quoted cards, one tone per kind of text** (`visual: "textcard"`, `card_style: "quote"`): a
  dashed card tinted with the source's tone. Its label has two parts:
  - the real example in italics: `<i>“… diagnosed as …”</i>`;
  - a small role line: `<br><small>label sentence · 1 per label</small>`.

  Caption, label sentence, concept sentence and query report each get their own tone, named in
  `color_semantics`. The reader tells the text sources apart at a glance and sees what each one is, as in the
  user's own figure.
- **No data-preparation provenance in the figure.** Show the sentences the model reads, not how they were made: no
  "templated by X" step, no prior-work name on an arrow (a run drew a "templated by <prior work>" arrow into its
  sentences; the user: just the text input). That provenance belongs in the caption.
- **What inputs look like:**
  - real samples: a small stack of photos with offset copies behind for a batch (CLIP), or one real photo per
    stream;
  - quoted sentences: one per text source, with a small grey role line under it ("caption · 1 per image", "label
    sentence · 1 per label").
  - A grey "image" box is a placeholder for a sample the author supplies (step ⑤ asks them first). It is never the
    design.
- **Outputs and objectives go on the opposite edge** (right or top).

## 5. Lines: short, straight, inside their unit
- **If a line needs a long detour, a block is in the wrong place.** Move the block, not the line.
  - Example: the text encoder belongs above the matrices it feeds, so its arrows drop straight down. It does not
    belong beside them with a loop over the top.
- **Fan-out from one input:** use a comb, one trunk with short drops (CLIP, BLIP's caption to three towers).
  Blueprint: `bundle`.
- **Feedback, losses and training-only loops:**
  - run along the unit's outer margin as dashed arcs (DreamBooth, data2vec);
  - never across the middle of another unit.
- **Use fewer line styles:**
  - solid for data — including the embeddings flowing into a drawn objective (a matrix or a loss box): the element
    at the end already says "loss", so these are `kind: "data"`, not red dashed `loss` lines (§ 0b, 6);
  - one dashed style for training signals that have no drawn objective at their end (a gradient, a target update);
  - label a special line directly ("hard negatives", "Shared Weights") instead of adding a legend entry.

## 6. The key: at the edge, or not at all
- **Prefer direct labels.** The strongest figures studied have **no legend**: CycleGAN, BYOL, DreamBooth, CLIP,
  BLIP, GLIP, DETR, UniCL, CoCa. Their lines and regions are labelled where they are.
- **When a key is needed,** it sits at the outer edge:
  - a right column (ALBEF);
  - a bottom-right corner box (MGCA);
  - a top strip (ImageBind, BLIP-2);
  - a bottom band (the author's figure).
- **Never in a hole between content.**
  - *Why:* a block in the middle reads as content and splits the figure in two.
  - Set it with `figure.legend_at` (`corner`, `bottom`, `right`, `top`; `auto` = a free corner, else a right column
    or a bottom band). Write the same value in the plan's `layout.legend_at`, or `none` with `figure.legend: "none"`.
  - The engine never places a key in an interior hole (test `test_legend_never_sits_between_content`).

## 7. Parallel structure and alignment
- **Repeated elements are identical** across units that do the same job: the same size, the same shape, the same
  position in each unit. A unit with a different job (it extends an earlier one, § 0b) may draw the same
  objectives in a compact form instead.
  - Examples: BLIP's towers differ only in the one block that changes; UniCL's panels differ only in their target
    matrix.
  - *Why:* similarity groups them, so the reader compares instead of decoding.
- **Align to invisible guides.** In a `lane-grid`, the same stage shares a column in every row (use `align_x`
  between lanes). Matrices in a row share their top edge. "Our eyes are acutely aware of small misalignments;
  compositions that use guides tend to look clean and professional" (Wong, Gestalt part 2).
- **Salience follows relevance.** The contribution is marked once (a ring or a name). The biggest or most saturated
  element should be the one that matters, not the decoration (Wong, *Salience to relevance*).

## 8. Building it in the blueprint
- **`lanes`:**
  - the root is a `canvas` whose children are the framed lanes (`frame: "box"`, `title: "(a) …"`,
    `title_align: "left"`), each `cell: [k, 0]` with `span: [1, <all columns>]`. Framed groups fill their span, so
    every lane has the same width and their edges line up (a root `column` leaves each lane as wide as its own
    content: the v5 run's lanes differed by ~30 px and their matrices did not line up);
  - each lane is a `row` or a `canvas`;
  - put the same stage in the same column of every lane and line them up with `align_x` (a lane's shared encoder
    under the other lane's).
- **Tall bar spanning rows** (an encoder feeding several outputs — the author's image encoder; BYOL's stage
  frames): use a `canvas` with the bar's `span` covering the rows it feeds. Boxes fill their span.
- **The butterfly** (§ 0b: two towers facing a column of objectives) is a `grid` (columns sized by their content —
  a `canvas` makes every column as wide as the widest need and spreads the figure):
  - columns: inputs · image encoder · image-side embeddings · objectives · text-side embeddings · text encoder ·
    quoted cards; rows: one per objective (a two-row objective box when it takes two inputs per side);
  - each encoder `span`s every row; an embedding that feeds several objectives `span`s exactly their rows (the
    engine stretches a box over the rows it spans, so every arrow is one short horizontal line);
  - each quoted card sits in the row of the embedding it produces; the inputs (query, retrieved samples, the module
    that retrieves them) sit in the left columns.
- **The teaching panel** (§ 0b) is a `grid` too: row 0 the quoted cards, each above the matrix it feeds; row 1 the
  text-encoder bar spanning the matrix columns; row 2 the matrices; the image encoder a tall box at the left
  spanning rows 1–3, its first readout beside the first matrix (enters its row names from the left), a second
  readout in row 3 under the first matrix (enters its own matrix's row names from below).
- **Reaching 7 pt at double width.** The binding constraint is width, so make labels narrow, not short of content:
  break a pairing line ("image ↔ own caption<br>1 : 1"), a long module name over two or three lines, a quoted
  card over two lines with a short role line; then `--mix spacing=compact --mix typography=compact`. A rehearsal of
  the author's design went from 5.6 pt to 7.0 pt this way (6.9 in tall, within a page).
- **Text encoder above the objectives** (the compact form — prefer it to stacking matrices vertically):
  - in a canvas, row 0 holds the text encoder spanning the objectives' columns, row 1 the `pair-matrix` glyphs;
  - give each matrix its own edge from the encoder (they drop straight down), or use a `bundle`.
- **`stage-panels` / `parallel-panels`:** the root is a `row` of framed groups (`order: "fixed"`), identical inside
  for parallel panels.
- **The plan's `layout`:**
  - **required fields:** `skeleton_from` (the card or reference copied), `takes`, `partition`, `why`, `inputs_at`
    and `legend_at`;
  - **optional fields:**
    - `units`: one per enclosed region, giving the group id, the analysis stage it draws (`of`), and the loss
      nodes inside it;
    - `links`: lines allowed between units;
    - `not_drawn`: losses a stream optimises that its unit does not draw, with the reason.
  - The kb brief's `arrangements` lists every card that records one, from any domain. Pick by partition and
    structure, not by topic.

## 9. Finish like the author would (v5 run vs the author's figure, 2026-11-15)
- **Size what matters by what is free.** When a panel has empty space, give it to the representation the
  reader studies: the matrices (`size`, e.g. 110×110) and their named headers (`axes: ["z", "t"]`). Don't leave
  it as margin around small glyphs. The author's matrices are the largest elements of the figure.
- **Name the rows and columns** of every pair-matrix: z₁…, t₁…, y₁…, c₁… (`axes`). They tell the reader which
  embedding meets which text, at no cost in boxes.
- **The contribution's mark is light:** a ring in the style's accent hue (`highlight: "ring"`), never a thick
  near-black frame. A black outline reads as "important block" for everything it touches and outweighs the
  modality colours.
- **No floating notes.** A note sits next to the element it explains (under the readouts, at the end of the path
  it describes), or it goes in the caption.
- **Say what each matrix pairs.** Its name has two lines: the objective, then the pairing and its cardinality —
  "L<sub>cap</sub><br>image ↔ own caption · 1:1", "L<sub>proto</sub><br>query → class prototype". "L_cap 1:1"
  alone makes the reader look the pairing up (lint `matrix-pairing-unnamed`).
- **Set the positive cells when the pattern means something** (`positives`: 1-based [row, col]). Same-class
  blocks, a row with several positives, or the same objective drawn in two panels: give the cells, so the copies
  match and the pattern shows the rule. Never search node ids for a pattern. A many-to-many pattern needs room to
  read: 4–5 rows (`grid`), not 3.
- **Lines meet a matrix where its sides are named:** the row side (images, from below) enters under the row names
  z₁…, the column side (texts, from above) on the middle of the column names. The engine does this; don't pin
  ports or hand-move labels to get it.
- **Key the cells.** A figure with matrices gets "positive pair / negative pair" in its key automatically. If the
  figure has no key (`legend: "none"`), say it in the caption.

## Checklist (the critic and the blueprint gate use it)
- [ ] The top-level units match the text's streams, stages or objectives; each is enclosed and titled as the text
  names it.
- [ ] Each panel has a job (§ 0b): the one that teaches the objectives draws them in full; a panel that extends it
  draws every objective as a compact loss box fed from both sides and spends its space on what is new.
- [ ] Embeddings are drawn between encoders and objectives; an embedding feeding several objectives is one box
  spanning them; colour means the kind of embedding, the same in every panel and in the matrix headers.
- [ ] Lines into drawn objectives are plain data lines; no long detours (a second readout enters from below).
- [ ] Side signals are labels at their consumer; panel titles are short; the key is kept when matrices are drawn;
  the ring's hue fills nothing; a line through an element continues on one line.
- [ ] Every method-defining loss (contrastive / matching, new, supervision) is drawn in each unit it trains,
  each as its own element, or `not_drawn` gives the reason; conventional objectives may stay in the caption.
- [ ] Two towers (image / text encoder) are separate in every unit; nothing is merged to save space.
- [ ] Text inputs are quoted cards, one tone per kind of text; there is no data-preparation provenance in the figure.
- [ ] With matrices in a row under a text-encoder bar, each text card stands above the matrix it feeds (no side
  stack joined by a trunk).
- [ ] No line crosses between units unless it is a declared link; shared modules appear once per unit.
- [ ] Inputs sit at the outer edge as real samples or quoted text (or placeholders the author will fill).
- [ ] The key is at the edge (or absent, with direct labels).
- [ ] Repeated elements are the same size and lined up across units; lanes are equally wide (root canvas).
- [ ] Matrices use the free space and name their rows and columns; the contribution ring is the accent hue, not
  black; no note floats away from what it explains.
- [ ] Each matrix's name says what it pairs ("image ↔ own caption · 1:1"); meaningful patterns and repeated
  matrices use explicit `positives`; the key explains positive / negative cells.
