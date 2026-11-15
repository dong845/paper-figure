# Restormer (phase-0 bench)

- Paper: Zamir et al., "Restormer: Efficient Transformer for High-Resolution Image Restoration", CVPR 2022, arXiv 2111.09881 (v2).
- Code: github.com/swz30/Restormer, `basicsr/models/archs/restormer_arch.py` (main branch, fetched 2026-11-12).
- Assets (not in this repo; cached under `~/.cache/paper-figure/bench/restormer/assets/`): the repo's own demo pair
  `demo/degraded/portrait.jpg` and `demo/restored/Single_Image_Defocus_Deblurring/portrait.png` (the authors' model output),
  both cropped to the subject (300x225 at (135,0)) to remove the burned-in watermark/EXIF strip; no other edits.
- Original figure for comparison: Fig. 2 of the paper, cropped locally from page 3 (cache only, never committed).
- Round 2 figure (composite): U-shaped overview with channel growth and concat/1×1 labels, a Transformer-Block composition
  (MDTA → GDFN) and detail panels (a) MDTA and (b) GDFN built from Sec. 3, Eq. 1–2 and the `Attention` / `FeedForward` code.
  `facts.json` holds 32 facts (per-branch Q/K/V and GDFN gate/value facts use `via` / `direct`), checked on every build.
- Discrepancy: the code fuses the Q/K/V (and GDFN) 1×1 + 3×3 convolutions into one conv with 3x / 2x channels and splits the
  result; the figure draws the paper's separate branches (mathematically equivalent).
- Honesty note: phase 0 is **not blind** — the developer had seen the paper. Blind runs start in phase 1.
