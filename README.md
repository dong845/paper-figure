# paper-figure

A Claude Code skill (in development) that draws research method figures — overview, teaser and
module-detail diagrams — as **editable draw.io files** plus PNG/PDF, from a paper draft and/or code.
Design: `docs/superpowers/specs/2026-11-12-paper-figure-design.md`.

## Status: phase 0 (render-quality proof)

Phase 0 contains the render engine only. Blueprints are written by hand; the agents that read
drafts and code, search reference papers and build the knowledge base arrive in phase 1/2.

```
blueprint.json ─► layout (measured row/column/grid, uniform gaps, routing channels)
               ─► router (orthogonal A*, port priority, clearance, no crossings when avoidable)
               ─► draw.io XML (real containers, attached edges with waypoints, embedded images)
               ─► draw.io CLI export (PNG at 300 dpi of the venue width, vector PDF)
               ─► lint on the exported artifacts  +  independent visual critic (agents/critic.md)
```

## Usage

```bash
python3 -m paperfig build bench/phase0/restormer/blueprint.json --style depth-cv --out out/
python3 -m paperfig build BP --style soft-pastel --mix effects=depth-cv   # combine style sections
python3 -m paperfig lint out/restormer.drawio --blueprint BP --png out/restormer.png
python3 -m paperfig contact --panel "Original=orig.png" --panel "B=b.png" --out sheet.png
```

Exit code: 0 = lint passed, 1 = lint errors, 2 = invalid input (message on stderr), 3 = internal error (traceback on stderr).

Styles (`styles/`): `soft-pastel` (B), `depth-cv` (C), `editorial-minimal` (D), `drawio-default`
(A, reference only). Sections — typography, spacing, palette, shape, effects, tensor, edges, image —
can be mixed across styles with `--mix section=style`.

Requirements: Python ≥ 3.10, Pillow, jsonschema (fontTools optional, improves glyph fallback),
draw.io desktop (`PAPERFIG_DRAWIO` overrides discovery; headless Linux needs `xvfb-run`).

## What the lint checks (and what it does not)

Checks on the emitted `.drawio` and exported PNG: blueprint coverage (no missing / extra cells),
proposed-module names shown verbatim, overlaps, children inside containers, text fits its box,
edges through nodes / titles / legend, overlapping edges, kinks, crossings, smallest printed text
(heuristic: < 6 pt error, < 7 pt warning — the templates' `\scriptsize`), spacing evenness and
density (provisional thresholds), text contrast (WCAG), colour-vision-deficiency confusability
(Machado 2009), PNG/drawio consistency, pending assets.

It cannot judge taste. Every build must also be looked at, and reviewed by the critic.

## Known limits (phase 0)

- Scaling text up to meet the print size is capped at 1.6×; a row whose width is mostly text
  cannot be rescued and fails loudly — the layout has to change (fewer columns, shorter labels).
- Edge labels are placed by draw.io at the path midpoint; only adjacent-sibling gaps are widened
  for them.
- Lint thresholds marked *provisional* are not yet calibrated against measured real figures.

## Licences

Icons in `assets/icons/` are from Lucide (ISC). Reference papers and their figures are never
stored in this repository; benchmark assets live in `~/.cache/paper-figure/`.
