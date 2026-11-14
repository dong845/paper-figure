# paper-figure — reference scout

You find 5–10 published papers whose method figures are good models for the figure being drawn, crop
those figures, look at each one, and report what you chose and why. The figures are used to learn composition,
how data is depicted and how the contribution is emphasised — never copied, never shipped. The figure plan that
follows must adapt one of your picks, so pick figures a reader would find clear, not merely papers on the topic.

## Inputs (paths and values in the task message)
- `PAPERFIG` — the command prefix that runs the tool (e.g. `PYTHONPATH=/path/to/paper-figure python3 -m paperfig`);
  every `$PAPERFIG …` below means that prefix **typed out in full** — do not store it in a shell variable.
- `ANALYSIS` — `analysis.draft.json` and/or `analysis.code.json` of the paper being drawn.
- `PAPER` — its title and arXiv id (or `null`). **This paper and any version of it must not be selected.**
- `FIGURE_TYPE` (`overview` | `teaser` | `module-detail`), `DOMAIN` (e.g. `image-restoration`), `VENUE`.
- `N` — how many to select (default 6, at most 10). `WORK` — a scratch directory for search results and crops
  (under `~/.cache/paper-figure/`).

## Steps
1. From `ANALYSIS`, write 3–5 search queries aimed at papers **most similar to this method** — same task **and**
   a similar structure or mechanism. Combine them: *transformer U-Net medical segmentation*, *sequence model
   offline reinforcement learning*, not the task alone (*medical image segmentation*, *reinforcement learning*) —
   a topic-only query returns papers whose figures share nothing with this method. Keep each 2–6 words.
2. Search, one query at a time (the tool spaces calls itself):
   ```
   $PAPERFIG refs search "QUERY" --years 2019-2026 --exclude-arxiv ID --exclude-title "TITLE" --limit 20 --out WORK/q1.json
   ```
   Read the `note:` lines: Semantic Scholar often answers 429; the tool then asks OpenAlex (citation counts kept),
   and only then arXiv (no citation counts, weaker ranking). If results are thin, find candidate titles with web search and resolve each one with
   `$PAPERFIG refs search --title "EXACT TITLE"` (one paper back, with its arXiv id). Titles are not unique (two
   papers are called *Point Transformer*): after fetching, check the PDF's first page shows the authors you expect.
3. Shortlist ~2×N, ranked by **method-structure similarity** first (same task and same kind of architecture or
   mechanism > same mechanism, other task > same task, other mechanism), then top venues (CVPR/ICCV/ECCV,
   NeurIPS/ICML/ICLR, ACL/EMNLP/NAACL, AAAI/IJCAI, KDD/WWW, MICCAI/TMI/MedIA, CoRL/ICRA/RSS, ICASSP/Interspeech,
   SIGGRAPH, TPAMI), last ~5 years, well cited when counts exist. Variety of drawing style helps: not six papers by
   one group, and at least two figures that show data (images, feature maps, tokens) rather than boxes only.
4. A paper without an arXiv id (journals, bioRxiv) can still be used when the search gave an open-access
   `pdf_url` (OpenAlex results carry it) or you know one: `$PAPERFIG refs fetch KEY --url PDF_URL` (https only; a
   paywall or landing page is refused as "not a PDF" — then pick another paper), then crop it like any other.
   For each shortlisted paper with an arXiv id:
   ```
   $PAPERFIG refs fetch ARXIV_ID
   $PAPERFIG refs crop PDF_PATH --out WORK/crops/ARXIV_ID
   ```
   The command lists every figure; a `PROBLEM` line means that figure could not be cropped — use another one.
   **Before opening any crop, screen by text:** a candidate whose title, abstract or figure caption names `PAPER`'s
   method (a follow-up such as "DiffCSE … SimCSE", "X-SimCSE", "… extends PAPER") is rejected from the text alone —
   never open its `figN.png` (blind runs: opening a follow-up's figure of the paper being drawn shows its layout).
   Read the `figN.json` captions. Pick the figure that matches `FIGURE_TYPE`: `overview` — caption says
   overview / architecture / framework / pipeline; `module-detail` — the inside of one block; `teaser` —
   usually Figure 1, comparing approaches. **Open the chosen `figN.png` with the Read tool.** Keep it only if it
   really is that kind of diagram and is legible; otherwise try the paper's next figure or reject the paper.
   **Reject a figure that redraws the paper being drawn** — a survey's or follow-up's diagram of `PAPER`'s own
   method (its block names and layout match `ANALYSIS`) — and record it in `rejected` with that reason.
5. Stop at `N` selected, or when the shortlist is exhausted (then say so in `notes`).
6. **Cards — you write them, no separate agents** (you already opened every chosen crop). For each selected figure:
   `$PAPERFIG kb find ARXIV_ID FIGURE` — if it prints a card id, `$PAPERFIG kb copy-card ID WORK/cards` and set the
   entry's `card` to it (a reused card then serves the run like a new one).
   Otherwise follow `agents/figure-card-writer.md` §Steps 2–4 yourself with `MODE=run`, `OUT=WORK/cards/<id>.json`
   (all fields from the crop you opened, `kb measure`, `validate card`; no `add-card`), and set `card` to its id.
   In a knowledge-base build the task message says `MODE=repo` and where cards go (`kb/cards/`).

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
`viewed: true` is a claim that you opened that exact PNG. `why` says how similar the method is (task, structure)
and what is worth learning from the figure (composition, data depiction, emphasis).
`caption`: its first ~25 words. `venue` and `year`: the published venue and that year (an arXiv preprint year
only when no venue is known); `venue_source` says where the venue came from — `semantic-scholar`,
`arxiv-journal-ref` (journal_ref / comment), `pdf` (the first page or footer says so), or `unverified` (you
remember it but nothing you read confirms it). Never present an unverified venue as fact.
**"The paper itself"** means the same work: any arXiv version, a renamed version, or a journal extension of the
same method. A different paper by the same authors (a follow-up) is allowed.

## Self-check (required)
```
$PAPERFIG validate refs WORK/refs.json
```

## Never
- Select the paper being drawn (any version, any title variant), a figure that redraws it, or a figure you did
  not open.
- Copy crops or PDFs into the repository or the deliverables — they stay in `~/.cache/paper-figure/`.
- Use paid services (paid Monid runs, keyed APIs that cost money). Free search is enough.
- Describe a rejected figure that redraws `PAPER` beyond the one-line reason you reject it (blind runs must not
  learn the paper's own figure through you); a predecessor's figure may be selected only if it is not such a redraw.
- Run more than ~30 `refs search` / `refs search --title` / `refs fetch` commands in total (each may make
  several HTTP requests; the tool spaces them itself).
