# paper-figure — repo notes for Claude

## Tests
- `python3 -m pytest -q` — full suite (several minutes; draw.io exports). Run it before every push.
- Engine/lint changes also run the corpus check below.

## Acceptance (fixed inputs and baseline for any "optimize / 检查潜在问题" round)
- Fixed inputs: `bench/corpus/<paper>/` — the last delivered blueprint of 11 papers across domains (controlnet,
  decision-transformer, gat, latent-diffusion, pointnet, rag, reflexion, transunet, wav2vec2, restormer, blip2) with
  their facts, plan, analyses and recorded style. Images are grey stand-ins at the delivered pixel sizes.
- Run: `PYTHONPATH=<tree> python3 bench/corpus_check.py --out OUT` for the baseline tree (a `git worktree` at the
  last pushed commit) and for the change; then `python3 bench/corpus_check.py --diff BASE/summary.json NEW/summary.json`.
- Verdict: not worse = no line starting `WORSE` (new lint errors, crash, PDF ≠ 1 page, a blank margin past 48 px,
  smaller smallest text) and every `CHANGED facts` line explained. Changed figures go into a before/after contact
  sheet (`paperfig contact`) for the user. A change that is worse is reverted.
- Known, correct findings in the corpus (not regressions): decision-transformer `facts-all-omitted` (that run's
  plan omitted every fact), `aspect-tall` on the older runs.
- Line-layout changes (router, gaps, ports) also run `PYTHONPATH=<tree> python3 bench/route_metrics.py OUT` on the
  baseline and the change: no total may rise (short / hug / cross / crowd from the routes; head_run / parallel /
  through_label = the lint's line-reading findings). 2026-11-14 at 63f5b86: short 8, hug 7, cross 6, crowd 2, and
  by the user's round-2 criteria 26 arrowheads without a straight run, 11 thick-line pairs, 18 lines through text;
  after round 2: short 0, hug 2, cross 6, crowd 0, and 1 / 0 / 0; with auto-order: cross 5, extra_bends 24 (26
  before), jogs 1.
- Blind runs (agent tokens) are separate: `bench/phase1/RUNNER.md`, configs in `bench/phase1/` and `bench/validation/`.

## Release
- Push only when the user says so in the current request ("push" / "发布"). Stage named paths, never `git add -A`.
- Upload zip for skill hosts (3 MB cap, packed and unpacked; root/dir/file depth): `python3 tools/release_zip.py OUT.zip`
  packs HEAD (`--worktree` packs uncommitted tracked edits) with cards/*.json as one gzip, kb/cards.json.gz, and
  without kb/index.json; it checks every card loads identically and refuses a package past the limits. 2026-11-16:
  zip 1.32 MB, unpacked 2.10 MB (git archive alone unpacks to 7.2 MB). The loader reads loose cards/ over the pack.
