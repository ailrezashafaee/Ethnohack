"""Stage 4: map Pliny's condition terms to modern MeSH terms.

Usage:
    python src/map_conditions.py                       # reads data/03_plants/claims_with_plants.jsonl
    python src/map_conditions.py --claims other.jsonl
Manual corrections: type a MeSH descriptor name (or NONE) into the your_mesh column of
data/04_conditions/review.csv and rerun.

Steps:
  step 1  collect and normalise condition terms from the claims
  step 2  context: up to 3 example sentences + their footnotes
  step 3  LLM mapping
  step 4  MeSH check
  step 5  decide match type
  step 6  outputs and report
"""
import json, re, time, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/config.json").read_text())
IN_CLAIMS = "data/03_plants/claims_with_plants.jsonl"


def read_jsonl(path):
    path = Path(path) if Path(path).is_absolute() else ROOT / path
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------- step 1
LEADING = re.compile(r"^(?:(?:as|for|in|of|to|the|a|an|with|against)\s+)+"
                     r"|^(?:(?:in\s+)?cases?\s+of|all\s+kinds\s+of|persons\s+(?:suffering\s+from|troubled\s+with|afflicted\s+with))\s+")


def normalise_term(term):
    """'As a Diuretic' -> 'diuretic'; 'Head-ache' -> 'headache'; 'cœliac affections' -> 'coeliac affections'."""
    s = (term or "").lower().replace("æ", "ae").replace("œ", "oe")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"(\w)-\s*(ache)\b", r"\1\2", s)            # head-ache, tooth-ache -> headache, toothache
    s = re.sub(r"[^a-z\s]", " ", s.replace("-", " "))
    s = re.sub(r"\s+", " ", s).strip()
    prev = None
    while prev != s:                                       # strip "as a", "for", "in cases of", ...
        prev, s = s, LEADING.sub("", s).strip()
    return s


def collect_terms(claims):
    """One record per normalised condition term.
    Returns {term: {"term", "raw_terms", "claim_ids", "claim_types", "n_claims"}}."""
    terms = {}
    for c in claims:
        t = normalise_term(c.get("indication_raw"))
        if not t:
            continue
        r = terms.setdefault(t, {"term": t, "raw_terms": set(), "claim_ids": [], "claim_types": set(), "n_claims": 0})
        r["raw_terms"].add(c["indication_raw"])
        r["claim_ids"].append(c["claim_id"])
        r["claim_types"].add(c["claim_type"])
        r["n_claims"] += 1
    for r in terms.values():
        r["raw_terms"], r["claim_types"] = sorted(r["raw_terms"]), sorted(r["claim_types"])
    return terms


# ---------------------------------------------------------------- step 2
# Context for the LLM: up to 3 example sentences per term, each with the footnotes
# whose marker sits inside that sentence (no footnote parsing, just extra context).

def load_context_sources():
    chapters = {c["chapter"]: c for c in read_jsonl(CFG["paths"]["chapters"])}
    notes = {}
    for n in read_jsonl("data/01_text/notes.jsonl"):
        if not n.get("duplicate"):
            ch = int(n["passage_id"].rsplit(".", 1)[1])
            notes.setdefault((ch, n["paragraph"]), []).append(n)
    return chapters, notes


def sentence_with_notes(claim, chapters, notes):
    """'Pliny sentence' + '[Editor's note: ...]' for one claim, or ''."""
    ch = chapters.get(claim["chapter"])
    if not ch:
        return ""
    p_no = int(claim["sent_id"].split(".")[0])
    para = next((p for p in ch["paragraphs"] if p["paragraph"] == p_no), None)
    sent = next((s for s in (para or {}).get("sentences", []) if s["sent_id"] == claim["sent_id"]), None)
    if not sent:
        return claim.get("quote", "")
    text = sent["text"]
    for n in notes.get((claim["chapter"], p_no), []):
        if sent["start"] <= n["char_offset"] <= sent["end"] + 1:
            text += f"\n  [Editor's note (1855): {n['text'][:400]}]"
    return text


