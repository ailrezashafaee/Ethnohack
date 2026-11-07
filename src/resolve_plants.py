"""Stage 3: map Pliny's plant names to modern scientific names.

Usage:
    python src/resolve_plants.py                          # full run
    python src/resolve_plants.py --claims data/02_claims/claims_1.jsonl
    python src/resolve_plants.py --no-llm                 # footnotes + WFO only
    python src/resolve_plants.py --blind 41               # also measure LLM vs footnotes
    Manual corrections: type a scientific name (or UNRESOLVED) into the your_decision column of
    data/03_plants/review.csv and rerun; decisions are copied into overrides.csv and win.

Steps:
  step 1  collect plant names from the claims
  step 2  footnote names
  step 3  LLM names
  step 4  WFO check (taxonomy.py)
  step 5  geography check
  step 6  combine evidence, decide status
  step 7  link claims, write outputs and report
"""
import argparse, csv, json, re, time, unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/config.json").read_text())


def read_jsonl(path):
    path = Path(path) if Path(path).is_absolute() else ROOT / path
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------- step 1
# Decisions: one record per name across chapters; plurals always merged after
# normalising; "wild X" and "X" stay separate records.

KEEP_ENDINGS = ("is", "us", "os", "as", "ss", "ys")   # Greek/Latin singulars: colocynthis, staphylinos


def singular(word):
    """'onions' -> 'onion', 'radishes' -> 'radish', 'berries' -> 'berry'; 'colocynthis' stays."""
    if len(word) <= 3 or word.endswith(KEEP_ENDINGS):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes", "sses")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def normalise_name(name):
    """Lowercase, unify ligatures and accents, drop punctuation, singularise every word.
    'Wild Onions,' -> 'wild onion'; 'Head-ache' style hyphens become spaces."""
    s = (name or "").lower().replace("æ", "ae").replace("œ", "oe")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))   # é -> e, ë -> e
    s = re.sub(r"[^a-z\s]", " ", s.replace("-", " "))
    return " ".join(singular(w) for w in s.split())


# Decisions (round 2): "cultivated X" / "garden X" merge into "X" ("wild X" stays separate);
# product names merge into their plant via a small alias list; leftovers without a plant name
# go to the chapter's main plant (its most frequent plant name); "X or Y" merges into an existing record.

CULTIVATED_PREFIXES = ("cultivated ", "garden ")
ALIASES = {                      # product or misspelt name -> plant record
    "aniseed": "anise", "hempseed": "hemp", "rape seed": "rape", "bulb seed": "bulb",
    "linseed": "flax", "nast urtium": "nasturtium",
}
LEFTOVERS = {"blossom", "seed of the cultivated kind", "plant", "seed", "flower", "leaf", "root", "juice"}


def base_key(name):
    """Normalise, drop 'cultivated'/'garden', apply aliases."""
    k = normalise_name(name)
    for prefix in CULTIVATED_PREFIXES:
        if k.startswith(prefix):
            k = k[len(prefix):]
    return ALIASES.get(k, k)


def make_key_function(claims, chapters):
    """Returns key(plant_name_raw, chapter) -> record name, applying all step-1 rules."""
    plain = {base_key(c["plant_name_raw"]) for c in claims}
    plain = {k for k in plain if " or " not in k and k not in LEFTOVERS}
    # chapter's main plant = the most frequent proper plant name among that chapter's claims
    counts = {}
    for c in claims:
        k = base_key(c["plant_name_raw"])
        if k in plain:
            counts.setdefault(c["chapter"], {}).setdefault(k, 0)
            counts[c["chapter"]][k] += 1
    main_plant = {ch: max(d, key=d.get) for ch, d in counts.items()}

    def key(raw, chapter):
        k = base_key(raw)
        if k in LEFTOVERS or not k:
            return main_plant.get(chapter) or k
        if " or " in k:
            parts = [base_key(p) for p in k.split(" or ")]
            if parts[0] == "wild" and len(parts) > 1:          # "wild or erratic cabbage"
                parts.append("wild " + parts[1].split()[-1])
            match = next((p for p in parts if p in plain), None)
            return match or k
        return k
    return key


