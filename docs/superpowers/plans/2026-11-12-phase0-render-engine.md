# paper-figure Phase 0 — Render Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove figure quality: hand-written blueprint + style recipe → editable `.drawio` → PNG/PDF, gated by mechanical lint and a visual critic, rendered for 2 real papers in styles B and C and shown side by side with the papers' original figures.

**Architecture:** A stdlib-first Python package `paperfig/` inside the skill repo. Pipeline: `blueprint.load` (schema + semantic validation) → `layout.solve` (measured, flex/grid container layout with uniform gaps) → `route.route_all` (orthogonal obstacle-avoiding A*) → `drawio.emit` (mxGraph XML, nested containers, explicit waypoints) → `export.run` (draw.io desktop CLI) → `lint.check` (reads back the emitted XML + PNG) → report. Style = composable JSON recipe sections (palette × shape × effects × typography × tensor).

**Tech Stack:** Python ≥3.10, Pillow (text measurement, contact sheet), jsonschema (validation), pytest; draw.io desktop CLI for export.

**Spec:** `docs/superpowers/specs/2026-11-12-paper-figure-design.md` (§4 ⑤⑥, §5, §14 phase 0)

**Execution:** user said "start" after approving the spec → native execution in-session, one fresh whole-branch review at the end, then the phase-0 user gate (§14).

## Global Constraints

- Every blueprint node except `visual: "text"` must carry ≥1 `provenance` entry; missing → validation error (spec anti-goal: no fabricated modules).
- A node with `role: "proposed"` must show its `full_name` and/or `abbrev` verbatim in the rendered figure (spec G3).
- AI-generated imagery is never allowed for `visual: "image"` nodes; `asset.status` ∈ `provided | from-code | requested | placeholder`. `requested`/`placeholder` render as a visibly dashed "ASSET NEEDED" box and are listed in the report.
- Lint must read the **emitted .drawio XML and exported PNG**, not the in-memory model (spec: "看真实产物").
- Thresholds not backed by a source are labeled `provisional` in code and in the report text.
- drawio data-URI images use `data:image/png,<base64>` (no `;base64` — `;` is the style delimiter).
- Venue widths (verified 2026-11-12 from official kits): NeurIPS 2025 textwidth 5.5in; ICLR 2026 textwidth 5.5in; ICML 2025 textwidth 6.75in, columnsep 0.25in; CVPR textwidth 6.875in, columnsep 0.3125in. Body font 10pt for all four; heuristic min figure text = the template's `\scriptsize` = 7pt.
- No hard-coded user paths; drawio binary discovered via `PAPERFIG_DRAWIO` env → `drawio` on PATH → platform defaults; missing → `ExportError` with install hint.
- Reference PDFs / original figures live only under the cache dir (`~/.cache/paper-figure/`), never in the repo (spec §6.3).
- git: stage named paths only; no push.

## Review Focus

1. **Long, multi-line, sub/superscript and CJK labels** — box must grow to fit; lint must flag any overflow. (Task 2 `test_cjk_measured_wider_than_latin_fallback`, Task 8 `test_text_overflow_flagged`)
2. **Dense skip connections (U-Net style)** — edges must not pass through unrelated nodes or run on top of each other. (Task 5 `test_unet_skips_do_not_cross_nodes`)
3. **Image assets with extreme aspect ratios, missing or unreadable files** — clamp size, keep aspect; missing file → validation error naming the path. (Task 1 `test_missing_asset_file_rejected`, Task 4 `test_extreme_aspect_image_clamped`)
4. **draw.io CLI absent, hanging, or producing no file** — loud `ExportError`, timeout, never a silent success. (Task 7 `test_missing_binary_raises`, `test_timeout_raises`)
5. **Edges that touch containers** (edge into a group, edge between nodes in different groups, edge from a node to its own ancestor) — routed through the right borders; node→own-ancestor rejected at validation. (Task 1 `test_edge_to_own_ancestor_rejected`, Task 5 `test_edge_into_container_allowed_border_crossing`)

---

## File Structure