def add_context(terms, claims, chapters, notes, per_term=3):
    by_id = {c["claim_id"]: c for c in claims}
    for t in terms.values():
        examples = []
        for cid in t["claim_ids"]:
            s = sentence_with_notes(by_id[cid], chapters, notes)
            if s and s not in examples:
                examples.append(s)
            if len(examples) == per_term:
                break
        t["examples"] = examples
    return terms


# ---------------------------------------------------------------- step 3
# LLM: one term per call; cached per model + prompt version.

import requests

PROMPT_VERSION = "conditions-v2"
CATEGORIES = ["disease", "symptom", "effect", "bite_or_poisoning", "other"]
MATCH_TYPES = ["exact", "close", "broad", "none"]
SYSTEM = """You translate medical terms from Pliny the Elder's Natural History (1st century AD;
English translation of 1855) into modern medicine.
For the given term (and the sentences it comes from), return:
- modern_meaning: what it means today, in plain words
- mesh_term: the single best MeSH descriptor name, spelled exactly as in MeSH
- category: disease, symptom, effect, bite_or_poisoning or other
- match_type: exact (same concept), close (same concept in modern terms), broad (only a wider
  category fits), none (see rules)
- reason: one short sentence

RULES
1. Map to a CONDITION or an EFFECT, never to a body part or organ system
   (not "Uterus", "Digestive System", "Kidney"; use "Uterine Diseases", "Dyspepsia", "Kidney Diseases").
2. Effects use these MeSH pharmacological actions, chosen by meaning:
   purging the bowels, laxative, relaxing the bowels or stomach -> Cathartics;
   causing vomiting -> Emetics; bringing up phlegm -> Expectorants;
   bile, "bilious secretions" -> Cholagogues and Choleretics; urine -> Diuretics;
   wind, flatulence -> Carminatives; more breast milk -> Galactogogues;
   bringing on menstruation or the afterbirth -> Emmenagogues;
   against poisons in general -> Antidotes; sexual desire, philtres -> Aphrodisiacs;
   sleep -> Hypnotics and Sedatives; stopping bleeding -> Hemostatics.
3. Bites and poisonings: serpents -> Snake Bites; scorpions -> Scorpion Stings;
   bees, wasps, hornets, insects -> Insect Bites and Stings; dogs and other animals -> Bites and Stings;
   fungi -> Mushroom Poisoning; poisonous plants (henbane, hemlock, mistletoe) -> Plant Poisoning.
4. Old terms: dropsy -> Edema; quinsy -> Peritonsillar Abscess; strangury -> Dysuria;
   iliac passion -> Intestinal Obstruction; lichens (of the skin) -> Lichenoid Eruptions;
   phagedaenic ulcer -> Skin Ulcer; defluxion -> discharge (of the eyes: Conjunctivitis);
   imposthume -> Abscess; phthiriasis -> Lice Infestations; itch-scab -> Scabies.
5. Use match_type "none" and mesh_term "" when the term is NOT a medical condition or effect
   (cooking, gardening, killing or driving away animals, how to prepare the plant),
   or is too vague to check ("numerous diseases", "health and robustness", "acts too powerfully").
   Never fall back to a default heading.
6. Editor's notes from 1855 may explain old terms; use them.
JSON only."""
SCHEMA = {"type": "object", "required": ["modern_meaning", "mesh_term", "category", "match_type", "reason"],
          "properties": {"modern_meaning": {"type": "string"}, "mesh_term": {"type": "string"},
                         "category": {"type": "string", "enum": CATEGORIES},
                         "match_type": {"type": "string", "enum": MATCH_TYPES},
                         "reason": {"type": "string"}}}
OUT = ROOT / "data/04_conditions"
LLM_CACHE = OUT / "llm_cache.json"


def model():
    return CFG.get("conditions", {}).get("llm_model") or CFG["llm"]["model"]


