"""Stage 5: does modern science agree with Pliny?

For every plant-condition pair:
  1. count:   how many papers have the plant in their title or abstract AND the condition in their
             title, abstract or MeSH index
  2. papers:  the top 3 papers with the plant in the TITLE and the condition in the title or MeSH index
             (if there are none: the top 3 papers of the count search)
  3. read:    the LLM reads those 3 abstracts: relevant? study type? result?
  4. verdict: supported / partly_studied / contradicted / not_confirmed / untested; a paper only counts if the LLM
             calls it relevant AND its title/abstract names both the plant and the condition

Usage (from the pliny/ folder):
    python src/check_evidence.py --limit 40     # pilot: the 40 pairs with the most claims
    python src/check_evidence.py                # all pairs

Input:  data/04_conditions/claims_with_conditions.jsonl, data/03_plants/plants.jsonl
Output: data/05_evidence/  (report.md, claims_with_evidence.jsonl, pairs.jsonl, leads.csv, spotcheck.csv)
Searches and LLM answers are cached in data/05_evidence/cache.json; reruns continue where they stopped.

A verdict says what modern literature reports. It does not mean that a remedy works or is safe.
"""
import argparse, csv, html, json, re, time
from collections import Counter
from datetime import date
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/config.json").read_text())
OUT = ROOT / "data/05_evidence"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MODEL = CFG.get("evidence", {}).get("llm_model") or CFG["llm"]["model"]

RELIABLE_PLANT = {"footnote", "footnote+llm", "manual"}
RELIABLE_CONDITION = {"exact", "close", "manual"}
AMBIGUOUS_NAMES = {"bulb", "nep", "gith", "cutleek", "rocket", "blite", "pepone", "squill", "mint", "rue", "sage"}


