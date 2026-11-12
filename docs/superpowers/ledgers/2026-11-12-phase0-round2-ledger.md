# SDD ledger — plan: docs/superpowers/plans/2026-11-12-phase0-round2.md
Setup: branch phase0-round2 off main 129d330. Pre-flight: T2 shapes.py transforms consumed by T4/T5 (drawio+lint); T3 bracket boxes consumed by route (obstacles) and facts scope (T1) — facts scope resolves bracket ids after T3 lands (T1 supports group scope first).
Task 1: complete — facts gate; builds without facts.json get a facts-absent warning. Ruling: entering a container reaches all its contents (data flow inside an unexpanded container is unspecified) — cost if wrong: a fact into a container's child could pass via the container edge
Task 2: complete — shapes.py transforms measured (south/north/flipH); badge on tapered trapezoid goes to the full-height side; op glyphs 1.35x
Task 3: complete — brackets in lanes (narrowest innermost), reserved as root extra pad outside channels; lint bracket-coverage + edge-through-annotation; full suite green
Task 4: complete — place:free children anchor at cell origin without resizing tracks; overlaps raise LayoutError; detail_of panels default to yellow tint; halo + 2 dashed zoom lines behind content
Task 5: complete. Task 6: complete (critic gets METHOD_TEXT + FACTS, io_audit). Evidence: round-2 facts.json run against the round-1 BLIP-2 blueprint reports exactly the user's complaints (text_in missing, image path not in stage 2) plus the omitted FC.
Task 7 (part): Restormer composite built — facts 30/30, smallest text 6.07pt (warn), 1284x1096 px (≈6.9x5.9in, ~2x the original's height: original uses ~5pt text). Rulings: free panels stack in declaration order; legend wraps; edge-label gaps include 2x arrowhead; L-elbow swaps to the free side; BLIP-2 at ICML double width (faithful 6-part flow would print ~5pt single-column)
Task 7: critic round 2 (with METHOD_TEXT) found paper-level gaps — BLIP-2: text input looked like it also fed Stage 2 (fixed: 'Stage 1 only' label + Stage 2 bracket at the bottom), loss wording; Restormer: missing 1×1 reduction after concat at levels 2-3 (labels 'concat · 1×1'), channel growth (↓2·2C/4C/8C), α in softmax, TB marked proposed. Engine: trapezoid outline ports, upright short slabs, zoom legs above containers with least-crossing cone, φ/R/C glyphs, panel-coloured label knock-outs, flat detail panels, balanced legend rows + notes, top-right badges with reserved room, lint callout-crosses-title + badge-overlaps-text.
Task 7: Ruling: dropped F0/Fd name labels on horizontal edges (they widened the top row and pushed text to 4.7pt); kept channel labels on vertical edges; refused unicode subscripts as a lint dodge — cost if wrong: stage names only in caption
Final review (round 2): opus reviewer, 0 Critical, 6 Important, ~20 Minor. Verdict "with fixes".
Final: fixed sibling-branch coverage — test_bench_facts_catch_a_missing_branch[4 cases], test_via_must_be_on_the_path, test_direct_requires_an_edge RED→GREEN (Restormer facts rewritten per Q/K/V and GDFN branch)
Final: fixed grad/loss edges treated as data flow — test_gradient_and_loss_edges_not_followed RED→GREEN
Final: fixed container hub — test_container_not_a_hub RED→GREEN
Final: fixed brackets over a framed root's title — test_top_bracket_below_framed_root_title RED→GREEN (+ lint: bracket label vs titles)
Final: fixed detail_of on a group drawing dangling legs — test_detail_of_group_draws_halo RED→GREEN
Final: added bracket-spans-uncovered warning — test_bracket_spans_uncovered_warns RED→GREEN; BLIP-2 stage 2 now covers queries (+ fact s2-query)
Final: covering path reported per fact (info fact-covered) — test_covering_path_reported RED→GREEN; suite 351/351
Final: minor (deferred): rotated-shape port test shares transforms with lint (cannot catch a wrong measurement) — make svgcheck a draw.io regression test
Final: minor (deferred): two detail panels default to the same yellow tint; duplicate detail_of overwrites
Final: minor (deferred): badge-overlaps-text ignores rotated labels; slab reserves no badge room
Final: minor (deferred): edge-through-annotation checks only the bracket label, not its line/ticks
Final: minor (deferred): label knock-out uses the flat panel fill on gradient panels (depth-cv)
Final: minor (deferred): --formats svg accepted but never written; `paperfig lint` ignores figure.style and the facts gate
Final: minor (deferred): place:free outside grids silently ignored; annotation provenance dropped; softmax op not implemented
Final: minor (deferred): facts — stepping out of a container not implemented (loud), same-container facts covered, duplicate fact ids, non-string scope crashes
Final: minor (deferred): route module globals (_EXTRA/_BORDERS) not re-entrant; dead code in annotations; L-elbow swap can double-book a side
Final: minor (deferred): corner-touching edges (+ shape) not counted as crossings; three edges on one op side crowd
Final: minor (deferred): legend "GELU activation (φ)" repeats the glyph
