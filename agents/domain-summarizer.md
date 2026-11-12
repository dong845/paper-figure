# paper-figure — domain summarizer (knowledge-base build)

You turn a set of figure cards from one research area into that area's drawing conventions: visual habits
that recur across its method figures. Every convention must be backed by at least two of the given cards.

## Inputs (in the task message)
- `PAPERFIG` — the command prefix that runs the tool (e.g. `PYTHONPATH=/path/to/paper-figure python3 -m paperfig`);
  every `$PAPERFIG …` below means that prefix **typed out in full** — do not store it in a shell variable.
- `DOMAIN` — the id (e.g. `image-restoration`) and a display name. `CARDS` — paths of its card JSON files.
- `OUT` — `kb/domains/<DOMAIN>.json`.

## Steps
1. Read every card. Note each recurring visual element and how it is drawn: layout pattern, flow direction,
   how data is depicted (thumbnails at both ends, token rows, 3-D feature blocks, k-space images, an
   agent–environment loop), how proposed modules are emphasised, typical colour use.
2. Keep a convention only if **two or more** cards show it **in full** (split a claim when different cards
   support different halves); list those cards' ids as evidence.
3. Keep **at most 10**, ordered by how distinctive they are of this area. Drop habits that hold for method
   figures in general (flat rounded boxes, lettered panels, a legend) — the brief already has those.
4. Write each as a drawing instruction a designer can follow, specific to this area — *"Restoration networks are
   drawn as a U: encoder down the left, decoder up the right, concat skips across, input and output images at
   the top corners"* — not general advice that holds everywhere.

## Output: `OUT` (this shape; `kb validate` checks it)
```json
{"id": "image-restoration", "name": "Image restoration",
 "conventions": [{"text": "…", "evidence_cards": ["swinir-2021-fig2", "uformer-2022-fig2"]}],
 "source": "summarised from the evidence cards listed under each convention"}
```

## Self-check (required)
```
$PAPERFIG kb validate
```
It rejects conventions with fewer than two existing evidence cards and an `id` that differs from the file name.

## Never
- State a convention the cards do not show, or cite a card that does not show it.
- Name or describe the papers' methods; conventions are about drawing.
