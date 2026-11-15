# paper-figure knowledge base

Read-only layer shipped with the skill. Every entry names its source. `paperfig kb validate` rejects
anything unsourced, any measurement not marked `computed:`, palette safety numbers that no longer match
their colours, domain conventions backed by fewer than two existing cards, and duplicate cards (same paper
and figure, in any URL / arXiv-id / title form).

| file | holds | provenance rule |
|---|---|---|
| `formats.json` | page geometry per venue or template (`textwidth_in`, `columnwidth_in`, fonts) | `source_url` + `evidence` (the line read in the official class/style file or guide) + `verified` date |
| `palettes.json` | published palettes (`colors` in the publisher's order, `names` where given) | `source.url` + `source.read`; `safety` is computed by `paperfig.kb.palette_safety` |
| `typography.json` | figure rules from publisher guidelines | `source.url` + verbatim `source.quote`; optional `lint` = the lint checks that enforce it |
| `styles.json` | index of the style recipes in `../styles/` | recipes are this skill's own designs; `evidence_cards` link to cards that show the style |
| `domains/<id>.json` | drawing conventions of a research area | each convention cites at least 2 cards in `evidence_cards` |
| `cards/<id>.json` | one real method figure, described in text (schema: `paperfig/schema/card.schema.json`) | `source` = paper URL + figure number + what was looked at; `measured` from `paperfig kb measure` |

No reference figures or crops are stored here (spec §6.3). PDFs and crops live in `~/.cache/paper-figure/`.

## Figure index and method facets (`index.json`, `taxonomy.json`)
Every card describes one real method figure in text and numbers. Cards are published, so they hold no image. On
top of the style fields, a card carries:
- `taxonomy`: the method facets, in the controlled vocabulary of `taxonomy.json`:
  - `family`;
  - `paradigm`, plus `paradigm_source` when this paper *is* the source;
  - `architecture`, `training`, `modality`;
  - `depicts`: what the figure draws (real photos, quoted text, a similarity matrix …);
  - `task`.
- `insights`: one specific sentence per aspect, saying what to learn: `structure`, `data`, `emphasis`, `flow`.
  Also `avoid`: what not to copy.
- `arrangement`: the top-level partition a run copies as its skeleton (`references/layout.md`).
- `fetch`: how to get the figure again — an arXiv id or an open-access PDF url, plus the figure number.
  `paperfig kb fetch-crop CARD_ID DIR` downloads and crops it, so no local image cache is needed.

`index.json` is generated from the cards (`paperfig kb index`) and never edited by hand. `kb validate` fails when
it is stale. A run retrieves references two ways:
- **by content:** the reference scout's search;
- **by method:** `paperfig kb match --paradigm … --family … --architecture … --training …`, which returns figures
  that draw the same kind of network.

Both routes are references, not templates.

### Growing it
- **Every run adds cards.** The scout writes this run's cards with the same facets (`agents/figure-card-writer.md`),
  and `kb harvest RUN` files them into the user layer. Repo cards come from knowledge-base builds.
- **`paperfig kb gaps` says what to add next:**
  - cards without facets;
  - families with fewer than 3 figures;
  - recurring `other` notes, which are candidates for new vocabulary;
  - paradigms not yet in the `paradigms` list.
- **Vocabulary changes:** add the value to `taxonomy.json` (with a one-line meaning), retag the cards that used
  `other` for it, then run `kb index`.
- **Choosing figures to add:** prefer each paradigm's source figure and figures readers know. Cover every family
  before adding more to a full one. A figure whose arrangement is weak is still useful when its `avoid` says why.

## User layer

Cards written during use go to `$PAPERFIG_DATA/cards/` (default `~/.local/share/paper-figure/cards/`) through
`paperfig kb add-card`; they never modify this directory. Reads merge both layers; a user card never overrides a
repo card with the same id or the same paper + figure.

## Template keys vs venue keys

Where a venue's template could be read directly, the key is the venue (`cvpr`, `iccv`, `eccv`, `icml`, `neurips`,
`iclr`, `acl`, `emnlp`, `naacl`, `ijcai`). Where only the class file was read and the venue → template mapping was
not verified, the key is the template (`ieee-conference`, `ieee-journal`, `ieee-compsoc-journal`,
`ieee-compsoc-conference`, `acm-sigconf`, `acm-tog`, `lncs`); use it as `figure.venue`, or give `figure.width`
in inches.

## TODO (not verified, therefore absent)

- **AAAI** — the official author kit (aaai.org/authorkit26) could not be downloaded from a primary source.
- **Venue → template mappings** to confirm from each venue's call for papers: MICCAI (LNCS), KDD and WWW (acm-sigconf),
  SIGGRAPH (acm-tog), ICRA / CoRL (IEEE conference), TPAMI (IEEE compsoc journal), IEEE TMI (IEEE journal).
- **Own templates not read yet**: ICASSP (spconf.sty), Interspeech, RSS, Medical Image Analysis (Elsevier),
  Nature Machine Intelligence (the `nature` entry is the Nature journal's own guide).
- `scriptsize_pt` for acmart (9 pt body) — the size table was not read.
- Typography: no rule is stored as universal (`applies_to: ["all"]`); every rule is tied to the venue whose guide says it.