```
paper-figure/
  paperfig/
    __init__.py          version
    __main__.py          CLI entry: build | lint | contact
    errors.py            BlueprintError, LayoutError, RouteError, ExportError
    blueprint.py         load/validate → model dataclasses
    schema/blueprint.schema.json
    markup.py            label mini-markup → runs; → drawio HTML
    measure.py           Pillow text measurement with font fallback
    styles.py            recipe load/compose/resolve
    layout.py            container layout → absolute Box per element
    route.py             orthogonal router
    drawio.py            mxGraph XML emitter
    export.py            draw.io CLI discovery + export
    color.py             sRGB↔Lab, CIEDE2000, CVD simulation, WCAG contrast
    lint.py              mechanical checks on emitted XML + PNG
    legend.py            auto legend element construction
    contact.py           contact sheet composer
    pipeline.py          build(blueprint_path, style, out_dir, venue_width) orchestration
  styles/                soft-pastel.json (B), depth-cv.json (C), editorial-minimal.json (D), drawio-default.json (A)
  kb/formats.json        venue widths + sources
  assets/icons/          snowflake.svg, flame.svg + LICENSE (Lucide, ISC)
  agents/critic.md       visual critic prompt (5 criteria)
  bench/phase0/<paper>/blueprint.json, SOURCES.md
  tests/                 one test module per paperfig module + test_pipeline.py
```

## Core data types (defined in Task 1, used everywhere)

```python
@dataclass class Provenance: source: Literal["draft","code","user"]; ref: str
@dataclass class Asset: path: str|None; status: Literal["provided","from-code","requested","placeholder"]; spec: str = ""
@dataclass class Node:        # leaf
    id: str; label: str; role: Role; visual: Visual; tone: str|None
    full_name: str|None; abbrev: str|None; badges: list[str]; asset: Asset|None
    size: tuple[float,float]|None; tokens: int|None; provenance: list[Provenance]; cell: tuple[int,int]|None; span: tuple[int,int]
@dataclass class Group:       # container
    id: str; title: str|None; role: Role|None; frame: Literal["box","dashed","none"]
    layout: Layout; children: list[Node|Group]; provenance: list[Provenance]; cell; span
@dataclass class Layout: type: Literal["row","column","grid"]; align: Literal["start","center","end"]; gap: Literal["tight","normal","loose"]; equalize: bool
@dataclass class Edge: id: str; src: str; dst: str; kind: EdgeKind; label: str|None; src_side: Side; dst_side: Side; provenance: list[Provenance]
@dataclass class Figure: type; venue: str; width: Literal["single","double"]|float; label_language: str; legend: Literal["auto","none"]
@dataclass class Blueprint: figure: Figure; root: Group; edges: list[Edge]; discrepancies: list[dict]; index: dict[str, Node|Group]; parent: dict[str, str|None]
Role = Literal["proposed","reused","io","data","loss","op","annotation"]
Visual = Literal["box","tensor","tokens","image","icon","op","text","placeholder"]
EdgeKind = Literal["data","skip","loss","train_only","infer_only","grad","control"]
Side = Literal["auto","left","right","top","bottom"]
@dataclass class Box: x: float; y: float; w: float; h: float   # absolute px; methods: right, bottom, cx, cy, intersects(other, eps), contains(other), inflate(d)
@dataclass class Placed: elem: Node|Group; box: Box; label_box: Box|None; title_box: Box|None  # label_box for below-labels (tensor/image/icon)
```

---

### Task 1: Scaffold, blueprint schema and validation

**Files:** Create `paperfig/{__init__,errors,blueprint}.py`, `paperfig/schema/blueprint.schema.json`, `tests/test_blueprint.py`, `tests/conftest.py` (fixture `mini_bp()` returning a valid 3-node dict), `pyproject.toml` (pytest config only).

**Interfaces:** Produces `load(path_or_dict) -> Blueprint` (raises `BlueprintError` with a list of all problems, not just the first) and the dataclasses above.

