# Was Pliny Right?

**Do Pliny the Elder's plant remedies hold up against modern science?**
An auditable pipeline from the remedy claims in Pliny's *Natural History*, Book 20 (1st century AD),
to modern plant names, modern conditions and modern literature.
EthnoHack 2026, Track 1: Traditional Knowledge Mining.

**Team Parse-ian-track1:** Alireza Ghassemi (M.Sc. student, Life Science Informatics, University of Bonn)
and Alireza Shafaee (M.Sc. student, Computer Science, University of Bonn)

> Historical claims only, not medical advice. A verdict says what the modern literature reports,
> not that a remedy works or is safe.

**Explore the results:** open `data/06_graph/explorer.html` in a browser, or the [online version](https://ailrezashafaee.github.io/Ethnohack/data/06_graph/explorer.html).

**App:** search and browse every remedy by plant or condition, on phone or desktop: [open the app](https://ailrezashafaee.github.io/Ethnohack/app/) (installable as a web app; see `app/README.md`).

## Research questions

1. How do Pliny's remedies hold up today: supported, studied, or never tested?
2. Does the source of a claim (a named physician, hearsay, Pliny himself) predict whether it holds up?
3. Which untested remedies are the most promising leads?

## Pipeline and results

| Stage | What it does | Result |
| --- | --- | --- |
| 1 Text | Parses the Perseus TEI edition (Bostock & Riley, 1855) | 100 chapters, 548 footnotes, 1,720 remedies counted by Pliny |
| 2 Claims | Local LLM extracts every remedy and harm claim with its exact quote | 1,621 claims; F1 **0.82** on held-out chapters |
| 3 Plants | 1855 footnotes, LLM and World Flora Online give each plant a modern name | 99.8% of claims linked, 92% at species level |
| 4 Conditions | Old terms mapped to MeSH ("dropsy" → Edema) | 94% searchable, 86% with a confirmed MeSH term |
| 5 Evidence | Europe PMC search per plant-condition pair; the LLM reads the top papers | see below |
| 6 Graph | Knowledge graph (Neo4j) and browser explorer | 112 plants, 351 conditions, 253 papers |

**Answers** (1,525 checked claims):

- **RQ1:** 51% have no paper at all, 31% have papers that do not test the remedy, at most 14% are
  partly studied (animal or lab) and at most 3% are supported by human studies. Mostly, modern
  science has not asked.
- **RQ2:** claims from named physicians were studied a little more often (20% partly studied vs.
  13–15%), but are not more often supported (2–3% in every group).
- **RQ3:** 307 untested remedies with a reliably identified plant and condition
  (`data/05_evidence/leads.csv`), e.g. rue and mallow for insect stings, radish against scorpion stings.

Full numbers: `data/0N_*/report.md`. What changed during the project and why: `docs/method_notes.md`.

## Human review

| Stage | Checked by the team |
| --- | --- |
| Claims | Gold set of 7 chapters (186 claims), AI-drafted and approved by the team, used for the F1 |
| Plants | 13 identifications decided against the text and footnotes (`data/03_plants/overrides.csv`) |
| Conditions | 32 mappings of frequent terms (`data/04_conditions/overrides.csv`) |
| Evidence | 24 verdicts checked against the papers (`data/05_evidence/spotcheck.csv`): untested 5/5, not confirmed 5/5, supported 3/5, partly studied 1/5, contradicted 0/4 |

## How we built this

**Design choices that make the results checkable rather than just generated:**

- **Every claim is traceable.** Each claim keeps Pliny's exact words with chapter, sentence and
  character offsets, and every later decision (plant, condition, verdict, papers) is attached to it.
- **Pliny checks himself.** His chapter headings state how many remedies each chapter holds
  ("ORAGE: FOURTEEN REMEDIES"); we use these counts as an independent recall check for extraction.
- **19th-century experts as evidence.** The 1855 editors' footnotes identify many plants. They decide
  where they are confident; the LLM only fills gaps, and is tested blind against them.
- **Authoritative names over model guesses.** Every plant name is validated against World Flora
  Online and every condition against MeSH; the LLM proposes, curated vocabularies decide.
- **Who said it matters.** Claims record whether Pliny cites a named physician, hearsay or himself,
  which lets us ask whether ancient source reliability predicts modern support (RQ2).
- **Honest verdicts.** "Untested" (no paper at all) is kept apart from "not confirmed" (papers exist,
  none tests the remedy), and every category's error rate was measured by hand.

**Role of AI.** A local open-weight model (qwen3:8b via Ollama) is one component of the pipeline:
it extracts claims, proposes plant and condition names and reads abstracts, and each of these
steps is constrained by rules, checked against external data and measured against a gold set or
manual review. An AI coding assistant (Claude) helped draft and revise the code. The team defined
the research questions, made the design choices at each stage, ran and debugged every stage on the
real data, found and fixed the problems documented in `docs/method_notes.md`, approved the gold set,
reviewed and approved the 45 plant and condition decisions against the text, and checked the
final verdicts by hand.

## How to run

```bash
pip install -r requirements.txt
ollama pull qwen3:8b        # Ollama running locally
./run_pipeline.sh           # all stages; with the committed caches no LLM or network calls are needed
```

Each stage can also be run alone (`python src/<stage>.py`, see `run_pipeline.sh`). Team decisions
go into the `review.csv` / `overrides.csv` files of stages 3 and 4. To load the graph into Neo4j 5:
copy `data/06_graph/*.csv` into the database's import folder, run `load_neo4j.cypher`, then try
`example_queries.cypher`.

The app (Flutter) runs with `cd app && flutter run -d chrome` (or a phone simulator); it reads a
copy of `data/06_graph/graph.json`. GitHub Pages publishes it and the explorer on every push to `main`.

## Repository layout

```
config/config.json   model, paths, settings
src/                 one script per stage: ingest_perseus, extract, evaluate, export_gold,
                     resolve_plants (+ taxonomy), map_conditions, check_evidence, build_graph
gold/                gold set (gold.jsonl) and annotation workbook
data/00_source       Perseus TEI source
data/01_text … 06_graph   outputs of each stage, with team decisions and caches
docs/                workflow and method notes
app/                 Flutter app (web, phone, desktop): search, plants, conditions, assistant preview
```

## Limitations

- Supported and partly-studied shares are upper bounds: in the spot-check, general overviews and
  papers that mention but do not test a remedy were sometimes counted. No automated contradiction
  survived manual checking. Only 3 papers per pair are read.
- "Untested" means no paper names the plant and the condition together; it is an open question,
  not a negative result. The search can miss known evidence (e.g. horehound for cough, EMA).
- 1855 footnote identifications are historical hypotheses; 60 plant names rest on the LLM alone
  (33% species agreement with the 1855 editors in a blind test). No geography check is applied.
- Two sentences of test chapter 52 appear as an example in the extraction prompt; without
  chapter 52 the held-out F1 is 0.82 (0.83 with it).

## Future work

Stricter evidence reading and more papers per pair; EMA herbal monographs; a larger model and
native-range check for plant names; comparing the 1855 editors' verdicts with today's; a
compound-level plausibility layer for the leads; Books 21–27, Dioscorides and OCR'd editions.

## Licence and sources

Code: MIT. Data: CC BY-SA 3.0 US, as it derives from the Perseus Digital Library edition of
Pliny (tr. Bostock & Riley, 1855); see `LICENSE`. Plant names: World Flora Online. Conditions:
MeSH (U.S. National Library of Medicine). Papers: Europe PMC.
