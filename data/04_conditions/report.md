# Condition mapping report

Run 2026-11-07, model `qwen3:8b`.

- **929** distinct condition terms in **1617** claims
- **1525 claims (94%)** can be searched in stage 5; **1393** with a confirmed MeSH descriptor

| Match | Terms | Claims |
| --- | --- | --- |
| manual | 32 | 118 |
| exact | 425 | 954 |
| close | 265 | 315 |
| broad | 6 | 6 |
| unchecked | 121 | 132 |
| none | 80 | 92 |

| Category | Terms |
| --- | --- |
| symptom | 207 |
| effect | 399 |
| bite_or_poisoning | 86 |
| disease | 158 |
| other | 79 |

## Most frequent terms

| Pliny's term | Claims | MeSH | Match |
| --- | --- | --- | --- |
| stings of serpents | 29 | Snake Bites | exact |
| defluxions of the eyes | 19 | Conjunctivitis | exact |
| dysentery | 19 | Dysentery | exact |
| headache | 18 | Headache | exact |
| dropsy | 17 | Edema | exact |
| cough | 17 | Cough | exact |
| toothache | 16 | Toothache | exact |
| jaundice | 16 | Jaundice | exact |
| aphrodisiac | 14 | Aphrodisiacs | exact |
| diuretic | 13 | Diuretics | exact |
| gout | 12 | Gout | exact |
| convulsions | 12 | Seizures | exact |
| stings of scorpions | 12 | Scorpion Stings | exact |
| flatulency | 11 | Flatulence | exact |
| wounds | 11 | Wounds and Injuries | manual |
| epilepsy | 10 | Epilepsy | exact |
| asthma | 10 | Asthma | exact |
| erysipelas | 10 | Erysipelas | exact |
| affections of the spleen | 10 | Splenic Diseases | manual |
| lumbago | 9 | Low Back Pain | exact |

## Limitations

- Historical terms are mapped by an LLM from the term and up to 3 example sentences; the most frequent terms were reviewed by hand (review.csv).
- 'broad' mappings use a wider modern category, so evidence found for them is less specific.
- 'unchecked' terms are not exact MeSH descriptors; stage 5 searches them as free text.
- Terms with no modern equivalent ('none') are not checked against modern evidence.