- [ ] Step 1: Write failing tests: `test_valid_minimal_loads`, `test_duplicate_id_rejected`, `test_unknown_edge_endpoint_rejected`, `test_missing_provenance_rejected` (text visual exempt), `test_proposed_without_name_rejected` (needs `full_name` or `abbrev`), `test_proposed_label_must_contain_name` (label must contain abbrev or full_name), `test_grid_cell_collision_rejected`, `test_grid_child_without_cell_rejected`, `test_missing_asset_file_rejected` (status provided/from-code with nonexistent path; message contains the path), `test_edge_to_own_ancestor_rejected`, `test_self_loop_rejected`, `test_markup_tag_whitelist` (only `i b sub sup br`), `test_all_errors_reported_together` (2 independent errors → both in message).
- [ ] Step 2: Run `pytest tests/test_blueprint.py -q` → fails (module missing).
- [ ] Step 3: Implement schema (structural) + `load()` semantic pass; asset paths resolved relative to the blueprint file's directory.
- [ ] Step 4: `pytest tests/test_blueprint.py -q` → all pass.
- [ ] Step 5: Commit.

### Task 2: Label markup and text measurement

**Files:** Create `paperfig/markup.py`, `paperfig/measure.py`, `tests/test_markup.py`, `tests/test_measure.py`.

**Interfaces:** `parse(label: str) -> list[Line]` where `Line = list[Run]`, `Run(text, bold, italic, script: Literal["","sub","sup"])`; `to_html(label) -> str` (escaped, tags preserved); `plain(label) -> str`. `measure(label, size_pt: float, bold=False, family="Helvetica") -> tuple[float,float]` (px width,height; sub/sup at 0.75 size; line height 1.2×). Font fallback chain resolves per glyph: Helvetica → Arial Unicode/PingFang/Noto Sans CJK (first found) for glyphs Helvetica lacks.

- [ ] Step 1: Tests: `test_parse_sub_sup_bold`, `test_html_escapes_ampersand_lt`, `test_br_makes_lines`, `test_measure_grows_with_text`, `test_bold_wider_than_regular`, `test_two_lines_taller`, `test_cjk_measured_wider_than_latin_fallback` ("特征融合" width > 4×0.5em), `test_measure_without_any_font_falls_back_to_estimate` (monkeypatch font discovery → estimate 0.6em/char, never crash).
- [ ] Step 2: run → fail. Step 3: implement (Pillow `ImageFont.truetype(...).getlength`, `.ttc` index 0 regular / bold index discovered by family name). Step 4: run → pass. Step 5: commit.

### Task 3: Style recipes and composition

**Files:** Create `paperfig/styles.py`, `styles/{soft-pastel,depth-cv,editorial-minimal,drawio-default}.json`, `tests/test_styles.py`.

Recipe sections (each recipe defines all): `typography {family,size,title_size,small_size,color}`, `spacing {gap:{tight,normal,loose}, group_pad, title_h, node_pad_x, node_pad_y, min_node_w, min_node_h, label_gap}`, `palette {tones:{blue,green,orange,purple,teal,pink,gray,red}→{fill,stroke,font}, roles:{role→{tone,bold,…}}, container:{default,proposed}}`, `shape {rounded, arc, stroke_width}`, `effects {shadow, gradient, gradient_dir}`, `tensor {depth, w, h_scale, label_pos}`, `edges {kind→{color,width,dash,start,end,rounded}}`, `image {radius, border}`. Values for B/C/D/A taken from `docs/mockups/texture-options.html`.

**Interfaces:** `load_recipe(id) -> Recipe`; `compose(base_id, mix: dict[section,str]) -> Recipe`; `node_style(recipe, node) -> dict[str,str]` (drawio style kv); `group_style(recipe, group)`; `edge_style(recipe, edge)`; `available() -> list[str]`.

- [ ] Step 1: Tests: `test_all_recipes_have_all_sections`, `test_compose_takes_effects_from_mix` (soft-pastel + effects=depth-cv → shadow on), `test_unknown_section_rejected`, `test_proposed_role_uses_accent_and_bold`, `test_tone_overrides_role_default`, `test_every_edge_kind_styled_in_every_recipe`, `test_edge_kinds_distinguishable_without_color` (each recipe: kinds differ in dash/arrow, not only color — warn list empty for skip vs data).
- [ ] Step 2–5: fail → implement → pass → commit.

### Task 4: Layout engine

**Files:** Create `paperfig/layout.py`, `tests/test_layout.py`.

