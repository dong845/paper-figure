# BLIP-2 (phase-0 bench)

- Paper: Li et al., "BLIP-2: Bootstrapping Language-Image Pre-training with Frozen Image Encoders and Large Language Models", ICML 2023, arXiv 2301.12597 (v3).
- Code: github.com/salesforce/LAVIS, `lavis/models/blip2_models/{blip2.py, blip2_opt.py, blip2_qformer.py}` (main, fetched 2026-11-12).
- Asset (cache only): the example photo embedded in the paper's Fig. 1, extracted with `pdfimages` from page 1 — i.e. taken from the draft itself.
  The quoted prompt and generated text are verbatim from Fig. 1.
- Original figure for comparison: Fig. 1, cropped locally from page 1 (cache only).
- Honesty note: phase 0 is **not blind** (developer had seen the paper). Target: ICML single column (3.25in), as the original.
- Discrepancy recorded in the blueprint: the FC projection (code `opt_proj`, paper Sec. 3.3 / Fig. 3) is omitted in this teaser.