def ask_llm(term):
    user = f'Term: "{term["term"]}"\n\nSentences:\n' + "\n\n".join(term["examples"] or ["(none)"])
    llm = CFG["llm"]
    r = requests.post(llm["ollama_url"], timeout=llm["timeout_s"], json={
        "model": model(), "stream": False, "format": SCHEMA, "think": llm.get("think", False),
        "options": {"temperature": 0, "num_ctx": llm["num_ctx"]},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]})
    r.raise_for_status()
    a = json.loads(r.json()["message"]["content"])
    a["category"] = a.get("category") if a.get("category") in CATEGORIES else "other"
    a["match_type"] = a.get("match_type") if a.get("match_type") in MATCH_TYPES else "none"
    return a


def map_terms(terms):
    cache = json.loads(LLM_CACHE.read_text()) if LLM_CACHE.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"step 3: {len(terms)} terms, model {model()}")
    for i, t in enumerate(terms.values(), 1):
        k = f"{model()}|{PROMPT_VERSION}|{t['term']}"
        if k not in cache:
            try:
                cache[k] = ask_llm(t)
            except Exception as e:                       # not cached: retried next run
                t["llm"] = {"modern_meaning": "", "mesh_term": "", "category": "other",
                            "match_type": "none", "reason": f"error: {str(e)[:120]}"}
                continue
            LLM_CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
        t["llm"] = cache[k]
        if i % 50 == 0:
            print(f"  {i}/{len(terms)}")
    return terms


# ---------------------------------------------------------------- step 4
# MeSH check: NLM's lookup service (exact descriptor name), then NCBI E-utilities for synonyms
# and entry terms ("Convulsions" -> Seizures). Both free, no key; cached.

MESH_LOOKUP = "https://id.nlm.nih.gov/mesh/lookup/descriptor"
MESH_CACHE = OUT / "mesh_cache.json"
_mesh = json.loads(MESH_CACHE.read_text()) if MESH_CACHE.exists() else {}


def mesh_lookup(label):
    """{'mesh_id', 'mesh_label'} for an exact MeSH descriptor name, or None. Raises on network errors."""
    label = (label or "").strip()
    if not label:
        return None
    if label.lower() in _mesh:
        return _mesh[label.lower()]
    r = requests.get(MESH_LOOKUP, params={"label": label, "match": "exact", "limit": 5}, timeout=30)
    r.raise_for_status()
    hits = r.json() or []
    if not hits:                                     # exact lookup is case-sensitive: "Snake bites"
        r = requests.get(MESH_LOOKUP, params={"label": label, "match": "contains", "limit": 50}, timeout=30)
        r.raise_for_status()
        hits = [h for h in (r.json() or []) if h.get("label", "").lower() == label.lower()]
    found = {"mesh_id": hits[0]["resource"].rsplit("/", 1)[-1], "mesh_label": hits[0]["label"]} if hits else None
    _mesh[label.lower()] = found
    MESH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MESH_CACHE.write_text(json.dumps(_mesh, indent=1, ensure_ascii=False))
    return found


EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _plural_forms(label):
    l = label.lower().strip()
    return {l, l + "s", l[:-1] if l.endswith("s") else l, l + "es"}


def mesh_synonym_lookup(label):
    """Resolve a synonym / entry term to its MeSH descriptor via NCBI E-utilities
    ('Convulsions' -> Seizures, 'Pleuritis' -> Pleurisy). Accepts a descriptor only if the
    label (or its singular/plural) is one of the descriptor's entry terms. Cached."""
    label = (label or "").strip()
    key = "syn|" + label.lower()
    if not label:
        return None
    if key in _mesh:
        return _mesh[key]
    r = requests.get(f"{EUTILS}/esearch.fcgi", params={"db": "mesh", "term": label, "retmode": "json",
                                                        "retmax": 5}, timeout=30)
    r.raise_for_status()
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    found = None
    if ids:
        time.sleep(0.4)                                   # NCBI: max 3 requests/second without a key
        r = requests.get(f"{EUTILS}/esummary.fcgi", params={"db": "mesh", "id": ",".join(ids),
                                                             "retmode": "json"}, timeout=30)
        r.raise_for_status()
        res = r.json().get("result", {})
        wanted = _plural_forms(label)
        for uid in res.get("uids", []):
            rec = res.get(uid, {})
            ui, entry_terms = rec.get("ds_meshui", ""), rec.get("ds_meshterms", []) or []
            if ui.startswith("D") and any(t.lower() in wanted for t in entry_terms):
                found = {"mesh_id": ui, "mesh_label": entry_terms[0], "via_synonym": label}
                break
    time.sleep(0.4)
    _mesh[key] = found
    MESH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MESH_CACHE.write_text(json.dumps(_mesh, indent=1, ensure_ascii=False))
    return found