**Interfaces:** `solve(bp: Blueprint, recipe: Recipe) -> dict[str, Placed]` (ids → absolute boxes; root at (0,0)). Leaf intrinsic size = max(min size, measured label + 2·pad) for in-box labels; tensor/image/icon/tokens: shape size + `label_box` below (label_gap); `size` hint can only enlarge. Image: default 80px on the long side, aspect from file, aspect clamped to [1/4, 4]. Row/column: uniform `gap[layout.gap]` between siblings, widened per adjacent pair to fit any edge label between them (label width + 2·8px); cross-axis alignment per `align`; `equalize` (default true) makes same-visual box siblings share cross size. Grid: column widths/row heights = max over cells; spans supported. Group: title_box inside top band of `title_h`, pad on all sides.

- [ ] Step 1: Tests: `test_row_gaps_uniform`, `test_column_center_alignment`, `test_equalize_heights_in_row`, `test_grid_columns_aligned` (same col → same cx), `test_span_occupies_two_columns`, `test_nested_group_contains_children_with_padding`, `test_title_band_reserved`, `test_gap_widened_for_edge_label`, `test_extreme_aspect_image_clamped` (1×20 px PNG fixture → aspect 1/4), `test_size_hint_cannot_shrink_below_text`, `test_no_sibling_overlap_property` (random blueprint generator, 50 seeds: no two sibling boxes intersect).
- [ ] Step 2–5: fail → implement → pass → commit.

### Task 5: Orthogonal router

**Files:** Create `paperfig/route.py`, `tests/test_route.py`.

**Interfaces:** `route_all(bp, placed, recipe) -> dict[str, Route]`, `Route(points: list[tuple[float,float]], src_port: tuple[float,float,str], dst_port: ...)` with port = (x, y, side). Raises `RouteError(edge_id)` if no path.

Algorithm (not determined by signature):
- Port sides: explicit or auto (dominant axis of center delta; ties → horizontal). Several edges on one side of a box are spread evenly at fractions k/(n+1), ordered by the opposite endpoint's coordinate.
- Obstacles: every leaf box (incl. its `label_box`) except the endpoints, inflated by `margin=8`; every group not an ancestor of either endpoint (whole box); for groups that are ancestors, only their `title_box`.
- Candidate lines: obstacle edges ± margin, port coordinates, midpoints between adjacent candidate lines; graph = intersections outside obstacles; A* over (point, heading) with cost = length + 24·bend + 60·crossing an already-routed segment + 200·collinear overlap with an already-routed segment of a different edge (shared endpoint/side exempt).
- First/last segment leave/enter perpendicular to the port side (stub ≥ margin).
- Route order: data → skip → train_only/infer_only → grad/control → loss; within a kind, longer Manhattan distance first. Collinear points removed.

- [ ] Step 1: Tests: `test_straight_line_between_aligned_neighbours` (2 points), `test_detours_around_blocker`, `test_ports_spread_on_shared_side`, `test_unet_skips_do_not_cross_nodes` (3-level U fixture: no segment intersects a non-endpoint box interior; no collinear overlap between skips), `test_edge_into_container_allowed_border_crossing`, `test_no_path_raises_route_error` (endpoint fully enclosed), `test_first_segment_perpendicular_to_port`.
- [ ] Step 2–5: fail → implement → pass → commit.

### Task 6: drawio emitter (+ legend)

**Files:** Create `paperfig/drawio.py`, `paperfig/legend.py`, `assets/icons/{snowflake,flame}.svg`, `assets/icons/LICENSE`, `tests/test_drawio.py`.

**Interfaces:** `emit(bp, placed, routes, recipe) -> str` (full `<mxfile>`); cell ids: blueprint id prefixed `pf-`; decoration cells `pfdeco-<owner>-<n>`; groups are `container=1` cells and children use parent-relative geometry; edges in layer `1` with `source`/`target`, `exitX/exitY/entryX/entryY` + `exitPerimeter=0;entryPerimeter=0`, `edgeStyle=none`, explicit `<mxPoint>` waypoints. `legend.build(bp, recipe) -> Group|None` appends a row under root when `figure.legend == "auto"` (one item per used edge kind other than `data`, plus `frozen`/`trainable` badges and proposed-module swatch when used).
Visual mapping: tensor → `shape=cube` with depth on the top-right (orientation verified by export in Step 4); tokens → invisible group of n small rounded squares; image → `shape=image;image=data:image/png,<b64>`; icon/badge → svg data URI (`data:image/svg+xml,<b64>`), badges 14px at the node's top-right corner; op → ellipse with symbol; placeholder & requested assets → dashed red-gray rect, label `ASSET NEEDED: <spec>`.