def collect_names(claims, chapters):
    """One record per plant name across chapters (step 1).
    Returns (plants, key) where plants = {name: {"name", "raw_names", "chapters", "n_claims"}}
    and key(raw_name, chapter) gives the record name for any claim."""
    key = make_key_function(claims, chapters)
    plants = {}
    for c in claims:
        k = key(c["plant_name_raw"], c["chapter"])
        if not k:
            continue
        p = plants.setdefault(k, {"name": k, "raw_names": set(), "chapters": set(), "n_claims": 0})
        p["raw_names"].add(c["plant_name_raw"])
        p["chapters"].add(c["chapter"])
        p["n_claims"] += 1
    for p in plants.values():
        p["raw_names"], p["chapters"] = sorted(p["raw_names"]), sorted(p["chapters"])
    return plants, key


# ---------------------------------------------------------------- step 2
# Decisions: a footnote belongs to a plant if the plant is named in the SAME SENTENCE before
# the footnote marker (when several plants are named there, the one closest to the marker wins);
# if a footnote names several species, the first one is confident when stated plainly, the
# others are hedged; genus-only mentions ("some kind of Chenopodium") are kept as genus candidates.

IGNORE_WORDS = {"wild", "the", "of", "and", "or", "a", "called", "kind", "seed", "red", "white", "black"}
NOT_GENUS = {"The", "This", "That", "These", "Pliny", "Fée", "Fee", "Hardouin", "Dalechamps", "Sillig",
             "Dioscorides", "Theophrastus", "Galen", "Hippocrates", "Celsus", "Book", "See", "Chap",
             "Greek", "Latin", "Roman", "Romans", "Italy", "Egypt", "Sprengel", "Bauhin", "Desfontaines",
             "Morbus", "Linnæus", "Linnaeus", "It", "In", "He", "We", "Our", "Its", "As", "Some", "For",
             "Coluber", "Vipera", "Scorpio",           # animals that appear in the notes
             "French", "English", "German", "Italian", "Italians", "Arabic", "Arabs", "Spanish",
             "Egyptian", "Egyptians", "Persian", "Indian", "Syrian", "Gallic", "Gauls", "Pythagoras",
             "Diocles", "Nicander", "Cato", "Varro", "Columella", "Lycus", "Mr", "Dr"}
HEDGES = re.compile(r"\b(probably|perhaps|possibly|supposed|supposes|uncertain|doubtful|conjectur\w*|"
                    r"impossible to identify|not known|unknown|some think|some suppose|F[ée]e thinks|"
                    r"or else|thought to be|said to be|some writers|some authors|by some)\b", re.I)
SPECIES = re.compile(r"\b([A-Z][a-zæœë]{2,}(?:-\s?[a-zæœë]+)?)\s+([a-zæœë]{3,}(?:-\s?[a-zæœë]+)?)"
                     r"(\s+of\s+Linn\w*|\s+L\.)?")
GENUS_ONLY = re.compile(r"\b(?:some|a|one) (?:kind|species|sort) of (?:the )?([A-Z][a-zæœ]{3,})\b"
                        r"|\bthe genus ([A-Z][a-zæœ]{3,})\b")


def name_pattern(word):
    """Regex for a plant word that also matches its plural: 'radish' -> radish, radishes."""
    stem = word[:max(4, len(word) - 1)]
    return re.compile(rf"\b{re.escape(stem)}\w*", re.I)


def last_mention(record, text, records):
    """Position of the last mention of this plant record in text, or -1.
    When both 'X' and 'wild X' are records in this chapter, 'wild X' needs 'wild' right before
    the word and plain 'X' must not have it; otherwise 'wild' is ignored."""
    best = -1
    text = text.replace("æ", "ae").replace("Æ", "Ae").replace("œ", "oe")   # positions are only compared within this text
    wild = record.startswith("wild ")
    base = record[5:] if wild else record
    both = base in records and "wild " + base in records
    for word in [w for w in record.split() if w not in IGNORE_WORDS and len(w) > 2]:
        for m in name_pattern(word).finditer(text):
            has_wild = bool(re.search(r"\bwild\W+(?:\w+\W+)?$", text[max(0, m.start() - 20):m.start()], re.I))
            if not both or wild == has_wild:
                best = max(best, m.start())
    return best