def resolve_mesh(label):
    """Exact MeSH descriptor first, then synonyms / entry terms."""
    return mesh_lookup(label) or mesh_synonym_lookup(label)


def check_mesh(terms):
    errors = 0
    for t in terms.values():
        t["mesh"] = None
        if t["llm"]["match_type"] == "none":
            continue
        try:
            t["mesh"] = resolve_mesh(t["llm"]["mesh_term"])
        except Exception:
            errors += 1
    print(f"step 4: MeSH checked, {errors} network errors (rerun to retry)")
    return terms


# ---------------------------------------------------------------- step 5
# Final match per term. Manual decisions (your_mesh column in review.csv) win.
#   exact / close / broad   LLM match type, MeSH descriptor confirmed
#   unchecked               LLM gave a term that is not an exact MeSH descriptor (still usable as text)
#   none                    no modern equivalent

import csv

REVIEW = OUT / "review.csv"


OVERRIDES = OUT / "overrides.csv"


def manual_decisions():
    """overrides.csv (term,mesh,note) plus anything typed into review.csv's your_mesh column;
    merged and saved back to overrides.csv so decisions survive later reruns."""
    rows = {}
    if OVERRIDES.exists():
        with open(OVERRIDES, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("term") or "").strip() and (r.get("mesh") or "").strip():
                    rows[r["term"].strip()] = {"term": r["term"].strip(), "mesh": r["mesh"].strip(),
                                               "note": (r.get("note") or "").strip()}
    if REVIEW.exists():
        with open(REVIEW, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("your_mesh") or "").strip():
                    rows[r["term"].strip()] = {"term": r["term"].strip(), "mesh": r["your_mesh"].strip(),
                                               "note": "from review.csv"}
    if rows:
        with open(OVERRIDES, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["term", "mesh", "note"])
            w.writeheader()
            w.writerows(rows.values())
    return {t: r["mesh"] for t, r in rows.items()}


def decide(terms):
    manual = manual_decisions()
    for t in terms.values():
        if t["term"] in manual:
            m = manual[t["term"]]
            if m.upper() == "NONE":
                t.update(match="none", mesh=None, source="manual")
            else:
                try:
                    t["mesh"] = resolve_mesh(m)
                except Exception:
                    t["mesh"] = None
                t.update(match="manual" if t["mesh"] else "unchecked", source="manual")
                t["llm"] = dict(t["llm"], mesh_term=m)
            continue
        t["source"] = "llm"
        lm = t["llm"]["match_type"]
        t["match"] = "none" if lm == "none" else (lm if t["mesh"] else "unchecked")
    return terms


# ---------------------------------------------------------------- step 6
from collections import Counter
from datetime import date

MATCHES = ["manual", "exact", "close", "broad", "unchecked", "none"]