- [ ] Step 1: Tests: `test_emitted_xml_parses_and_ids_present`, `test_children_geometry_parent_relative`, `test_edge_waypoints_match_route`, `test_image_data_uri_has_no_semicolon_base64`, `test_html_label_escaped`, `test_placeholder_rendered_dashed_with_text`, `test_legend_lists_used_kinds_only`, `test_badge_placed_top_right`.
- [ ] Step 2: run → fail. Step 3: implement. Step 4: run → pass; then export a tensor sample via Task 7 later — orientation is asserted visually in Task 11 and fixed here if wrong. Step 5: commit.

### Task 7: Export via draw.io CLI

**Files:** Create `paperfig/export.py`, `tests/test_export.py`.

**Interfaces:** `find_drawio() -> str` (raises `ExportError` with install hint); `run(drawio_path, fmt: Literal["png","pdf","svg"], out_path, width_px: int|None=None, timeout_s=120) -> Path` — uses `-x -f <fmt> --border 12 [-t] [--width W] -o out in`; `--crop` for pdf; verifies file exists, size > 0, mtime ≥ start; `print_px(venue_width_in, dpi=300) -> int`.

- [ ] Step 1: Tests: `test_missing_binary_raises` (env points to nonexistent), `test_timeout_raises` (fake binary script that sleeps), `test_no_output_file_raises` (fake binary exits 0 without writing), `test_real_export_png` (skipped if no drawio; PNG width == requested ±2px).
- [ ] Step 2–5: fail → implement → pass → commit.

### Task 8: Color science + mechanical lint

**Files:** Create `paperfig/color.py`, `paperfig/lint.py`, `tests/test_color.py`, `tests/test_lint.py`.

**Interfaces:** `color.contrast(hex_a, hex_b) -> float` (WCAG 2.x), `color.de2000(hex_a, hex_b) -> float`, `color.simulate(hex, kind: Literal["protan","deutan","tritan","gray"]) -> hex` (Machado 2009 severity 1.0 matrices; gray = Rec.709 luma). `lint.check(drawio_path, bp, recipe, png_path|None, print_width_in) -> Report`; `Report(findings: list[Finding], ok: bool)`, `Finding(code, severity: Literal["error","warn","info"], ids: list[str], message: str, provisional: bool)`; `Report.to_markdown()`, `Report.to_json()`.

Checks (codes): `coverage-missing`, `coverage-extra`, `proposed-name-missing`, `overlap`, `child-outside-parent`, `text-overflow`, `edge-through-node`, `edge-through-title`, `edge-overlap`, `edge-crossings` (info), `min-font` (scaled pt < 7 → error, heuristic note), `gap-uneven` (CV > 0.25, provisional), `density` (leaf area / root area outside [0.15, 0.60], provisional), `text-contrast` (<3 error, <4.5 warn), `tone-confusable` (ΔE2000 < 10 under any CVD sim or gray, for different tones used side by side; provisional), `png-mismatch` (missing, older than drawio, or aspect differs >3%), `asset-pending` (warn, lists ids), `edge-kind-color-only` (warn).

