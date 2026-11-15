# BLIP-2 (phase-0 bench)

- Paper: Li et al., "BLIP-2: Bootstrapping Language-Image Pre-training with Frozen Image Encoders and Large Language Models", ICML 2023, arXiv 2301.12597 (v3).
- Code: github.com/salesforce/LAVIS, `lavis/models/blip2_models/{blip2.py, blip2_opt.py, blip2_qformer.py}` (main, fetched 2026-11-12).
- Asset (cache only): the example photo embedded in the paper's Fig. 1, extracted with `pdfimages` from page 1 (taken from the draft).
  The quoted prompt and generated text are verbatim from Fig. 1.
- Original figure for comparison: Fig. 1, cropped locally from page 1 (cache only).
- Round 2 figure: one pipeline image → frozen encoder → Q-Former (+ learned queries, + text in Stage 1 only) → FC → frozen LLM
  (+ prompt) → output, with overlapping Stage 1 (top) / Stage 2 (bottom) brackets. Rewritten after the user found the round-1
  figure unfaithful (text input and the stage-2 image path were missing; FC omitted). `facts.json` (11 facts) is checked on
  every build.
- Width: ICML **double** column (6.75in). The faithful main flow has 6 parts; single-column variants measured 4.7–5.6pt text.
- Discrepancy: Sec. 3.3 covers decoder-only and encoder-decoder LLMs; the figure shows the generic LLM and names both losses.
- Honesty note: phase 0 is **not blind** (developer had seen the paper).
