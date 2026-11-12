# Restormer (phase-0 bench)

- Paper: Zamir et al., "Restormer: Efficient Transformer for High-Resolution Image Restoration", CVPR 2022, arXiv 2111.09881 (v2).
- Code: github.com/swz30/Restormer, `basicsr/models/archs/restormer_arch.py` (main branch, fetched 2026-11-12).
- Assets (not in this repo; cached under `~/.cache/paper-figure/bench/restormer/assets/`): the repo's own demo pair
  `demo/degraded/portrait.jpg` and `demo/restored/Single_Image_Defocus_Deblurring/portrait.png` (the authors' model output).
- Original figure for comparison: Fig. 2 of the paper, cropped locally from page 3 (cache only, never committed).
- Honesty note: phase 0 is **not blind** — the developer had seen the paper before writing this blueprint by hand from Sec. 3 and the code.
  The blind protocol (method text + code only, original figure withheld) starts in phase 1.
- Scope: overview + Transformer-Block level. MDTA/GDFN internals (Fig. 2a/b of the paper) are a separate module-detail figure, not drawn here.