- [ ] Step 1: Tests: color — `test_contrast_black_white_21`, `test_de2000_reference_pairs` (Sharma 2005 test pairs 1, 7, 17 to 1e-3), `test_deutan_collapses_red_green` (#d62728 vs #2ca02c ΔE drops below 15). Lint — one test per code built from small hand-edited XML fixtures: `test_text_overflow_flagged`, `test_overlap_flagged`, `test_edge_through_node_flagged`, `test_proposed_name_missing_flagged`, `test_min_font_flagged_when_figure_too_wide`, `test_png_mismatch_when_stale`, `test_clean_figure_has_no_errors` (pipeline output of `mini_bp`).
- [ ] Step 2–5: fail → implement → pass → commit.

### Task 9: Pipeline, CLI, contact sheet, formats KB

**Files:** Create `paperfig/pipeline.py`, `paperfig/__main__.py`, `paperfig/contact.py`, `kb/formats.json`, `tests/test_pipeline.py`, `tests/test_contact.py`.

**Interfaces:** `build(blueprint_path, style: str, mix: dict, out_dir, formats=("png","pdf")) -> BuildResult(drawio, png, pdf, report)` writes `<out>/<name>.drawio|.png|.pdf|.lint.md|.lint.json` and a copy of the resolved blueprint; print width from `kb/formats.json` (`venue` × `figure.width`). CLI: `python -m paperfig build BP --style soft-pastel [--mix effects=depth-cv] --out DIR`; `python -m paperfig lint DRAWIO --blueprint BP`; `python -m paperfig contact --panel "Original=path" --panel "B=path" ... --out sheet.png`. Exit code 1 when report has errors. `contact.compose(panels: list[tuple[str,Path]], out, height=700)` — equal height, labeled, wraps to 2 rows if >3 panels.
`kb/formats.json`: entries for neurips (2025), iclr (2026), icml (2025), cvpr (author-kit) with `textwidth_in`, `columnwidth_in` (computed from columnsep where two-column), `body_pt`, `scriptsize_pt: 7`, `source_url`, `source_file`, `verified: "2026-11-12"`.

- [ ] Step 1: Tests: `test_build_end_to_end_mini` (skip w/o drawio; files exist; report has no errors), `test_build_reports_errors_exit_code`, `test_formats_have_sources`, `test_contact_sheet_dimensions`.
- [ ] Step 2–5: fail → implement → pass → commit.

### Task 10: Critic prompt

**Files:** Create `agents/critic.md`.

Prompt for an independent critic subagent: inputs = PNG path(s), blueprint path, lint report, optional reference image paths; must open the PNG; score 1–5 on faithfulness, conciseness, readability, aesthetics/质感, proposed-module salience+naming; return JSON `{scores, issues:[{severity, where (node/edge ids or region), problem, concrete_fix}]}`; forbid vague issues; forbid scoring without having viewed the image.

- [ ] Step 1: write file. Step 2: dry-run on the Task 9 mini output via Agent; confirm JSON parses. Step 3: commit.

### Task 11: Phase-0 bench — two real papers, styles B and C

**Files:** Create `bench/phase0/restormer/{blueprint.json,SOURCES.md}`, `bench/phase0/blip2/{blueprint.json,SOURCES.md}`.

Papers: Restormer (Zamir et al., CVPR 2022, arXiv 2111.09881, code github.com/swz30/Restormer) — overview with proposed MDTA and GDFN; BLIP-2 (Li et al., ICML 2023, arXiv 2301.12597, code github.com/salesforce/LAVIS) — Q-Former overview with frozen encoders.

- [ ] Step 1: Fetch PDFs + code into `~/.cache/paper-figure/bench/` (not repo). Read method sections and model code; write blueprints with `provenance` refs (section + `file:line`). Note in SOURCES.md that the author had seen these papers before — phase 0 is not blind.
- [ ] Step 2: `python -m paperfig build ... --style soft-pastel` and `--style depth-cv` for each → 4 builds; lint must have 0 errors.
- [ ] Step 3: Open every PNG and look; run the critic (Task 10) per PNG; fix blueprint/engine issues; repeat ≤3 rounds; record unresolved issues honestly.
- [ ] Step 4: Crop original figures from the PDFs (cache only); compose contact sheets Original | B | C per paper → `~/Desktop/paper-figure-phase0/`, plus the `.drawio` files.
- [ ] Step 5: Full test suite green; commit bench blueprints (not originals).

### Task 12: Whole-branch review and hand-off

- [ ] Step 1: Fresh reviewer subagent reviews the whole repo against spec §4⑤⑥/§5/§14 and this plan; fix confirmed findings.
- [ ] Step 2: `pytest -q` full suite → green; record counts.
- [ ] Step 3: Hand off to user: contact sheets, drawio files, lint summaries, unresolved issues, the explicit phase-0 gate question.
