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
