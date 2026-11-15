# Deriving the figure from the method — before, and without, any reference

Read this at step ③, before `concepts`, and write its result into the plan's `structure`. References come after:
they calibrate a derived design (density, glyphs, the field's conventions); they do not supply it.

**Why this file exists.** A reference that draws this method's structure will often not exist — a new method is new
— and a rulebook built from past corrections ("a two-tower model is a butterfly", "the text card goes above its
matrix") only covers the papers it was written on. Every correction the user made so far reduces to five
principles. A figure derived from them is right for a paper no rule has seen; a figure copied from the nearest
reference is right only when that reference happens to share the method's structure (six runs on one paper copied
CLIP-like neighbours and lost to the author's own draft each time; the author's draft follows the principles).

## Five principles
1. **Position shows the method's relations.** Position is the strongest visual channel (Bertin; Cleveland &
   McGill); spend it on the relation that matters most. Order of operations → reading direction. *What is compared
   with what* → the two sides face each other across the comparison. Parallel variants → identical panels side by
   side. Zoom → an enclosed detail. A reader who covers the labels should still see what comes first, what meets
   what, and what belongs together.
2. **One channel, one meaning, everywhere.** Colour says what *kind* of thing an element is (an image-side
   embedding, a text-side one, a pooled prototype); shape says data vs operation vs store; line style says data vs
   training-only vs inference-only; a frame says "one unit". Never two meanings on one channel (an orange fill and
   an orange "ours" ring), never one meaning on two channels without need. Each code is keyed or obvious.
3. **Draw the nouns, not only the verbs.** Objectives compare representations; modules make them. Draw the
   representations (z, h, t, a prototype) between the module that makes them and the objective that compares
   them, and the data as data (a real sample, a quoted sentence). A wire from an encoder straight into a loss
   hides what is compared. **Names, not formulas:** a block carries its name and at most the variable it produces
   (z, h, soft(·, θ)); an equation is drawn as its terms (elements and edges), never typeset into a block — about
   2 % of 366 published figures put a formula in a block (lint `formula-in-block`).
4. **Space and salience follow the reader's questions.** The 5 s / 30 s / 2 min levels decide what is big: the new
   part is the biggest or most saturated thing, the routine part compact. Each panel has one job (teach, extend,
   compare); a vocabulary is taught once and reused compactly. Method-defining detail is never dropped to save
   space — the figure grows instead, within a page.
5. **Paths are short, straight, aligned and continuing.** A line that bends round a block says the block is in the
   wrong place; a line into a block and the line out of its far side continue on one line; a side signal (scores,
   a mask, a temperature) is a label at the block that uses it, not a wire across the panel.

## Relations → forms (pick per relation; the core relation's form fixes the skeleton)
| relation in the method | form | engine |
|---|---|---|
| a chain of transformations | one axis, reading direction (left → right; bottom → top for towers) | `row` / `column` |
| a comparison or matching: an objective pairs A with B | A's side and B's side face each other with the objective between; when *which pairs are positive* is the point, the objective is a matrix (rows A, columns B) | `grid` butterfly; `pair-matrix` |
| several objectives over the same two sides | one row per objective between two towers; or, where the objectives are taught, a row of matrices under one bar of the shared side | `grid` with spanning towers |
| one representation feeding several objectives | one box spanning exactly the rows it feeds | grid `span` (stretches) |
| streams trained side by side | stacked enclosed lanes, equally wide | root `canvas`, framed lanes |
| stages in time / a cascade | panels left → right, a reused module the same shape and fill in each | framed `row` |
| iteration / recurrence | 2–3 unrolled steps (columns of the same unit); a cycle only when the loop is the method | `row`; `cycle` |
| fusion / conditioning | lines converging on one node; an added signal on its own bus from the side | `bundle` |
| retrieval / memory | the store beside the main flow, the retrieved items drawn as data in their own colour | `glyph` database / documents |
| the method acts on a structure (graph, points, patches, k-space) | draw the operation on a small instance of the structure | glyphs, toy graph |
| hierarchy / zoom | the overview, plus a detail panel tied by matching tint | `detail_of` |
| alternatives (ours vs prior, variants) | identical panels side by side, ours last | `parallel-panels` |

## When the forms pull against each other
The core relation's form is never traded away — it is why the figure exists. Below it, in this order: the page
(fits one page, 7 pt), then a secondary relation's form, then aspect and density norms (`aspect-tall`, `ink-heavy`
are calibration, not rules). So when a secondary pairing and `aspect-tall` cannot both clear, keep the page and the
core form, give the secondary form a try in one other place, and report the one you kept and why (ISTA-Net no-ref
run: the training loss's inputs came from two rows).

## Recipes for forms the engine needs help with
- **One unit drawn several times** (unrolled phases, a module per stream): the copies need ids of their own — a
  drawn node may not carry the component's id. Name them (`phase_1`, `phase_k`, `phase_np`) and map the component
  to all of them in the plan: `drawn_as: [{"ids": ["phase"], "into": ["phase_1", "phase_k", "phase_np"], "how":
  "unrolled"}]`; a fact between consecutive steps (x(k) → r(k+1)) is then checked across the copies.
- **The opened copy** (the k-th phase expanded below the strip): a `detail_of` group for that copy; the copy in the
  strip stays collapsed, tied to the panel by matching tint.

## The derivation (the plan's `structure`)
1. **Entities** — from the analysis: inputs, modules, representations, objectives, stores.
2. **Relations** — every one, by type from the table: `sequence`, `pairing`, `shared`, `streams`, `stages`,
   `iteration`, `fusion`, `retrieval`, `on-structure`, `zoom`, `alternatives`, each with the ids it relates.
3. **Core relation** — the one relation that makes this method different from its family; the reader must see it
   in 30 s. It gets position and the most space.
4. **Forms** — one per relation from the table; the core relation's form fixes the skeleton (the main axis and
   what faces what), the others fit around it.
5. **Channels** — `colour`, `shape`, `line`, `frame`: one meaning each (these become `color_semantics`).
6. **Budget** — per unit: its job (`teach` / `extend` / `same` / `compare`) and roughly what share of the area.
7. **Calibrate** — only now look at the references: does a published figure draw the same core relation? Take
   its craft (glyphs, density, the field's reading conventions — CLIP's matrix is how readers expect pairing to
   look). Where a reference disagrees with the derivation on structure, the derivation wins and the plan says why.

## Check without a reference (you and the critic)
- Cover the labels: does position alone show the order, what meets what, and what is new?
- List each colour, shape and line style with its meaning: does any carry two?
- Is every compared representation drawn between its maker and its objective?
- Is the biggest or most saturated element the contribution?
- Any bend, detour, near-continuation or side signal drawn as a long wire?
