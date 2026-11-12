# SDD ledger — plan: docs/superpowers/plans/2026-11-12-phase0-render-engine.md
Setup: branch phase0-render-engine off master 9542169 (new local repo, user said "start"; no worktree needed). Spec: docs/superpowers/specs/2026-11-12-paper-figure-design.md
Pre-flight:
- T1→T2..9: Blueprint/Node/Group/Edge dataclasses consumed everywhere — consistent names in plan's Core data types. OK
- T2→T4: measure(label,size_pt,bold,family)->(w,h) px; layout consumes. Ruling: sizes in recipe are px at 1:1 (drawio units); "size_pt" param means drawio fontSize units. — drawio fontSize is px-like; — cost: rename only.
- T4→T5: Placed(box,label_box,title_box) consumed by router obstacles. OK
- T5→T6: Route.points absolute; emitter writes edges in layer 1 (absolute) OK
- T6→T8: lint reads emitted XML: needs absolute boxes → lint must re-accumulate parent-relative geometry. Noted.
- T7→T9: print_px used by pipeline for --width. OK
Task 1: complete (commits 9542169..fcd537a, tests: python3 -m pytest tests/test_blueprint.py → 22 passed in 0.11s)
Task 2: Ruling: add test_measure_matches_drawio_render to Task 7 (real-export calibration of PIL widths vs drawio's browser render) — lint text-overflow shares measure(), so a systematic mismatch would hide overflow — cost if wrong: one extra slow test
Task 2: complete (commits fcd537a..33daf36, tests: python3 -m pytest tests/test_markup.py tests/test_measure.py → 19 passed in 0.10s)
Task 3: complete (commits 33daf36..2699c80, tests: python3 -m pytest tests/test_styles.py → 23 passed in 0.07s)
Task 4: Ruling: added paperfig/geometry.py (Box + segment_hits_box) shared by layout/route/lint; Placed.footprint property = box ∪ label_box — plan put Box in core types without a file — cost if wrong: none (internal)
Task 4: complete (commits 2699c80..44002b2, tests: python3 -m pytest tests/test_layout.py → 68 passed in 0.20s)
Task 5: Ruling: auto edge ids skip ids already used by nodes/explicit edges (e{i}_{k}) — U-Net fixture named nodes e1/e2 and validation rejected the blueprint; users would hit the same — cost if wrong: none
Task 5: complete (commits 44002b2..8c86b31, tests: python3 -m pytest tests/test_route.py tests/test_blueprint.py → 34 passed in 0.26s)
Task 6: Ruling: cube orientation = shape=cube;flipH=1 (exported 8 variants, flipH=1 puts depth top-right as in mockup C); added darkOpacity face shading to tensor section — cost if wrong: one style key
Task 6: complete (commits 8c86b31..55c09f7, tests: python3 -m pytest tests/test_drawio.py → 16 passed in 0.45s)
Task 7: Ruling: signature export(src, fmt, out, width_px=None, scale=None, border=12, timeout_s=120, binary=None) instead of plan's run(drawio_path, ...) — plan name was ambiguous between binary and input — cost if wrong: rename
Task 7: complete (commits 55c09f7..372aeb9, tests: python3 -m pytest tests/test_export.py → 12 passed in 10.89s)
Task 8: Ruling(process): color.py was written in the same step as test_color.py (RED not observed). Mitigation: tests assert external reference values (Sharma 2005 CIEDE2000 pairs 1/7/17, WCAG 21:1) that an incorrect implementation would not hit — cost if wrong: a colour bug the reference pairs don't cover
Task 8: complete (commits 372aeb9..45b9326, tests: python3 -m pytest tests/test_color.py tests/test_lint.py → 25 passed in 0.24s)
Task 9: Ruling: first real render showed jogs on main data edges (even port spreading) and a hooked skip edge -> router now (a) picks top/bottom (or left/right) sides when the straight corridor is blocked, (b) assigns ports by priority (data first) at the coordinate that makes the edge straight, with 10px separation — tests test_main_edge_stays_straight_when_side_shared / test_blocked_skip_goes_around_via_top_or_bottom RED→GREEN — cost if wrong: different but valid routes
Task 9: Ruling: drawio --border is in OUTPUT px (measured: 2063px wide export had 2039px content); lint min-font and png-aspect now use content width = print width - 2*12/300 in; shadows enlarge drawio bounds -> aspect slack 0..6px when shadow=1 — cost if wrong: ~1% font-size estimate error
Task 9: Ruling: grayscale confusability downgraded to one info finding (gray-confusable); CVD confusability stays warn — gray print is secondary and per-pair warnings were noise — cost if wrong: grayscale issues less visible
Task 9: Ruling: added lint edge-jog (inner segment < 8px, provisional) — kinks are what the user would see first — cost if wrong: extra warnings
Task 9: Ruling: gradient = mix(fill, tone stroke, gradient_darken) instead of RGB darkening (orange went muddy brown in C render) — test_gradient_keeps_hue_not_muddy RED→GREEN
Task 9: complete (commits 45b9326..6833e66, tests: python3 -m pytest → 214 passed in 27.30s)
Task 11: Ruling: critic dry-run (agents/critic.md) on mini returned 5 actionable issues, all engine-level; fixed with tests RED→GREEN (axis alignment of titled groups, same-side detour ports at own centre + corner inset radius+4, clearance 14px, legend below routed edges + lint edge-through-legend, peer width equalisation ratio<=1.6, reused labels regular weight in B/C) — cost if wrong: style taste (reversible in recipes)
Task 11: Ruling: first Restormer render showed residual lines hugging the Transformer-Block frame and starting under the X label -> pipeline.solve_and_route reserves 16px channels per detour on the LCA group side (2-pass layout), router adds frame walls for containers enclosing both endpoints, bottom detours penalised when an endpoint has a below-label — tests RED→GREEN — cost if wrong: slightly taller groups
Task 11: Ruling: fit_typography scales text up to 2.5x until smallest text >= 7pt; measured that text-dominated rows cannot be rescued (pt saturates), so the build fails loudly with min-font instead (test_text_dominated_row_too_wide_fails_loudly) — layout restructuring stays the designer's job — cost if wrong: none (loud)
Task 11: Ruling: EDGE_BOUNDS_PAD=11px measured: drawio export bounds extend ~11px beyond edge paths (viewBox 117 vs path bottom 105.8; 95 without the edge) — cost if wrong: ±1% font estimate
Task 11: Ruling: lint gap-uneven crashed on unhashable Edge set and skipped all groups when any edge had a label; now excludes only pairs widened for a label — test RED→GREEN
Task 11: Ruling: text-only scaling (x2.2) passed lint but looked wrong (thin strokes, tiny arrows/images, cramped rows) -> _scaled grows text+ink (strokes, arrowheads, tensors, images, tokens, badges, legend) by f and whitespace by sqrt(f), capped 1.6x; min-font: error <6pt, warn 6-7pt (both heuristic, labelled) — cost if wrong: threshold taste
Task 11: Ruling: router tries every clearance and keeps the cheapest (early exit at Manhattan+2 bends) — first-success at 14px produced loops in a tight grid (test_diagonal_neighbours_in_tight_grid_get_short_route RED→GREEN)
Task 11: Ruling: Restormer blueprint as designer: single tone for all Transformer blocks (6 tones were CVD-confusable), arch grid gap tight, thumbnails 96x54 -> smallest text 6.8pt (warn band) at CVPR double width
Task 11: Ruling: detour side choice now avoids sides other edges attach to (BLIP-2 LLM->text crossed Q-Former->LLM) — test_detour_prefers_side_without_other_edges RED→GREEN; designer: frozen image encoder + LLM share one tone, orange only for the trainable Q-Former
Task 11: Ruling: critic round 2 (4 reviews) -> engine: drawio mirrors exit/entry X of flipH shapes (measured with 9-point export grid) so tensor ports are mirrored in emitter and lint; diagonal neighbours get one L-elbow with the vertical leg on the upper box; repair pass re-routes edges with crossings/>3 bends/>1.8x detour over all 16 side pairs; group axis_of aligns specific descendants across groups; grid rows align on shape centres; inline <b> respected; reused strokes muted 45% to gray and 0.75 width; badges inside corner; plain panels flat in depth-cv; arrowheads grow with sqrt(ink); edge labels at the middle of the longest segment; crossings now warn — all with tests RED→GREEN
Task 11: Ruling (designer): BLIP-2 at ICML single column stacks Stage 1 over Stage 2 — measured side-by-side variants at 5.6pt and 4.7pt (error) vs stacked 7.0pt; Restormer assets cropped to the subject (watermark/EXIF strip removed), enc->dec skips labelled 'concat'
Task 11: Deferred (taste/scope): restrict depth effects to proposed only; compact Restormer by placing the Transformer-Block panel into the U's empty bottom-right; callout connector from level boxes to the TB panel; route clearance from dashed frame borders (BLIP-2 bracket runs ~4px from frames)
Task 11: complete (commits 2699c80..28e2c58, tests: python3 -m pytest → 257 passed in 34.90s)
Final review: opus reviewer, 0 Critical, 6 Important, 9 Minor. Verdict "with fixes".
Final: fixed EXIF-rotated photos squashed — test_exif_rotated_photo_gets_portrait_box RED→GREEN, suite 270/270
Final: fixed extreme-aspect images stretched — test_extreme_aspect_image_is_cropped_not_stretched + test_build_reports_cropped_image RED→GREEN
Final: fixed truncated/non-image assets crash without path; CLI crash looked like lint failure — test_truncated_image_rejected_with_path, test_non_image_file_rejected_with_path, test_cli_unexpected_exception_has_distinct_exit_code (exit 3) RED→GREEN
Final: fixed png-mismatch false errors on small figures — test_single_node_figure_has_no_png_mismatch[depth-cv] RED→GREEN (absolute 30px slack per dimension)
Final: fixed repair trading crossings for overlaps / bending main edges — test_repair_does_not_create_collinear_overlaps, test_repair_never_makes_global_badness_worse, test_lint_collinear_overlap_is_error RED→GREEN (global badness acceptance, low-priority edges move first, unrelated overlaps = error)
Final: fixed min-font ignoring sub/sup; SCRIPT_SCALE 0.75->0.83 calibrated against drawio render — test_min_font_uses_script_run_size, test_script_scale_matches_drawio_render RED→GREEN
Final: minor (deferred): second badge on one node covers the label (frozen+trainable together should be rejected)
Final: minor (deferred): arrows stop 4-5px short of op circles when two edges share a side (ports on bbox, not ellipse)
Final: minor (deferred): no lint clearance check; routes may run ~2-3px from box borders (also BLIP-2 bracket near dashed frames)
Final: minor (deferred): compressed .drawio files give 46 coverage-missing errors instead of "compressed not supported"
Final: minor (deferred): layout+routing computed twice per build (fit loop result not reused) — ~19s of 40s on a 35-node figure
Final: minor (deferred): edge-jog finding not marked provisional in the report
Final: minor (deferred): blueprint has no style / flow-direction fields (spec §5); blueprint alone cannot reproduce a build
Final: minor (deferred): --formats silently ignores unknown values (svg)
Final: minor (deferred): ledger quoted Restormer smallest text 6.8pt; current build is 6.56pt (warn band)
Final: Ruling: container moved in the draw.io GUI — edges sit in layer 1 with absolute waypoints, so moving a group may leave waypoints behind; not verifiable via CLI — stands for phase 0, user to check by hand — cost if wrong: manual waypoint cleanup after moving groups
Final: Ruling: Linux/Windows font metrics untested — spec §8 says macOS first — cost if wrong: box overflow on other OSes that the lint (same measure()) would not see
Final: Ruling: Electron helper processes after a timeout kill not verified — cost if wrong: stray processes after a hung export
Final: Ruling: taste (palette, spacing, Restormer's empty bottom-right) — belongs to the user's phase-0 gate
Final: Ruling: min-font bands (<6 error, 6-7 warn) stand — heuristic, documented; kits state no figure-text rule
Final: Ruling: icon name joined to assets/icons unsanitised stands — only local .svg can be read
Final: Ruling: edge from above into a titled group's child routes around the title band — stands (defensible)
Final: Ruling: scale beyond 35 nodes / 45 edges unmeasured (35/45 builds in ~40s) — cost if wrong: slow builds for very large figures
Final: Ruling: color.py RED-not-observed process ruling stands (reference-pair tests)
Final: Ruling: phase-1 scope items (agents, KB, review/ dir, blind protocol) out of phase 0
