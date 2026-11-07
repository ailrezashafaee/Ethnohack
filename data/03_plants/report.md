# Plant resolution report

Run 2026-11-07, model `qwen3:8b`.

- **114 of 115** plant names resolved (106 to species level)
- **1617 of 1621** claims (100%) linked to a modern plant; 92% at species level
- **36** plant names backed by the 1855 editors' footnotes

| Status | Plant names | Claims |
| --- | --- | --- |
| manual | 12 | 317 |
| footnote | 34 | 644 |
| footnote+llm | 2 | 18 |
| hedged_footnote | 0 | 0 |
| llm | 60 | 619 |
| disputed | 6 | 19 |
| unresolved | 1 | 4 |

## Most frequent plants

| Pliny's name | Claims | Modern name | Status |
| --- | --- | --- | --- |
| rue | 83 | Ruta graveolens L. | footnote |
| cabbage | 78 | Brassica oleracea L. | llm |
| anise | 58 | Pimpinella anisum L. | manual |
| garlic | 57 | Allium sativum L. | llm |
| mallow | 53 | Malva sylvestris L. | footnote |
| radish | 48 | Raphanus sativus L. | footnote |
| mustard | 45 | Sinapis alba L. | footnote |
| lettuce | 39 | Lactuca L. | footnote |
| purslain | 38 | Portulaca oleracea L. | manual |
| onion | 37 | Allium cepa L. | llm |
| mint | 37 | Mentha × verticillata L. | footnote |
| ocimum | 36 | Ocimum basilicum L. | footnote |
| nasturtium | 34 | Lepidium sativum L. | footnote |
| cutleek | 32 | Allium ampeloprasum L. | manual |
| colocynthis | 31 | Citrullus colocynthis (L.) Schrad. | footnote |

**LLM vs 1855 editors (blind, n=39):** same species 33%, same genus 54%

## Limitations

- 1855 footnote identifications are historical hypotheses, not ground truth.
- A footnote is only used when the plant is named in the same sentence before its marker.
- The geography rule excludes plants native only outside the wider ancient world, so traded imports (e.g. from India) can be wrongly excluded.
- Claims whose plant is unresolved are not checked against modern evidence.
