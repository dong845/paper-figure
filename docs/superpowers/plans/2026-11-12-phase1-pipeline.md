# paper-figure Phase 1 — Full Pipeline + Seed Knowledge Base + Blind Benchmark

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native; user said "step into the next phase"). Checkbox steps.

**Goal:** Turn the phase-0 render engine into the skill the spec describes (§4): draft/code analysis agents, faithfulness facts, asset inventory, reference retrieval + figure cards, style samples, critic loop, hand-off — backed by a sourced seed knowledge base (§6) and measured on a blind benchmark of 8 papers (+2 regression) with a recorded baseline (§10).

**Architecture:** The skill is `SKILL.md` (orchestrator instructions) + `agents/*.md` (prompts for subagents the orchestrator spawns) + the `paperfig` CLI (deterministic tools: text extraction, code map, reference search/fetch/crop, KB query/validate, style samples, build/lint, bench prepare/report). Every subagent writes a JSON artifact into a per-run directory; the orchestrator never trusts an artifact it did not validate.

**Spec:** `docs/superpowers/specs/2026-11-12-paper-figure-design.md` §4, §6, §7, §10, §14 (phase 1).

## Global Constraints
- All phase-0 constraints hold (provenance, no fabricated facts/numbers, lint on real artifacts, no paid APIs without asking, no push).
- KB rule: every entry carries `source` (URL + what was read, or `computed:` with the computation). `paperfig kb validate` rejects entries without it. Values not verified are **absent**, never guessed.
- Reference papers' PDFs and figure crops live only under `~/.cache/paper-figure/`; the repo stores text cards, hex values, measurements and links (§6.3).
- Blind protocol: benchmark runs receive the method text with figure environments and captions removed, plus the code; never the original figure. Cards of benchmark papers themselves are excluded from their own runs.
- Network tools: arXiv API and Semantic Scholar Graph API (free, no key); rate-limited politely (≥1 s between calls), with a clear error when offline.
- Runs are reproducible: a run directory records inputs, model, style, KB version (git sha) and every artifact.

## Review Focus
1. Draft inputs in all supported formats (.tex dir with \input, .pdf, .md, .docx) and blind stripping of figures/captions — no caption text may leak into blind method text (Task 1 `test_blind_strips_figure_env_and_caption`, `test_pdf_blind_drops_caption_paragraphs`).
2. PDFs whose captions say "Fig." / "Figure 1:" / "Figure 1." or sit above the figure → crop finds the figure region or reports failure loudly (Task 3 `test_crop_restormer_fig2`, `test_crop_reports_missing_caption`).
3. KB entries missing sources, duplicate card ids, cards for a benchmark paper used in that paper's own run (Task 4 `test_validate_rejects_unsourced`, `test_query_excludes_paper`).
4. Offline / rate-limited / empty search results → explicit error or empty list with reason, never a crash (Task 3 `test_search_offline_error`, `test_search_empty`).
5. Auto (benchmark) mode reaching a confirmation point → records the decision it took instead of blocking (Task 7 SKILL.md section + Task 8 harness check).

---

### Task 1: Text extraction + code map
`paperfig/extract.py`: `extract_draft(path, blind=False) -> Draft(text, sections: [(title, start, end)], source_kind)` for .tex (dir or file; resolves `\input`/`\include`, strips comments; blind removes `figure`/`figure*` environments incl. captions), .pdf (pdftotext; blind drops paragraphs starting with `Figure N`/`Fig. N`), .md (blind drops image lines + following caption paragraph), .docx (zip XML text). `method_section(draft)` returns the method chapter by heading match (Method/Approach/Model/Proposed…), else the whole text with a warning.
`paperfig/codemap.py`: `code_map(repo) -> {files: [{path, classes: [{name, line, bases, methods:[{name,line}], forward_line}], functions}]}` via `ast` (py only; other languages listed by path), skipping tests/venv/build dirs.
CLI: `paperfig extract DRAFT [--blind] --out method.txt`, `paperfig codemap REPO --out code_map.json`.
- [ ] Tests (fixtures built in tmp): `test_tex_input_resolved`, `test_blind_strips_figure_env_and_caption`, `test_pdf_blind_drops_caption_paragraphs` (Restormer PDF from cache, skip if absent), `test_md_blind`, `test_docx_text`, `test_method_section_found`, `test_codemap_classes_and_forward`, `test_codemap_skips_venv`.

### Task 2: Reference search, fetch and figure crop
`paperfig/refs.py`: `search(query, years=None, venues=None, limit=20) -> [Candidate(title, year, venue, arxiv_id, url, citations)]` via Semantic Scholar Graph API (`/paper/search`, fields title,year,venue,externalIds,citationCount) with arXiv Atom API fallback; `fetch(arxiv_id) -> Path` (PDF into cache); `crop_figures(pdf) -> [FigureCrop(number, page, png_path, caption)]` using `pdftotext -bbox-layout` to locate caption lines (`Figure N`/`Fig. N`), rendering the page at 200 dpi and cropping the region between the previous text block and the caption (or caption-above layouts); writes `figN.png` + `figN.json` (caption, page, bbox).
CLI: `paperfig refs search …`, `paperfig refs fetch ID`, `paperfig refs crop PDF`.
- [ ] Tests: `test_parse_s2_response` (fixture JSON), `test_parse_arxiv_atom` (fixture XML), `test_search_offline_error` (monkeypatched network), `test_search_empty`, `test_crop_restormer_fig2` (cache PDF: page 3 crop contains the figure, height > 30% page; skip if absent), `test_crop_blip2_fig1`, `test_crop_reports_missing_caption`.