def species_in_note(text):
    """Scientific names in a footnote: [{'name', 'rank', 'confidence', 'excerpt'}]."""
    found = []
    for m in SPECIES.finditer(text):
        genus, epithet, linnaeus = m.group(1), m.group(2), m.group(3)
        if genus in NOT_GENUS or epithet in ("the", "and", "who", "was", "has", "with", "from"):
            continue
        before = text[max(0, m.start() - 15):m.start()].lower()
        if not linnaeus and not re.search(r"\b(the|a|or|probably|perhaps)\s*$", before):
            continue                                  # accept "the X y", "X y of Linnæus", "X y L."
        sentence = next((s for s in re.split(r"(?<=[.;])\s+", text) if m.group(0) in s), text)
        found.append({"name": f"{genus} {epithet}", "rank": "species", "author_hint": "L." if linnaeus else None,
                      "hedged": bool(HEDGES.search(sentence)), "excerpt": sentence[:220]})
    for m in GENUS_ONLY.finditer(text):
        g = m.group(1) or m.group(2)
        if g not in NOT_GENUS:
            found.append({"name": g, "rank": "genus", "hedged": True,
                          "excerpt": text[max(0, m.start() - 60):m.end() + 60]})
    seen, out = set(), []
    for i, f in enumerate(found):                     # first plainly stated species = confident
        if f["name"] in seen:
            continue
        seen.add(f["name"])
        first_species = f["rank"] == "species" and not any(o["rank"] == "species" for o in out)
        f["confidence"] = "confident" if first_species and not f.pop("hedged") else "hedged"
        f.pop("hedged", None)
        out.append(f)
    return out


def footnote_candidates(plants, chapters, notes):
    """Step 2: attach footnotes to plant records and extract their scientific names.
    Adds plants[name]['footnote_candidates'] = [{name, rank, confidence, excerpt, note_id, chapter}]."""
    for p in plants.values():
        p["footnote_candidates"] = []
    for chapter, chapter_notes in notes.items():
        records = [r for r, p in plants.items() if chapter in p["chapters"]]
        if not records:
            continue
        paragraphs = {p["paragraph"]: p for p in chapters[chapter]["paragraphs"]}
        for n in chapter_notes:
            para = paragraphs.get(n["paragraph"])
            if not para:
                continue
            sent = next((s for s in para["sentences"] if s["start"] <= n["char_offset"] <= s["end"] + 1), None)
            if not sent:
                continue
            before = para["text"][sent["start"]:n["char_offset"]]      # same sentence, before the marker
            positions = {r: last_mention(r, before, records) for r in records}
            owner = max(positions, key=positions.get)
            if positions[owner] < 0:
                continue
            for cand in species_in_note(n["text"]):
                cand.update(note_id=n["note_id"], chapter=chapter)
                plants[owner]["footnote_candidates"].append(cand)
    return plants


def load_notes():
    """notes.jsonl grouped by chapter number, duplicates skipped."""
    notes = {}
    for n in read_jsonl("data/01_text/notes.jsonl"):
        if not n.get("duplicate"):
            notes.setdefault(int(n["passage_id"].rsplit(".", 1)[1]), []).append(n)
    return notes


# ---------------------------------------------------------------- step 3
# Decisions: ask the LLM only about records WITHOUT a confident footnote species
# (optionally plus a blind sample of footnoted ones, --blind N, default 0); it sees every
# sentence that mentions the plant across its chapters (never the footnotes); it returns up
# to 3 ranked species. Answers are cached per model + prompt version.

