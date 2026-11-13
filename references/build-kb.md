# Knowledge-base build (maintainers)

Grows the read-only layer shipped in `kb/` (spec §6.4). It never runs during a user's figure job. Everything
written must pass `$PAPERFIG kb validate`; `kb/README.md` states the provenance rules.

## Per domain
1. Pick the domain id (`image-restoration`, `diffusion`, `llm`, `vision-language`, `rl`, `speech`, `medical-imaging`,
   `3d-point-cloud`, `graph-learning`, `retrieval`, `segmentation`, …) and 2–3 short descriptions of typical methods.
2. Dispatch **reference-scout** with `ANALYSIS` = a short JSON note of those descriptions (no paper of its own),
   `PAPER` = a paper to exclude when building for a benchmark (else `null`), `FIGURE_TYPE=overview`, `N=6–10`,
   `WORK=~/.cache/paper-figure/kb-build/<domain>`. Validate: `$PAPERFIG validate refs WORK/refs.json`.
3. Cards: the scout writes them itself for its selected figures (`agents/reference-scout.md` step 6) — give it
   `MODE=repo` and have it write `kb/cards/<id>.json` (`DOMAINS=[<domain>]`, a second domain when the figure clearly
   belongs to both); `kb find` first, so a paper figure that already has a card is not carded twice. A separate
   **figure-card-writer** per figure is only for re-carding one figure.
4. Dispatch **domain-summarizer** with all cards of the domain (`grep -l '"<domain>"' kb/cards/*.json`),
   `OUT=kb/domains/<domain>.json`. Conventions need two or more evidence cards each.
5. `$PAPERFIG kb validate` → 0 problems. Look at the cards' `lesson` lines: generic ones ("clean layout") are
   rewritten by re-opening the crop.
6. Link styles: for each card that clearly shows a recipe's look, add its id to that recipe's `evidence_cards` in
   `kb/styles.json`.

## Fields whose papers are not on arXiv
Journals and bioRxiv (protein structure, much of biology and chemistry): search still works (Semantic Scholar,
then OpenAlex, which returns an open-access `pdf_url` when one exists). Fetch with
`$PAPERFIG refs fetch KEY --url PDF_URL`; it accepts only an https URL that answers with a real PDF, so a
paywall or a publisher landing page fails loudly instead of being cropped. bioRxiv/medRxiv `…/vN.full.pdf`
links usually work; publisher sites often answer bots with HTML — then use the preprint, or record the gap.

## Rules
- Benchmark papers never get cards that their own benchmark run could see: build their domains with `PAPER` set
  to the benchmark paper, and `kb query --exclude-paper` keeps the paper's own cards out of its run.
- Cards are text and measured numbers only; crops stay in `~/.cache/paper-figure/`.
- Commit `kb/` changes separately from code, with the domains and card counts in the message.