def write_outputs(terms, claims, review_top=40):
    by_term = {}
    for t in terms.values():
        for cid in t["claim_ids"]:
            by_term[cid] = t
    with open(OUT / "claims_with_conditions.jsonl", "w", encoding="utf-8") as f:
        for c in claims:
            t = by_term.get(c["claim_id"])
            c = dict(c, condition_term=t["term"] if t else None,
                     condition_modern=t["llm"]["modern_meaning"] if t else None,
                     condition_mesh_id=(t["mesh"] or {}).get("mesh_id") if t else None,
                     condition_mesh_label=(t["mesh"] or {}).get("mesh_label") if t else None,
                     condition_search_term=(t["llm"]["mesh_term"] or None) if t and t["match"] != "none" else None,
                     condition_category=t["llm"]["category"] if t else None,
                     condition_match=t["match"] if t else "none")
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(OUT / "conditions.jsonl", "w", encoding="utf-8") as f:
        for t in terms.values():
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    ranked = sorted(terms.values(), key=lambda t: -t["n_claims"])
    top = {t["term"] for t in ranked[:review_top]}
    with open(REVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["term", "why_listed", "claims", "modern_meaning", "llm_mesh_term", "mesh_found",
                    "category", "match", "reason", "example", "your_mesh"])
        for t in ranked:
            why = f"top {review_top}" if t["term"] in top else ("unchecked" if t["match"] == "unchecked" else None)
            if not why or t["source"] == "manual":
                continue
            w.writerow([t["term"], why, t["n_claims"], t["llm"]["modern_meaning"], t["llm"]["mesh_term"],
                        (t["mesh"] or {}).get("mesh_label", ""), t["llm"]["category"], t["match"],
                        t["llm"]["reason"], (t["examples"] or [""])[0][:200], ""])

    n = len(claims)
    claims_by = Counter(by_term[c["claim_id"]]["match"] if c["claim_id"] in by_term else "none" for c in claims)
    searchable = sum(v for k, v in claims_by.items() if k != "none")
    report = {
        "date": date.today().isoformat(), "model": model(), "prompt_version": PROMPT_VERSION,
        "terms": len(terms), "claims": n,
        "claims_searchable": searchable, "claims_searchable_share": round(searchable / n, 3) if n else None,
        "claims_with_confirmed_mesh": sum(v for k, v in claims_by.items() if k in ("manual", "exact", "close", "broad")),
        "terms_by_match": dict(Counter(t["match"] for t in terms.values())),
        "claims_by_match": dict(claims_by),
        "terms_by_category": dict(Counter(t["llm"]["category"] for t in terms.values())),
        "top_terms": [{"term": t["term"], "claims": t["n_claims"], "mesh": (t["mesh"] or {}).get("mesh_label"),
                       "match": t["match"]} for t in ranked[:20]],
        "limitations": [
            "Historical terms are mapped by an LLM from the term and up to 3 example sentences; the most "
            "frequent terms were reviewed by hand (review.csv).",
            "'broad' mappings use a wider modern category, so evidence found for them is less specific.",
            "'unchecked' terms are not exact MeSH descriptors; stage 5 searches them as free text.",
            "Terms with no modern equivalent ('none') are not checked against modern evidence.",
        ],
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    lines = ["# Condition mapping report", "", f"Run {report['date']}, model `{report['model']}`.", "",
             f"- **{report['terms']}** distinct condition terms in **{n}** claims",
             f"- **{searchable} claims ({report['claims_searchable_share']:.0%})** can be searched in stage 5; "
             f"**{report['claims_with_confirmed_mesh']}** with a confirmed MeSH descriptor", "",
             "| Match | Terms | Claims |", "| --- | --- | --- |"]
    lines += [f"| {m} | {report['terms_by_match'].get(m, 0)} | {claims_by.get(m, 0)} |" for m in MATCHES]
    lines += ["", "| Category | Terms |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in report["terms_by_category"].items()]
    lines += ["", "## Most frequent terms", "", "| Pliny's term | Claims | MeSH | Match |", "| --- | --- | --- | --- |"]
    lines += [f"| {t['term']} | {t['claims']} | {t['mesh'] or '–'} | {t['match']} |" for t in report["top_terms"]]
    lines += ["", "## Limitations", ""] + [f"- {l}" for l in report["limitations"]]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Stage 4: map condition terms to MeSH")
    ap.add_argument("--claims", default=IN_CLAIMS)
    a = ap.parse_args()
    claims = read_jsonl(a.claims)
    terms = collect_terms(claims)                                      # step 1
    print(f"step 1: {len(terms)} condition terms from {len(claims)} claims")
    chapters, notes = load_context_sources()
    add_context(terms, claims, chapters, notes)                        # step 2
    map_terms(terms)                                                   # step 3
    check_mesh(terms)                                                  # step 4
    decide(terms)                                                      # step 5
    print(write_outputs(terms, claims))                                # step 6
    print(f"outputs in {OUT}")


if __name__ == "__main__":
    main()
