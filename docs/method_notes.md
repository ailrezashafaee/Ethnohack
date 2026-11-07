# Method notes: what changed and why

The plan from the start of the week (`plant_candidates` ranked by name similarity, Disease
Ontology terms, EMA and ClinicalTrials.gov counts) changed as the data showed what works. This file
records the changes that affect the results.

## Stage 2: extraction (prompt v2)

- **One entry per treatment, not per condition.** v1 asked the LLM for one claim per condition.
  v2 asks for one entry per treatment (one preparation and route) with a list of `indications`, and
  the script expands it into one claim per condition, so lists like "good for A, B and C" are
  handled in one place and preparation, route and attribution are written once per treatment.
- **Smaller windows with context.** v1 sent up to 6,000 characters per call; v2 sends at most 1,500,
  with the two preceding sentences marked `[context]` so "it" and "he" stay resolvable, and the
  prompt forbids taking claims from the context lines.
- **Tolerant quote matching.** v1 needed the quote verbatim (after whitespace clean-up). v2 matches
  ignoring case, punctuation and spacing and stores the exact source span, so the quote in the
  output is still verbatim; paraphrased quotes are still dropped.
- **Truncated answers are salvaged.** Complete claim objects are kept from an answer that was cut
  off, and the answer length limit is set explicitly (`num_predict` 4096).
- **Clearer field rules.** What counts as a claim (food effects, cosmetics, amulets count;
  descriptions, cooking and effects on animals do not), how to write indications ("scrofulous
  sores", not "cleanses scrofulous sores"), and when attribution is hearsay.
- **Worked examples.** Besides gold chapter 83, seven short snippets from other chapters show the
  hard cases. Examples must never come from a scored gold chapter; the script checks this.

Result: F1 0.86 on the dev chapter, 0.83 on the five held-out chapters. Because two sentences of
chapter 52 are in the prompt (see below), the clean number is 0.82 on the four other held-out
chapters (13, 14, 15, 86; 107 claims).

**Open issue.** One snippet comes from chapter 52, which was added to the gold set as a test
chapter after the extraction run. The published claims are not affected, but `extract.py` now
refuses to extract new chapters until that snippet is replaced (which means a new prompt version
and a new extraction run).

## Stage 3: plants

- **Footnotes first.** The 1855 editors identify many plants in footnotes. A confident footnote name
  decides; the LLM is only asked where there is none, and never sees the footnotes, so its accuracy
  can be measured blind against them (39 records: 33% same species, 54% same genus).
- **Stricter WFO matching (v2/v3).** Fuzzy matches are allowed only within the same genus and for
  spelling variants of the epithet (silvestris = sylvestris); earlier versions let "Lactuca
  silvestris" jump to "Lactuca siamensis". A misspelt genus is accepted only with an identical
  epithet ("Menta pulegium" → Mentha pulegium). WFO's own unambiguous match wins; among homonyms the
  Linnaean name is preferred (the classic Old World names).
- **Footnote noise.** Footnote candidates that WFO does not know at all ("French ladies") are
  ignored. If a confident footnote name is not a WFO name (the 1855 typo "Pinpinella anisum"), the
  LLM answer may decide even for a blind-test record.
- **Team decisions.** 13 plants were decided by the team after review (`overrides.csv`), e.g. anise
  and pennyroyal (footnote typos), squill = Drimia maritima, hibiscum = Althaea officinalis, and
  piperitis left unresolved.
- **Geography not used.** The rule (exclude species native only outside the ancient world and its
  trade regions) is written but the WCVP lookup is not connected, so no candidate was excluded.

## Stage 4: conditions (prompt v2)

- **MeSH instead of the Disease Ontology.** Stage 5 searches Europe PMC, which indexes papers by
  MeSH, so MeSH descriptors make the search precise.
- **Effects and old terms.** Many of Pliny's "conditions" are effects (purging, diuretic) or old
  terms (dropsy, quinsy, strangury). The v2 prompt maps them to MeSH pharmacological actions and
  modern terms, forbids body parts as answers, and returns "none" for non-medical or vague terms.
- **Synonyms.** A proposed term that is not a descriptor name is resolved through MeSH entry terms
  ("Convulsions" → Seizures). Terms that still do not resolve are kept as free-text search terms
  ("unchecked").
- **Team decisions.** 32 terms were decided after reviewing the most frequent ones.

## Stage 5: evidence

- **One source.** EMA monographs, ClinicalTrials.gov and safety lists from the plan are not used in
  the final version; the verdict rests on Europe PMC.
- **Count search plus reading.** A hit count says how much is written, not what it says. The count
  search now only decides untested vs. studied; the three top papers with the plant in the title
  (or the top hits if there are none) are read by the LLM.
- **Effect words.** MeSH names for effects ("Cathartics") are drug classes that papers rarely
  write, so the words papers do use ("laxative", "purgative") are searched as well.
- **Stricter relevance (v5).** The LLM called general reviews and off-topic trials relevant. A paper
  now counts only if its title or abstract also names both the plant and the condition.
- **Contradicted vs. harm (v5).** A harm report no longer contradicts a remedy claim; only human
  evidence of no effect does. Harm claims are supported by harm reports.
- **Not confirmed (v6).** Pairs with papers that mention plant and condition but do not test the
  remedy were called untested. They are now "not confirmed", so "untested" means that no paper names
  both: a cleaner basis for leads.

## Stage 6: graph

Only papers that count under the stage 5 rule enter the graph, so every `TESTS` edge is evidence a
reader can check. The explorer embeds the graph in one HTML file so it works without a server.

## Validation of stage 5 (manual spot-check)

24 verdicts were checked by hand against the papers' titles and abstracts
(`data/05_evidence/spotcheck.csv`). Agreement: untested 5/5, not confirmed 5/5, supported 3/5,
partly studied 1/5, contradicted 0/4. The errors share one cause: a paper that names both the
plant and the condition is not necessarily a test of the remedy (general overviews of a plant,
toxicology of related plants, trials of unrelated mixtures). The two negative categories are
reliable; supported and partly studied are upper bounds, and no contradiction survived the check.
Next step for the method: ask the LLM a stricter question ("does this paper test X for Y?") and
read more than three papers for pairs with many hits.
