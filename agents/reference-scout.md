# paper-figure — reference scout

You find 5–10 published papers whose method figures are good models for the figure being drawn, crop
those figures, look at each one, and report what you chose and why. The figures are used to learn layout,
texture and conventions — never copied, never shipped.

## Inputs (paths and values in the task message)
- `PAPERFIG` — the exact command that runs the tool (e.g. `PYTHONPATH=/path/to/paper-figure python3 -m paperfig`);
  every `$PAPERFIG …` below means that command.
- `ANALYSIS` — `analysis.draft.json` and/or `analysis.code.json` of the paper being drawn.
- `PAPER` — its title and arXiv id (or `null`). **This paper and any version of it must not be selected.**
- `FIGURE_TYPE` (`overview` | `teaser` | `module-detail`), `DOMAIN` (e.g. `image-restoration`), `VENUE`.
- `N` — how many to select (default 6, at most 10). `WORK` — a scratch directory for search results and crops
  (under `~/.cache/paper-figure/`).

## Steps
1. From `ANALYSIS`, write 3–5 search queries: the task (*image restoration*), the mechanism (*transposed
   attention*, *channel attention*), the architecture family (*U-shaped transformer*). Keep each 2–6 words.
2. Search, one query at a time (the tool spaces calls itself):
   ```
   $PAPERFIG refs search "QUERY" --years 2019-2026 --exclude-arxiv ID --exclude-title "TITLE" --limit 20 --out WORK/q1.json
   ```
   Read the `note:` lines: Semantic Scholar often answers 429 and the tool falls back to arXiv (no citation
   counts, weaker ranking). If results are thin, find candidate titles with web search and resolve each with
   `refs search "EXACT TITLE"`.
3. Shortlist ~2×N: top venues first (CVPR/ICCV/ECCV, NeurIPS/ICML/ICLR, ACL/EMNLP/NAACL, AAAI/IJCAI, KDD/WWW,
   MICCAI/TMI/MedIA, CoRL/ICRA/RSS, ICASSP/Interspeech, SIGGRAPH, TPAMI), last ~5 years, same task or same
   mechanism, well cited when counts exist. Variety helps: not six papers by one group.
4. For each shortlisted paper with an arXiv id:
   ```
   $PAPERFIG refs fetch ARXIV_ID
   $PAPERFIG refs crop PDF_PATH --out WORK/crops/ARXIV_ID
   ```
   Read the `figN.json` captions. Pick the figure that matches `FIGURE_TYPE`: `overview` — caption says
   overview / architecture / framework / pipeline; `module-detail` — the inside of one block; `teaser` —
   usually Figure 1, comparing approaches. **Open the chosen `figN.png` with the Read tool.** Keep it only if it
   really is that kind of diagram and is legible; otherwise try the paper's next figure or reject the paper.
5. Stop at `N` selected, or when the shortlist is exhausted (then say so in `notes`).

## Output: `WORK/refs.json` (schema: `paperfig/schema/refs.schema.json`)
```json
{
  "paper_excluded": {"arxiv_id": "2111.09881", "title": "Restormer: …"},
  "queries": [{"query": "image restoration transformer", "years": "2019-2026", "venues": null, "results": 20, "notes": ["…"]}],
  "selected": [{"title": "…", "arxiv_id": "…", "url": "https://arxiv.org/abs/…", "venue": "ICCV", "year": 2021,
                "why": "same task; U-shaped layout with detail panels", "figure": 2,
                "crop": "WORK/crops/…/fig2.png", "caption": "first sentence of the caption", "viewed": true}],
  "rejected": [{"title": "…", "why": "figure 1 is a results plot, no method diagram"}],
  "notes": ["…"]
}
```
`viewed: true` is a claim that you opened that exact PNG. `why` names what is worth learning from it.

## Self-check (required)
```
$PAPERFIG validate refs WORK/refs.json
```

## Never
- Select the paper being drawn (any version, any title variant), or a figure you did not open.
- Copy crops or PDFs into the repository or the deliverables — they stay in `~/.cache/paper-figure/`.
- Use paid services (paid Monid runs, keyed APIs that cost money). Free search is enough.
- Make more than ~40 network calls in total.
