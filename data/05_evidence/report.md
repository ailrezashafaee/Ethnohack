# Evidence report

Run 2026-11-07, model `qwen3:8b`.

**1525 of 1617 claims** checked in **1332** plant-condition pairs; 733 claims have a reliable plant and condition.

## Verdicts (RQ1)

| Verdict | All checked claims | Reliable claims | Pairs |
| --- | --- | --- | --- |
| supported | 3% | 2% | 32 |
| partly_studied | 14% | 15% | 185 |
| contradicted | 0% | 0% | 4 |
| not_confirmed | 31% | 33% | 410 |
| untested | 51% | 50% | 701 |

## Who said it (RQ2)

| Source | Claims | supported | partly_studied | contradicted | not_confirmed | untested |
| --- | --- | --- | --- | --- | --- | --- |
| named | 203 | 2% | 20% | 0% | 33% | 44% |
| hearsay | 112 | 2% | 15% | 0% | 32% | 51% |
| pliny | 1210 | 3% | 13% | 0% | 31% | 52% |

## Untested leads (RQ3): 307

| Plant | Condition | Claims | Sources |
| --- | --- | --- | --- |
| Ruta graveolens L. | Insect Bites and Stings | 7 | hearsay, pliny |
| Malva sylvestris L. | Emetics | 2 | hearsay, pliny |
| Althaea officinalis L. | Insect Bites and Stings | 4 | pliny |
| Malva sylvestris L. | Insect Bites and Stings | 4 | pliny |
| Portulaca oleracea L. | Antidotes | 3 | hearsay |
| Raphanus sativus L. | Emetics | 2 | pliny |
| Raphanus sativus L. | Scorpion Stings | 2 | pliny |
| Ecballium elaterium (L.) A.Rich. | Gout | 2 | pliny |
| Ecballium elaterium (L.) A.Rich. | Lichenoid Eruptions | 2 | pliny |
| Citrullus colocynthis (L.) Schrad. | Tooth Diseases | 2 | pliny |

## Limitations

- 'Untested' means no paper mentions this plant and this condition together in its title, abstract or MeSH terms. 'Not confirmed' means such papers exist, but none of the top 3 actually tests the remedy; these are open, not negative.
- Only the top 3 papers per pair are read, by an LLM; spot-check before quoting.
- 'Supported' means a human study or review reports the effect, not that the remedy works or is safe.
- 'Reliable' pairs: plant from the 1855 footnotes or manual review at species level, condition mapped exactly or closely to MeSH.
