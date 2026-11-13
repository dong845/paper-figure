# paper-figure round 4 — robust, economical, free in style (user's standing order, 2026-11-13)
User (verbatim gist): references are optional — if none fits after analysis, draw from the material and the target
venue's conventions; fix every listed unresolved problem carefully; draw accurately without excessive tokens; do not
constrain the style direction, research figures should be beautiful; review the whole skill from scratch and make it
robust; read more papers / web search to enrich the knowledge base and the understanding of figure design.
Native execution, TDD, corpus check after engine changes, commit per task, no push.

### T1 References optional
`concepts[].adapts` may be `"none"` (with `takes` naming the venue/domain conventions used); validator accepts it and
run-card ids; SKILL ②/③ say "adapt a reference when one fits, else design from material + venue"; critic MODEL
optional. Tests: test_concept_may_adapt_none, test_concept_may_cite_run_card.

### T2 Token economy
Scout writes the cards of its selected figures itself in MODE=run (it already opened every crop; `kb measure` is
deterministic) — no card-writer fleet per run; existing cards (repo/user layer, same paper+figure) are reused;
`kb harvest RUN` promotes a finished run's valid cards into the user layer (dedupe by paper+figure). Test:
test_harvest_dedupes, test_query_prefers_run_card_over_duplicate.

### T3 Style freedom and aesthetics
`--style PATH.json` accepts a run-local recipe; `paperfig style derive --base B --from-cards DIR --out` builds one from
the references' measured palettes (semantic roles assigned, fills tinted, contrast-checked); auto style = derived or
the brief's evidence, never a silent default; train-only edges never in the accent colour. Tests: test_style_path,
test_style_derive_contrast_safe, test_train_only_edge_not_accent.

### T4 Engine fixes
tokens `values` (per-cell shade); legend fallback = right-side column before a bottom band; edge-label knockout
measures markup (sub/sup/italic); conditional bar "|" → "∣" inside parentheses; text nodes honour tone; glyph
`accent: false`; legend_notes render markup. One test each; corpus check.

### T5 Plan/validator fixes
train_only accepts drawn_as components; Brief ids may be bracket ids; drawn_as accepts analysis component ids
(--analysis) not only fact endpoints; data_visuals.source "public-sample"; unit count applies to overview/teaser;
document equalize. Tests per rule.

### T6 Expression techniques
design.md: contribution type → composition technique catalogue (new space → regions; new conditioning → side input
entering at layers; new loss → supervision path; new module → zoom-in; efficiency → size/scale cue; sequence →
token row; retrieval → database → top-k), each tied to a KB card or a sourced principle.

### T7 Knowledge base enrichment (web + papers)
Sourced figure-design principles (KB rules with URLs); an MRI-reconstruction domain volume and cards (user's field);
validate with `kb validate`.

### T8 SKILL.md audit rewrite, T9 whole-branch review + fix pass, T10 one end-to-end validation run (LDM).