# ---------------------------------------------------------------- helpers
def read_jsonl(path):
    with open(ROOT / path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def clean(text):
    """Remove HTML escapes and tags from titles and abstracts."""
    return re.sub(r"<[^>]+>", "", html.unescape(html.unescape(text or ""))).strip()


def species(name):
    """'Allium sativum L.' -> 'Allium sativum'; 'Rumex L.' -> 'Rumex'."""
    words = (name or "").replace("×", "").split()
    if len(words) > 1 and words[1][:1].islower():
        return f"{words[0]} {words[1]}"
    return words[0] if words else ""


# ---------------------------------------------------------------- 1. pairs
def plant_names(plant):
    """Accepted name, its synonyms from stage 3, and the common name if it is unambiguous."""
    accepted = species(plant["accepted_name"])
    names = {accepted}
    candidates = plant.get("footnote_candidates", []) + plant.get("llm_candidates", [])
    if plant.get("manual_candidate"):
        candidates.append(plant["manual_candidate"])
    for c in candidates:
        wfo = c.get("wfo") or {}
        if species(wfo.get("accepted_name")) == accepted:          # a synonym of the same plant
            names.add(species(wfo.get("matched_name")))
            names.add(species(c.get("name")))
    common = plant["name"]
    if " " not in common and len(common) >= 5 and common not in AMBIGUOUS_NAMES:
        names.add(common)
    return sorted(n for n in names if n)


# MeSH names for effects are drug classes that papers rarely write; add the words they do use
EFFECT_WORDS = {
    "Diuretics": ["diuretic"], "Cathartics": ["laxative", "purgative"], "Emetics": ["emetic"],
    "Expectorants": ["expectorant"], "Carminatives": ["carminative"], "Galactogogues": ["galactagogue", "lactation"],
    "Emmenagogues": ["emmenagogue"], "Menstruation-Inducing Agents": ["emmenagogue"],
    "Cholagogues and Choleretics": ["choleretic", "cholagogue"], "Aphrodisiacs": ["aphrodisiac"],
    "Antidotes": ["antidote"], "Hypnotics and Sedatives": ["sedative", "hypnotic", "sleep"],
    "Hemostatics": ["hemostatic", "haemostatic"], "Analgesics": ["analgesic"],
    "Anthelmintics": ["anthelmintic"], "Abortifacient Agents": ["abortifacient"],
}


def condition_names(claim):
    label = claim.get("condition_mesh_label")
    names = {label, claim.get("condition_search_term")} | set(EFFECT_WORDS.get(label, []))
    return sorted(n for n in names if n)


def make_pairs(claims, plants):
    """Group claims into unique (plant, condition) pairs, most claims first."""
    pairs = {}
    for c in claims:
        plant = plants.get(c.get("plant_id"))
        if not plant or c.get("plant_status") == "unresolved" or c.get("condition_match") == "none":
            continue
        key = f'{c["plant_id"]}|{c.get("condition_mesh_id") or c.get("condition_search_term")}'
        if key not in pairs:
            pairs[key] = {
                "pair_id": key,
                "plant": c["plant_accepted_name"],
                "condition": c.get("condition_mesh_label") or c.get("condition_search_term"),
                "plant_names": plant_names(plant),
                "condition_names": condition_names(c),
                "has_mesh": bool(c.get("condition_mesh_label")),
                "reliable": c["plant_status"] in RELIABLE_PLANT and plant.get("level") == "species"
                            and c["condition_match"] in RELIABLE_CONDITION,
                "claim_ids": [], "claim_types": set(), "sources": set(), "pliny_terms": set(),
            }
        p = pairs[key]
        p["claim_ids"].append(c["claim_id"])
        p["claim_types"].add(c["claim_type"])
        p["sources"].add(c.get("attributed_to") or c.get("attribution"))
        p["pliny_terms"].add(c["indication_raw"])
    for p in pairs.values():
        for k in ("claim_types", "sources", "pliny_terms"):
            p[k] = sorted(x for x in p[k] if x)
    return sorted(pairs.values(), key=lambda p: -len(p["claim_ids"]))


# ---------------------------------------------------------------- 2. search
def count_query(p):
    """Plant in the title or abstract AND condition in the title, abstract or MeSH index."""
    plant = " OR ".join(f'TITLE:"{n}" OR ABSTRACT:"{n}"' for n in p["plant_names"])
    cond = [f'TITLE:"{n}" OR ABSTRACT:"{n}"' for n in p["condition_names"]]
    if p["has_mesh"]:
        cond.append(f'MESH:"{p["condition"]}"')
    return f"({plant}) AND ({' OR '.join(cond)})"


def paper_query(p):
    """Plant in the TITLE, condition in the title or the MeSH index."""
    plant = " OR ".join(f'TITLE:"{n}"' for n in p["plant_names"])
    cond = [f'TITLE:"{n}"' for n in p["condition_names"]]
    if p["has_mesh"]:
        cond.append(f'MESH:"{p["condition"]}"')
    return f"({plant}) AND ({' OR '.join(cond)})"


def europe_pmc(query, page_size, cache):
    key = f"epmc|{query}|{page_size}"
    if key not in cache:
        params = {"query": query, "format": "json", "pageSize": max(page_size, 1),
                  "resultType": "core" if page_size else "lite", "synonym": "false"}
        r = requests.get(EUROPE_PMC, params=params, timeout=40)
        r.raise_for_status()
        data = r.json()
        cache[key] = {
            "hits": int(data.get("hitCount", 0)),
            "papers": [{"id": str(x.get("pmid") or x.get("id")), "year": x.get("pubYear"),
                        "title": clean(x.get("title")), "abstract": clean(x.get("abstractText"))[:1500]}
                       for x in data.get("resultList", {}).get("result", [])[:page_size]],
        }
        time.sleep(0.2)
    return cache[key]


# ---------------------------------------------------------------- 3. read
READ_PROMPT = """You check whether scientific papers test a plant for a condition or effect.
For EACH paper return:
- relevant: true only if the paper itself studies this plant (or its extract, oil or a preparation
  of it) for this condition or effect
- study_type: human_trial, review, animal, in_vitro or other
- result: positive (the plant helped / had the effect), no_effect, harm, or unclear
Return JSON only: {"papers": [{"id": "...", "relevant": true, "study_type": "...", "result": "..."}]}"""
READ_SCHEMA = {"type": "object", "required": ["papers"], "properties": {"papers": {"type": "array", "items": {
    "type": "object", "required": ["id", "relevant", "study_type", "result"],
    "properties": {"id": {"type": "string"}, "relevant": {"type": "boolean"},
                   "study_type": {"type": "string", "enum": ["human_trial", "review", "animal", "in_vitro", "other"]},
                   "result": {"type": "string", "enum": ["positive", "no_effect", "harm", "unclear"]}}}}}}


def read_papers(p, cache):
    """Ask the LLM about the top papers; adds relevant / study_type / result to each paper."""
    key = f'read|{MODEL}|{p["pair_id"]}|{",".join(x["id"] for x in p["papers"])}'
    if key not in cache:
        papers = "\n\n".join(f'id: {x["id"]}\ntitle: {x["title"]}\nabstract: {x["abstract"] or "(none)"}'
                             for x in p["papers"])
        question = f'Plant: {p["plant"]} ({", ".join(p["plant_names"])})\nCondition or effect: {p["condition"]}\n\n{papers}'
        llm = CFG["llm"]
        r = requests.post(llm["ollama_url"], timeout=llm["timeout_s"], json={
            "model": MODEL, "stream": False, "format": READ_SCHEMA, "think": llm.get("think", False),
            "options": {"temperature": 0, "num_ctx": llm["num_ctx"]},
            "messages": [{"role": "system", "content": READ_PROMPT}, {"role": "user", "content": question}]})
        r.raise_for_status()
        cache[key] = json.loads(r.json()["message"]["content"]).get("papers", [])
    answers = {str(a.get("id")): a for a in cache[key]}
    for x in p["papers"]:
        a = answers.get(x["id"], {})
        x.update(relevant=bool(a.get("relevant")), study_type=a.get("study_type"), result=a.get("result"))


# ---------------------------------------------------------------- 4. verdict
GENERIC = {"disease", "diseases", "disorder", "disorders", "injuries", "wounds", "tract", "syndrome",
           "infections", "agents", "and", "with", "other", "drug"}


def mentions(text, name):
    """Does the text mention this name? The full name, or any main word of it (word stem, so
    'Scorpion Stings' matches 'scorpion venom' and 'Joint Diseases' matches 'joint pain')."""
    text = text.lower()
    if name.lower() in text:
        return True
    words = [w for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 3 and w not in GENERIC]
    return any(w[:max(5, len(w) - 3)] in text for w in words)


def really_relevant(x, p):
    """The LLM says relevant AND the paper's title/abstract names both the plant and the condition.
    The second check stops general reviews and off-topic trials from deciding a verdict."""
    text = f'{x["title"]} {x["abstract"]}'
    return (x.get("relevant") and any(mentions(text, n) for n in p["plant_names"])
            and any(mentions(text, n) for n in p["condition_names"]))


def verdict(p):
    if p["hits"] == 0:
        return "untested", "no paper mentions this plant and this condition together"
    relevant = [x for x in p["papers"] if really_relevant(x, p)]
    if not relevant:
        return "not_confirmed", "papers mention both, but none of the top 3 tests this plant for this condition"
    human = [x for x in relevant if x["study_type"] in ("human_trial", "review")]
    wanted = "harm" if p["claim_types"] == ["harm"] else "positive"   # a harm claim is confirmed by harm
    if any(x["result"] == wanted for x in human):
        return "supported", "a relevant human study or review reports the effect"
    if any(x["result"] == "no_effect" for x in human):
        return "contradicted", "relevant human evidence finds no effect"
    return "partly_studied", "relevant studies, but only animal or lab work, unclear results, or harm reports"


# ---------------------------------------------------------------- 5. outputs
VERDICTS = ["supported", "partly_studied", "contradicted", "not_confirmed", "untested"]


def share(rows, v):
    return f"{sum(r['verdict'] == v for r in rows) / len(rows):.0%}" if rows else "–"


def write_outputs(pairs, claims, partial):
    by_claim = {cid: p for p in pairs for cid in p["claim_ids"]}
    out = []
    for c in claims:
        p = by_claim.get(c["claim_id"])
        out.append(dict(c, verdict=p["verdict"] if p else "not_checked",
                        verdict_reason=p["reason"] if p else "not checked",
                        evidence_pair=p["pair_id"] if p else None,
                        evidence_reliable=p["reliable"] if p else None))
    write_jsonl(OUT / "claims_with_evidence.jsonl", out)
    write_jsonl(OUT / "pairs.jsonl", pairs)

    leads = [p for p in pairs if p["verdict"] == "untested" and p["reliable"] and "remedy" in p["claim_types"]]
    leads.sort(key=lambda p: (-len(p["sources"]), -len(p["claim_ids"])))
    with open(OUT / "leads.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["plant", "condition", "pliny_terms", "claims", "sources"])
        for p in leads:
            w.writerow([p["plant"], p["condition"], "; ".join(p["pliny_terms"]), len(p["claim_ids"]), "; ".join(p["sources"])])

    with open(OUT / "spotcheck.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["verdict", "plant", "condition", "reason", "paper_titles", "your_check"])
        for v in VERDICTS:
            for p in [p for p in pairs if p["verdict"] == v][:5]:
                w.writerow([v, p["plant"], p["condition"], p["reason"],
                            " | ".join(x["title"][:90] for x in p["papers"]), ""])

    checked = [c for c in out if c["verdict"] not in ("not_checked", "error")]
    reliable = [c for c in checked if c["evidence_reliable"]]
    lines = ["# Evidence report", "",
             f"Run {date.today().isoformat()}, model `{MODEL}`" + (" — PILOT (--limit)" if partial else "") + ".", "",
             f"**{len(checked)} of {len(claims)} claims** checked in **{len(pairs)}** plant-condition pairs; "
             f"{len(reliable)} claims have a reliable plant and condition."
             + (f" **{sum(p['verdict'] == 'error' for p in pairs)} pairs failed: rerun to retry.**"
                if any(p["verdict"] == "error" for p in pairs) else ""), "",
             "## Verdicts (RQ1)", "", "| Verdict | All checked claims | Reliable claims | Pairs |", "| --- | --- | --- | --- |"]
    for v in VERDICTS:
        lines.append(f"| {v} | {share(checked, v)} | {share(reliable, v)} | {sum(p['verdict'] == v for p in pairs)} |")
    lines += ["", "## Who said it (RQ2)", "", "| Source | Claims | " + " | ".join(VERDICTS) + " |",
              "| --- | --- | " + " | ".join("---" for _ in VERDICTS) + " |"]
    for a in ("named", "hearsay", "pliny"):
        rows = [c for c in checked if c.get("attribution") == a]
        if rows:
            lines.append(f"| {a} | {len(rows)} | " + " | ".join(share(rows, v) for v in VERDICTS) + " |")
    lines += ["", f"## Untested leads (RQ3): {len(leads)}", "", "| Plant | Condition | Claims | Sources |", "| --- | --- | --- | --- |"]
    lines += [f"| {p['plant']} | {p['condition']} | {len(p['claim_ids'])} | {', '.join(p['sources'])} |" for p in leads[:10]]
    lines += ["", "## Limitations", "",
              "- 'Untested' means no paper mentions this plant and this condition together in its title, abstract or "
              "MeSH terms. 'Not confirmed' means such papers exist, but none of the top 3 actually tests the remedy; "
              "these are open, not negative.",
              "- Only the top 3 papers per pair are read, by an LLM; spot-check before quoting.",
              "- 'Supported' means a human study or review reports the effect, not that the remedy works or is safe.",
              "- 'Reliable' pairs: plant from the 1855 footnotes or manual review at species level, "
              "condition mapped exactly or closely to MeSH."]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Stage 5: evidence check")
    ap.add_argument("--limit", type=int, default=0, help="only the first N pairs (pilot)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cache_file = OUT / "cache.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}

    claims = read_jsonl("data/04_conditions/claims_with_conditions.jsonl")
    plants = {p["plant_id"]: p for p in read_jsonl("data/03_plants/plants.jsonl")}
    pairs = make_pairs(claims, plants)
    print(f"{len(pairs)} plant-condition pairs from {len(claims)} claims")
    if args.limit:
        pairs = pairs[:args.limit]

    for i, p in enumerate(pairs, 1):
        try:
            p["hits"] = europe_pmc(count_query(p), 0, cache)["hits"]
            p["papers"] = europe_pmc(paper_query(p), 3, cache)["papers"] if p["hits"] else []
            if p["hits"] and not p["papers"]:        # no paper with the plant in its title: read the top hits
                p["papers"] = europe_pmc(count_query(p), 3, cache)["papers"]
            if p["papers"]:
                read_papers(p, cache)
            p["verdict"], p["reason"] = verdict(p)
        except Exception as e:                       # one failed pair must not stop the run
            p.update(hits=None, papers=[], verdict="error", reason=f"rerun to retry: {str(e)[:100]}")
        if i % 25 == 0:
            cache_file.write_text(json.dumps(cache, ensure_ascii=False))
            print(f"  {i}/{len(pairs)}")
    cache_file.write_text(json.dumps(cache, ensure_ascii=False))
    print(write_outputs(pairs, claims, bool(args.limit)))


if __name__ == "__main__":
    main()