LLM_PROMPT_VERSION = "plants-v1"
LLM_SYSTEM = """You identify plants named in Pliny the Elder's Natural History, Book 20
(1st century AD, Roman Mediterranean; English translation of 1855).
You get the plant's name as the translator wrote it and every sentence where Pliny mentions it.
Return up to 3 candidate modern species, most likely first, as Latin binomials with author
abbreviation (e.g. "Allium cepa L."). Prefer plants known in the Roman world.
For each: confidence (high, medium or low) and a one-sentence reason based on the text
(description, habitat, use, Greek or Latin name given by Pliny).
If you cannot identify the plant, return an empty list.
Return JSON only: {"candidates": [{"scientific_name": "...", "confidence": "...", "reason": "..."}]}"""
LLM_SCHEMA = {"type": "object", "required": ["candidates"], "properties": {"candidates": {
    "type": "array", "maxItems": 3, "items": {"type": "object",
    "required": ["scientific_name", "confidence", "reason"],
    "properties": {"scientific_name": {"type": "string"},
                   "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                   "reason": {"type": "string"}}}}}}
LLM_CACHE = ROOT / "data/03_plants/llm_cache.json"
MAX_CONTEXT_CHARS = 4000


def plant_sentences(record, plants, chapters):
    """Every sentence mentioning the plant, grouped under its chapter headings (step 3 context)."""
    p = plants[record]
    lines, size = [], 0
    for ch in p["chapters"]:
        chapter_records = [r for r, q in plants.items() if ch in q["chapters"]]
        hits = [s["text"] for para in chapters[ch]["paragraphs"] for s in para["sentences"]
                if last_mention(record, s["text"], chapter_records) >= 0]
        if not hits:
            continue
        block = [chapters[ch]["title"]] + hits
        for line in block:
            if size + len(line) > MAX_CONTEXT_CHARS:
                lines.append("[...]")
                return "\n".join(lines)
            lines.append(line); size += len(line)
    return "\n".join(lines) if lines else chapters[p["chapters"][0]]["title"]


def is_binomial(name):
    return bool(re.match(r"^[A-Z][a-z]+ [a-z][a-z\-]+", (name or "").strip()))


def plant_model():
    """Model for plant identification: config plants.llm_model, else the extraction model."""
    return CFG.get("plants", {}).get("llm_model") or CFG["llm"]["model"]


def call_llm(messages):
    llm = CFG["llm"]
    r = requests.post(llm["ollama_url"], timeout=llm["timeout_s"], json={
        "model": plant_model(), "messages": messages, "stream": False, "format": LLM_SCHEMA,
        "think": llm.get("think", False), "options": {"temperature": 0, "num_ctx": llm["num_ctx"]}})
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"]).get("candidates", [])


def ask_llm(record, plants, chapters):
    """Up to 3 ranked candidates: [{'name', 'llm_rank', 'confidence', 'reason'}], or [] on failure."""
    raw = ", ".join(plants[record]["raw_names"])
    user = f'Plant name(s) in the translation: {raw}\n\nSentences:\n{plant_sentences(record, plants, chapters)}'
    messages = [{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": user}]
    cands = []
    for attempt in (1, 2):
        try:
            cands = [c for c in call_llm(messages) if is_binomial(c.get("scientific_name"))]
        except Exception as e:                       # one bad answer must not stop the run
            return [], f"error: {str(e)[:150]}"
        if cands:
            break
        messages.append({"role": "user", "content": "Give Latin binomials only, e.g. 'Allium cepa L.', "
                                                    "or an empty list if you really cannot identify it."})
    out = [{"name": " ".join(c["scientific_name"].split()[:2]), "llm_rank": i + 1,
            "confidence": c["confidence"], "reason": c["reason"]} for i, c in enumerate(cands[:3])]
    return out, "ok" if out else "no answer"


def llm_candidates(plants, chapters, blind=0, seed=13):
    """Step 3: fill plants[name]['llm_candidates'] for records without a confident footnote
    species (plus `blind` footnoted ones, marked blind_sample=True, used only for evaluation)."""
    import random
    cache = json.loads(LLM_CACHE.read_text()) if LLM_CACHE.exists() else {}
    confident = sorted(r for r, p in plants.items()
                       if any(c["rank"] == "species" and c["confidence"] == "confident"
                              for c in p.get("footnote_candidates", [])))
    random.seed(seed)
    blind_set = set(random.sample(confident, min(blind, len(confident))))
    todo = [r for r in plants if r not in confident] + sorted(blind_set)
    print(f"step 3: asking the LLM about {len(todo)} records ({len(blind_set)} blind)")
    for i, r in enumerate(todo, 1):
        k = f'{plant_model()}|{LLM_PROMPT_VERSION}|{r}'
        if k not in cache:
            cands, status = ask_llm(r, plants, chapters)
            if status.startswith("error"):           # not cached, so a rerun tries again
                plants[r]["llm_candidates"], plants[r]["llm_status"] = [], status
                continue
            cache[k] = {"candidates": cands, "status": status}
            LLM_CACHE.parent.mkdir(parents=True, exist_ok=True)
            LLM_CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
        plants[r]["llm_candidates"], plants[r]["llm_status"] = cache[k]["candidates"], cache[k]["status"]
        if i % 10 == 0:
            print(f"  {i}/{len(todo)}")
    for r, p in plants.items():
        p.setdefault("llm_candidates", []); p.setdefault("llm_status", "not asked")
        p["blind_sample"] = r in blind_set
    return plants


# ---------------------------------------------------------------- step 4
# Decisions: see taxonomy.py (official WFO first, hackathon fallback, fuzzy closest candidate,
# genus kept when the species is unknown).

def wfo_check(plants):
    """Step 4: add a 'wfo' result to every footnote and LLM candidate."""
    from taxonomy import check_name
    names = [(c, c.get("rank", "species")) for p in plants.values()
             for c in p.get("footnote_candidates", []) + p.get("llm_candidates", [])]
    print(f"step 4: checking {len(names)} candidate names with WFO")
    for i, (c, rank) in enumerate(names, 1):
        c["wfo"] = check_name(c["name"], rank, author_hint=c.get("author_hint"))
        if i % 25 == 0:
            print(f"  {i}/{len(names)}")
    errors = sum(c["wfo"]["match_type"] == "error" for c, _ in names)
    if errors:
        print(f"  {errors} lookups failed (network); rerun later to retry them")
    return plants


# ---------------------------------------------------------------- step 5
# Decisions: geography EXCLUDES implausible candidates: a species whose known native range lies
# entirely outside the wider ancient world (Mediterranean, West and Central Asia, North Africa,
# plus the trade regions India and Northeast Africa). Unknown ranges and genus-level candidates
# are kept. v2: a CONFIDENT footnote name is never excluded by geography (the 1855 editors win).

def geography_check(plants):
    """Step 5: add 'geo' to every candidate found in WFO; mark implausible ones excluded."""
    from taxonomy import native_check
    n_checked = n_excluded = n_unknown = 0
    for p in plants.values():
        for c in p.get("footnote_candidates", []) + p.get("llm_candidates", []):
            w = c.get("wfo", {})
            if w.get("match_type") in (None, "not_found", "error"):
                continue
            c["geo"] = native_check(w["accepted_name"])
            n_checked += 1
            confident_fn = c.get("confidence") == "confident" and "llm_rank" not in c
            if c["geo"]["plausible"] is False and not confident_fn:
                c["excluded"] = "native range outside the ancient world"
                n_excluded += 1
            elif c["geo"]["plausible"] is None:
                n_unknown += 1
    print(f"step 5: {n_checked} candidates checked, {n_excluded} excluded, {n_unknown} with unknown range (kept)")
    return plants


# ---------------------------------------------------------------- step 6
# Decisions:
#  - a confident footnote species that fails (not in WFO, or excluded by geography) -> unresolved
#  - hedged footnote and LLM disagree (different genus) -> disputed, current best = footnote name
#  - the LLM answer that counts = its first candidate that passes WFO and geography
# Statuses: footnote | footnote+llm (hedged footnote confirmed by the LLM) | hedged_footnote |
#           llm | disputed | unresolved

USABLE = ("exact", "synonym", "fuzzy", "genus")


def clean_sci(s):
    from taxonomy import clean_name
    return clean_name(s)


def usable(c):
    return c.get("wfo", {}).get("match_type") in USABLE and not c.get("excluded")


def genus_of(c):
    return (c["wfo"].get("accepted_name") or "").split(" ")[0].lower()


def level_of(c):
    """'species' or 'genus': the level the final name is actually known at."""
    return "genus" if c.get("rank") == "genus" or c["wfo"]["match_type"] == "genus" else "species"


def decide(p):
    """Returns (status, best candidate or None, reason)."""
    fn = [c for c in p.get("footnote_candidates", [])
          if c.get("wfo", {}).get("match_type") != "not_found"]      # v2: "French ladies" is not a name
    confident = next((c for c in fn if c.get("rank") == "species" and c["confidence"] == "confident"), None)
    if confident:
        if usable(confident):
            return "footnote", confident, "confident footnote name"
        why = confident.get("excluded") or f"WFO: {confident.get('wfo', {}).get('match_type')}"
        return "unresolved", None, f"confident footnote name failed ({why})"
    hedged = next((c for c in fn if usable(c)), None)
    # blind answers are only for the accuracy test, unless the confident footnote turned out
    # not to be a WFO name at all (e.g. the 1855 typo "Pinpinella anisum"): then they may decide
    footnote_failed = any(c.get("rank") == "species" and c["confidence"] == "confident"
                          and c.get("wfo", {}).get("match_type") == "not_found"
                          for c in p.get("footnote_candidates", []))
    blind_ok = not p.get("blind_sample") or footnote_failed
    llm = next((c for c in p.get("llm_candidates", []) if usable(c)), None) if blind_ok else None
    if hedged and llm:
        if genus_of(hedged) == genus_of(llm):
            best = llm if level_of(hedged) == "genus" and level_of(llm) == "species" else hedged
            return "footnote+llm", best, "hedged footnote confirmed by the LLM (same genus)"
        return "disputed", hedged, "hedged footnote and LLM name different genera"
    if hedged:
        return "hedged_footnote", hedged, "hedged footnote only"
    if llm:
        return "llm", llm, f"LLM candidate #{llm['llm_rank']} ({llm['confidence']})"
    return "unresolved", None, "no usable name"


OVERRIDES = ROOT / CFG.get("plants", {}).get("overrides", "data/03_plants/overrides.csv")


def load_overrides():
    """overrides.csv: plant,scientific_name,note. scientific_name 'UNRESOLVED' forces unresolved.
    Decisions typed into the your_decision column of review.csv are merged in first."""
    rows = {}
    if OVERRIDES.exists():
        with open(OVERRIDES, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("plant") and r.get("scientific_name"):
                    rows[r["plant"].strip()] = r
    review = OVERRIDES.parent / "review.csv"
    if review.exists():
        with open(review, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d = (r.get("your_decision") or "").strip()
                if d:
                    rows[r["plant"].strip()] = {"plant": r["plant"].strip(), "scientific_name": d,
                                                "note": (r.get("your_note") or "from review.csv").strip()}
    if rows:
        OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
        with open(OVERRIDES, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["plant", "scientific_name", "note"])
            w.writeheader()
            for r in rows.values():
                w.writerow({k: r.get(k, "") for k in ("plant", "scientific_name", "note")})
    return rows


def decide_all(plants):
    """Step 6: add status, final name and reason to every plant record.
    Manual overrides (overrides.csv / review.csv) win over every automatic rule."""
    from taxonomy import check_name
    overrides = load_overrides()
    for name, p in plants.items():
        o = overrides.get(name)
        if o:
            sci = o["scientific_name"].strip()
            if sci.upper() == "UNRESOLVED":
                status, best, reason = "unresolved", None, f"manual: {o.get('note', '')}"
            else:
                cand = {"name": sci, "rank": "genus" if " " not in clean_sci(sci) else "species",
                        "confidence": "manual", "excerpt": o.get("note", "")}
                cand["wfo"] = check_name(cand["name"], cand["rank"])
                p["manual_candidate"] = cand
                if cand["wfo"]["match_type"] in USABLE:
                    status, best, reason = "manual", cand, f"manual: {o.get('note', '')}"
                else:
                    status, best, reason = "unresolved", None, f"manual name not found in WFO: {sci}"
            p.update(status=status, reason=reason, plant_id="plant:" + name.replace(" ", "_"),
                     accepted_name=best["wfo"]["accepted_name"] if best else None,
                     wfo_id=best["wfo"]["accepted_wfo_id"] if best else None,
                     level=level_of(best) if best else None, source="manual" if best else None)
            continue
        status, best, reason = decide(p)
        p.update(status=status, reason=reason, plant_id="plant:" + name.replace(" ", "_"),
                 accepted_name=best["wfo"]["accepted_name"] if best else None,
                 wfo_id=best["wfo"]["accepted_wfo_id"] if best else None,
                 level=level_of(best) if best else None,
                 source=("footnote" if best in p.get("footnote_candidates", []) else "llm") if best else None)
    return plants


# ---------------------------------------------------------------- step 7
# Decisions: claims whose plant is unresolved are dropped from claims_with_plants.jsonl (kept in
# claims_unresolved.jsonl so nothing is lost); review.csv lists disputed + unresolved plants;
# the report gives the numbers mentors look for: coverage, confidence, method and limitations.

OUT = ROOT / "data/03_plants"
STATUSES = ["manual", "footnote", "footnote+llm", "hedged_footnote", "llm", "disputed", "unresolved"]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def first_sentence(p, chapters):
    for ch in p["chapters"]:
        recs = [p["name"]]
        for para in chapters[ch]["paragraphs"]:
            for s in para["sentences"]:
                if last_mention(p["name"], s["text"], recs) >= 0:
                    return f"[{ch}.{s['sent_id']}] {s['text'][:200]}"
    return ""


def write_outputs(plants, claims, key, chapters, args):
    """Step 7: link claims to plants and write all outputs."""
    OUT.mkdir(parents=True, exist_ok=True)
    kept, dropped = [], []
    for c in claims:
        p = plants.get(key(c["plant_name_raw"], c["chapter"]))
        if not p:
            dropped.append(c); continue
        c = dict(c, plant_id=p["plant_id"], plant_status=p["status"], plant_accepted_name=p["accepted_name"],
                 plant_wfo_id=p["wfo_id"], plant_level=p["level"], plant_source=p["source"])
        (dropped if p["status"] == "unresolved" else kept).append(c)
    write_jsonl(OUT / "claims_with_plants.jsonl", kept)
    write_jsonl(OUT / "claims_unresolved.jsonl", dropped)
    write_jsonl(OUT / "plants.jsonl", plants.values())

    with open(OUT / "review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["plant", "why_listed", "status", "claims", "chapters", "current_best", "footnote_names",
                    "llm_names", "reason", "footnote_excerpt", "first_mention", "your_decision", "your_note"])
        ranked = sorted(plants.values(), key=lambda p: -p["n_claims"])
        top = {p["name"] for p in ranked[:args.review_top]}
        for p in ranked:
            listed = "disputed/unresolved" if p["status"] in ("disputed", "unresolved") else \
                     (f"top {args.review_top} by claims" if p["name"] in top and p["status"] != "manual" else None)
            if not listed:
                continue
            fn = "; ".join(f"{c['name']} ({c['confidence']}, WFO {c.get('wfo', {}).get('match_type')})"
                           for c in p["footnote_candidates"])
            llm = "; ".join(f"#{c['llm_rank']} {c['name']} ({c['confidence']}, WFO {c.get('wfo', {}).get('match_type')}"
                            + (", excluded" if c.get("excluded") else "") + ")" for c in p["llm_candidates"])
            excerpt = p["footnote_candidates"][0]["excerpt"] if p["footnote_candidates"] else ""
            w.writerow([p["name"], listed, p["status"], p["n_claims"], " ".join(map(str, p["chapters"])),
                        p["accepted_name"] or "", fn, llm, p["reason"], excerpt, first_sentence(p, chapters), "", ""])

    report = build_report(plants, kept, dropped, args)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (OUT / "report.md").write_text(report_markdown(report), encoding="utf-8")
    return report


def build_report(plants, kept, dropped, args):
    ps = list(plants.values())
    n_claims = len(kept) + len(dropped)
    by_status = {s: {"plants": sum(p["status"] == s for p in ps),
                     "claims": sum(p["n_claims"] for p in ps if p["status"] == s)} for s in STATUSES}
    resolved = [p for p in ps if p["status"] != "unresolved"]
    species = [p for p in resolved if p["level"] == "species"]
    cands = [c for p in ps for c in p["footnote_candidates"] + p["llm_candidates"]]
    blind = [p for p in ps if p.get("blind_sample")]
    def blind_hit(p, level):
        ref = next((c for c in p["footnote_candidates"] if c.get("rank") == "species" and c["confidence"] == "confident"
                    and c.get("wfo", {}).get("match_type") != "not_found"), None)
        if not ref:
            return False
        llm = next((c for c in p["llm_candidates"] if usable(c)), None)
        if not llm or not usable(ref):
            return False
        if level == "species":
            return llm["wfo"]["accepted_wfo_id"] == ref["wfo"]["accepted_wfo_id"]
        return genus_of(llm) == genus_of(ref)
    return {
        "run": {"date": date.today().isoformat(), "claims_file": str(args.claims), "model": plant_model(),
                "llm_prompt_version": LLM_PROMPT_VERSION, "llm_used": not args.no_llm,
                "taxonomy": "WFO Plant List API (official), hackathon wrapper as fallback; WCVP via hackathon wrapper"},
        "headline": {
            "plant_names": len(ps),
            "plant_names_resolved": len(resolved),
            "plant_names_species_level": len(species),
            "claims": n_claims,
            "claims_kept": len(kept),
            "claims_kept_share": round(len(kept) / n_claims, 3) if n_claims else None,
            "claims_species_level_share": round(sum(p["n_claims"] for p in species) / n_claims, 3) if n_claims else None,
            "plants_backed_by_1855_editors": by_status["footnote"]["plants"] + by_status["footnote+llm"]["plants"],
        },
        "by_status": by_status,
        "by_source": dict(Counter(p["source"] for p in resolved)),
        "wfo_match_types": dict(Counter(c.get("wfo", {}).get("match_type") for c in cands)),
        "excluded_by_geography": sum(bool(c.get("excluded")) for c in cands),
        "fuzzy_matches": sorted({f"{c['name']} -> {c['wfo'].get('matched_name')}" for c in cands
                                 if c.get("wfo", {}).get("match_type") == "fuzzy"}),
        "manual_overrides": sum(p["status"] == "manual" for p in ps),
        "top_plants": [{"plant": p["name"], "claims": p["n_claims"], "name": p["accepted_name"], "status": p["status"]}
                       for p in sorted(ps, key=lambda p: -p["n_claims"])[:15]],
        "blind_sample": ({"size": len(blind),
                          "same_species_as_1855_editors": round(sum(blind_hit(p, "species") for p in blind) / len(blind), 2),
                          "same_genus_as_1855_editors": round(sum(blind_hit(p, "genus") for p in blind) / len(blind), 2)}
                         if blind else "not run (use --blind N)"),
        "limitations": [
            "1855 footnote identifications are historical hypotheses, not ground truth.",
            "A footnote is only used when the plant is named in the same sentence before its marker.",
            "The geography rule excludes plants native only outside the wider ancient world, "
            "so traded imports (e.g. from India) can be wrongly excluded.",
            "Claims whose plant is unresolved are not checked against modern evidence.",
        ],
    }


def report_markdown(r):
    h = r["headline"]
    lines = ["# Plant resolution report", "",
             f"Run {r['run']['date']}, model `{r['run']['model']}`.", "",
             f"- **{h['plant_names_resolved']} of {h['plant_names']}** plant names resolved "
             f"({h['plant_names_species_level']} to species level)",
             f"- **{h['claims_kept']} of {h['claims']}** claims ({h['claims_kept_share']:.0%}) linked to a modern plant; "
             f"{h['claims_species_level_share']:.0%} at species level",
             f"- **{h['plants_backed_by_1855_editors']}** plant names backed by the 1855 editors' footnotes", "",
             "| Status | Plant names | Claims |", "| --- | --- | --- |"]
    lines += [f"| {s} | {v['plants']} | {v['claims']} |" for s, v in r["by_status"].items()]
    lines += ["", "## Most frequent plants", "", "| Pliny's name | Claims | Modern name | Status |", "| --- | --- | --- | --- |"]
    lines += [f"| {t['plant']} | {t['claims']} | {t['name'] or '–'} | {t['status']} |" for t in r["top_plants"]]
    if isinstance(r["blind_sample"], dict):
        b = r["blind_sample"]
        lines += ["", f"**LLM vs 1855 editors (blind, n={b['size']}):** same species {b['same_species_as_1855_editors']:.0%}, "
                      f"same genus {b['same_genus_as_1855_editors']:.0%}"]
    lines += ["", "## Limitations", ""] + [f"- {l}" for l in r["limitations"]]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claims", default=CFG["paths"]["claims_out"])
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--blind", type=int, default=0, help="blind sample of footnoted plants for the LLM")
    ap.add_argument("--review-top", type=int, default=30, help="also list the N most frequent plants in review.csv")
    args = ap.parse_args()
    claims = read_jsonl(args.claims)
    chapters = {c["chapter"]: c for c in read_jsonl(CFG["paths"]["chapters"])}
    plants, key = collect_names(claims, chapters)                                   # step 1
    print(f"step 1: {len(plants)} plant records from {len(claims)} claims")
    footnote_candidates(plants, chapters, load_notes())                             # step 2
    print(f"step 2: {sum(bool(p['footnote_candidates']) for p in plants.values())} records with footnote names")
    if args.no_llm:
        for p in plants.values():
            p.update(llm_candidates=[], llm_status="skipped", blind_sample=False)
    else:
        llm_candidates(plants, chapters, blind=args.blind)                          # step 3
    wfo_check(plants)                                                               # step 4
    geography_check(plants)                                                         # step 5
    decide_all(plants)                                                              # step 6
    report = write_outputs(plants, claims, key, chapters, args)                     # step 7
    print(report_markdown(report))
    print(f"outputs in {OUT}")


if __name__ == "__main__":
    main()
