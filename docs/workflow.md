# Workflow

Every stage is one script in `src/`. It reads the previous stage's folder in `data/` and writes its
own, so any stage can be rerun alone. LLM answers and API lookups are cached in the stage folder;
errors are never cached, so a rerun retries only what failed.

## Pipeline

```
 Perseus TEI (Book 20, 1855 translation)
        │
        ▼
 1 ingest_perseus.py ── data/01_text      chapters → paragraphs → sentences (with offsets),
        │                                  footnotes kept separately, manifest with licence
        ▼
 2 extract.py ───────── data/02_claims    LLM (qwen3:8b): one entry per treatment → one claim per
        │   ▲                              condition; quote located in the text or dropped
        │   └── evaluate.py ◄── gold/gold.jsonl   precision / recall / F1, field accuracy
        ▼
 3 resolve_plants.py ── data/03_plants    plant name → 1855 footnote name / LLM candidates →
        │   (taxonomy.py)                 WFO check → status; team overrides win
        ▼
 4 map_conditions.py ── data/04_conditions condition term → LLM proposes MeSH → NLM / NCBI
        │                                  confirm; team overrides win
        ▼
 5 check_evidence.py ── data/05_evidence  plant-condition pair → Europe PMC search → LLM reads the
        │                                  top 3 abstracts → verdict
        ▼
 6 build_graph.py ───── data/06_graph     Neo4j CSVs + Cypher, graph.json, explorer.html
        (explorer_template.html)
```

## Stages

**1. Ingest.** One record per chapter with its Perseus citation ID, title, the number of remedies
announced in the heading, paragraphs and sentences with character offsets. Footnotes are stored
separately with the offset of their marker. `manifest.json` records source, licence, checksum and
retrieval date.

**2. Extract.** The chapter goes to the LLM in paragraph windows of at most 1,500 characters, with
the two preceding sentences as context. The prompt has worked examples: the gold chapter 83 and
short snippets from unscored chapters. The LLM returns one entry per treatment (one preparation and
one route) with every condition it treats; the script expands it into one claim per condition. A
quote must be found in the window (case, punctuation and spacing ignored) and is stored as the exact
source span, otherwise the claim is dropped and logged. Each claim keeps plant part, preparation,
route, attribution (Pliny, named authority, Magi, hearsay) and Pliny's stance.

**3. Plants.** One record per plant name across chapters. A footnote belongs to the plant named
closest before its marker in the same sentence; its first plainly stated species is confident,
others are hedged. The LLM is asked only about records without a confident footnote (it never sees
the footnotes), plus a blind sample of footnoted records (`--blind 41`; 39 exist) to measure its
accuracy; their LLM answers do not decide. Every candidate is checked
against the WFO Plant List. Status: manual, footnote, footnote+llm, hedged_footnote, llm, disputed,
unresolved. Claims with an unresolved plant stop here.

**4. Conditions.** One record per normalised term ("Head-ache", "for head-ache" → "headache"). The
LLM sees the term, up to three example sentences and their 1855 notes, and proposes a MeSH
descriptor, a category and a match type. NLM's MeSH lookup confirms the descriptor, NCBI entry
terms resolve synonyms. Match: manual, exact, close, broad, unchecked, none. Terms with no modern
equivalent stop here.

**5. Evidence.** Claims are grouped into plant-condition pairs. A count search finds papers with the
plant in title or abstract and the condition in title, abstract or MeSH index; the three top papers
with the plant in the title are read by the LLM (relevant? study type? result?). A paper counts only
if the LLM calls it relevant and its title or abstract names both plant and condition. Verdict:
supported (a human study or review reports the effect), partly studied, contradicted (human evidence
of no effect), not confirmed (papers exist, none tests the remedy), untested (no paper names both).

**6. Graph.** Plants, conditions, claims, sources and the papers that count become nodes; Pliny's
remedies and the papers' tests become relationships. The same graph is written as Neo4j CSVs with
a load script, as JSON, and inside a single HTML explorer that works without a server.

## Human review

Each of stages 3 and 4 writes a `review.csv` with the most frequent and the doubtful records. A
decision typed into its last column is copied into the stage's `overrides.csv` on the next run and
wins over every automatic rule. Stage 5 writes `spotcheck.csv` (five pairs per verdict) for manual
checking before results are quoted.