### Task 3: Knowledge base structure + CLI
Layout `kb/`: `formats.json`, `palettes.json`, `typography.json`, `styles.json` (index of `styles/*.json` with descriptions + example renders), `domains/<domain>.json` (`conventions: [{text, evidence_cards:[ids]}]`), `cards/<id>.json` (figure card schema §6.2 + `source` = paper URL + figure number, `measured` block computed by a script). User layer: `~/.local/share/paper-figure/cards/` (env `PAPERFIG_DATA`). `paperfig/kb.py`: `load_kb()`, `validate() -> problems`, `query(domain, venue, exclude_paper=None) -> Brief` (format, palettes, typography rules, domain conventions, up to N cards), `add_card(card)` (user layer, dedupe by paper+figure). `paperfig/cardmeasure.py`: from a figure PNG compute palette (k-means on non-white pixels → hex, share), whitespace ratio, aspect — stored as `measured` with `source: computed`.
CLI: `paperfig kb validate|query|add-card|measure`.
- [ ] Tests: `test_validate_rejects_unsourced`, `test_validate_rejects_duplicate_card`, `test_query_merges_user_layer`, `test_query_excludes_paper`, `test_measure_palette_on_synthetic` (3-colour image → 3 hex within ΔE 3), `test_card_schema`.

### Task 4: Seed KB content (sourced)
- formats: add IEEE conference/journal (IEEEtran.cls), ACM sigconf (acmart.cls: KDD/WWW/SIGGRAPH), Springer LNCS (llncs.cls: ECCV/MICCAI), ACL (acl.sty: ACL/EMNLP/NAACL), AAAI, IJCAI, ICCV (CVPR kit), NeurIPS/ICLR/ICML/CVPR existing — each read from the official class/style file with the evidence line; venues not verified are left out and listed in `kb/README.md` as TODO.
- palettes: Okabe–Ito, Paul Tol (bright, vibrant, muted, light, high-contrast), ColorBrewer qualitative (Set2, Dark2, Paired, Pastel1), Matplotlib tab10 — hex read from the publishers' own files/pages; CVD/grayscale safety recorded as `computed` with our color module.
- typography: only rules quoted from publisher guidelines that could be fetched (e.g. IEEE graphics guidelines, Nature figure guide); otherwise empty with TODO.
- domains + cards for the 8 benchmark domains: per domain the reference-scout agent finds ~4 related top-venue papers (excluding the benchmark paper), crops their method figure, figure-card-writer writes cards; domain conventions are summarised only from those cards (each convention cites ≥2 cards).
- [ ] `paperfig kb validate` → 0 problems; commit KB.

### Task 5: Style samples
`paperfig samples BP --styles a,b,c [--mix …] --out DIR` → builds each style (fast path: png only) + labelled contact sheet `samples.png`; refuses to show a sample whose lint has errors (spec: samples must pass mechanical checks).
- [ ] Tests: `test_samples_builds_each_style_and_sheet`, `test_samples_skips_failing_style_with_reason`.

### Task 6: Agent prompts
`agents/draft-analyst.md`, `agents/code-analyst.md` (structured JSON reports: components, data flow, named modules verbatim, losses, train/infer differences, every item with provenance), `agents/facts-writer` section inside draft-analyst (facts.json written from text only, per branch with `via`/`direct`), `agents/reference-scout.md` (uses `paperfig refs`, selection criteria, never the benchmark paper itself), `agents/figure-card-writer.md` (card schema, look at the crop), `agents/critic.md` (exists). Each prompt states its input files, output file + schema, and forbidden actions.
- [ ] Dry-run each prompt once on Restormer inputs; validate the JSON outputs with `paperfig kb validate` / blueprint loader; fix prompts.

### Task 7: SKILL.md (orchestrator)
Use the `authoring-skills` skill. SKILL.md (concise) + `references/workflow.md` (step details), `references/blueprint.md` (schema guide with examples), `references/design.md` (layout patterns, compaction, detail panels, brackets, what the lint means). Steps = spec §4 ①–⑦ with the four user confirmation points via AskUserQuestion; `auto` mode (benchmark) records each decision in `run.json` instead of asking. Run directory layout fixed.
- [ ] Trigger description; dry-read by a fresh agent for ambiguity (builder check).

### Task 8: Benchmark harness + baseline
`bench/phase1/<paper>/config.json` (arXiv id, code repo + commit, venue, width, figure no., domain, style). `paperfig bench prepare` (fetch PDF + code into cache, blind method text, original crop cache-only), `paperfig bench report` (contact sheets original vs ours, table of lint / facts / critic scores) → `bench/phase1/baseline.json` (numbers, model, git sha; no images).
- [ ] Run the skill in auto mode on the 8 blind papers (one runner agent per paper following SKILL.md) + rebuild the 2 regression papers; record baseline; contact sheets to `~/Desktop/paper-figure-phase1/`.

### Task 9: Whole-branch review → fix pass → merge locally → hand-off (user gate on the baseline sheets).
