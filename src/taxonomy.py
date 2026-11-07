"""Step 4: check plant names against World Flora Online (WFO).

    check_name("Atriplex hortensis of Linnæus")          # species candidate
    check_name("Chenopodium", rank="genus")              # genus candidate

returns {"input", "cleaned", "rank", "matched_name", "wfo_id",
         "accepted_name", "accepted_wfo_id", "match_type", "service"}

match_type:
  exact      WFO knows the name and it is accepted
  synonym    WFO knows the name; accepted_name is today's name for it
  fuzzy      same genus, species epithet differs only in spelling (silvestris = sylvestris),
             or several same-named entries (homonyms) exist and the author hint chose one
  genus      the species is unknown to WFO, but its genus is known (genus-level match)
  not_found  WFO knows neither species nor genus (e.g. an animal or a non-name)
  error      both services failed (not cached, so the next run tries again)

Decisions: official WFO API first, hackathon wrapper as fallback when the official one is
unreachable; fuzzy matches only within the same genus, species rank, spelling-level differences
(v2: "Lactuca silvestris" can no longer jump to "Lactuca siamensis"); keep the genus when the
species is unknown. Every answer is cached in data/03_plants/taxonomy_cache.json.

Quick test:  python src/taxonomy.py "Atriplex hortensis" "Malva silvestris"
             add --debug to print WFO's raw answer
"""
import json, re, sys, time
from difflib import SequenceMatcher
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/config.json").read_text())
TAX = CFG.get("taxonomy", {})
CACHE_PATH = ROOT / TAX.get("cache", "data/03_plants/taxonomy_cache_v3.json")   # v3: WFO match wins, Linnaeus preferred
WFO_MATCH = "https://list.worldfloraonline.org/matching_rest.php"
WFO_GQL = "https://list.worldfloraonline.org/gql.php"
HACKATHON_URL = TAX.get("hackathon_wfo_url", "http://wfo.ethcstwin.di.uoa.gr:65000")
MIN_EPITHET = 0.85       # spelling variants of the species epithet must be at least this similar
ACCEPTED_QUERY = """query ($id: String!) {
  taxonNameById(nameId: $id) {
    id fullNameStringPlain
    currentPreferredUsage { hasName { id fullNameStringPlain } }
  }
}"""

_cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}


class ServiceDown(Exception):
    """The service could not be reached or answered with an error."""


# ---------- cleaning ----------
def clean_name(name, rank="species"):
    """'Atri- plex hortensis of Linnæus' -> 'Atriplex hortensis'; genus rank keeps one word."""
    s = (name or "").replace("æ", "ae").replace("Æ", "Ae").replace("œ", "oe").replace("ë", "e")
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)
    words = re.findall(r"[A-Za-z]+", s)
    if not words:
        return ""
    genus = words[0].capitalize()
    if rank == "genus":
        return genus
    epithet = words[1].lower() if len(words) > 1 and words[1][0].islower() else ""
    return f"{genus} {epithet}".strip()


def plain(name):
    """'Atriplex hortensis L.' -> 'atriplex hortensis' (drop authors) for comparisons."""
    words = (name or "").split()
    return " ".join(words[:2] if len(words) > 1 and words[1][:1].islower() else words[:1]).lower()


# ---------- official WFO ----------
INFRA = re.compile(r"\b(var|subsp|ssp|f|forma|cv|nothosubsp)\.\s", re.I)


def norm_epithet(e):
    """Spelling-tolerant form of an epithet: sylvestris = silvestris, sativum = sativus, ..."""
    e = (e or "").lower().replace("y", "i").replace("ae", "e").replace("ph", "f").replace("th", "t")
    e = re.sub(r"(.)\1", r"\1", e)                        # double letters
    return re.sub(r"(um|us|a|is|e)$", "", e)                 # Latin gender endings


def split_name(full):
    """'Malva sylvestris L.' -> ('malva', 'sylvestris', 'L.'); infraspecific names -> None."""
    if not full or INFRA.search(full):
        return None
    w = full.split()
    if len(w) < 2 or not w[1][:1].islower():
        return (w[0].lower(), "", " ".join(w[1:])) if w else None
    return w[0].lower(), w[1].lower(), " ".join(w[2:])


def pick_candidate(cleaned, candidates, author_hint=None, wfo_match_id=None):
    """Strict choice among WFO candidates for a species name:
    same genus, species rank (no var./subsp.), epithet equal after spelling normalisation
    or at least MIN_EPITHET similar; among homonyms prefer the author hint (e.g. 'L.')."""
    genus, epithet = cleaned.lower().split(" ", 1)
    ok = []
    for c in candidates:
        parts = split_name(c.get("full_name_plain"))
        if not parts or not parts[1]:
            continue
        if parts[0] != genus:
            # a misspelt genus ("Menta" for "Mentha") is allowed only with an identical epithet
            if SequenceMatcher(None, parts[0], genus).ratio() < 0.85 or norm_epithet(parts[1]) != norm_epithet(epithet):
                continue
        same = norm_epithet(parts[1]) == norm_epithet(epithet) and parts[0] == genus
        score = 1.0 if same else SequenceMatcher(None, norm_epithet(parts[1]), norm_epithet(epithet)).ratio()
        if score >= MIN_EPITHET:
            author = parts[2].replace(" ", "")
            hint = (author_hint or "L.").replace(" ", "")     # default: Linnaeus, the classic Old World names
            author_ok = author == hint or author.startswith(hint + "(") or author.endswith(")" + hint)
            is_wfo_match = c.get("wfo_id") is not None and c.get("wfo_id") == wfo_match_id
            ok.append((score, is_wfo_match, author_ok, parts[1] == epithet, c))
    if not ok:
        return None, None
    ok.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
    best = ok[0]
    if best[1]:                                              # WFO's own unambiguous match wins
        return best[4], "exact" if best[3] else "fuzzy"
    ties = [t[4] for t in ok if t[0] == best[0] and t[2] == best[2]]
    if len(ties) > 1:                     # homonyms without a deciding author: keep the entry whose
        for c in ties:                    # accepted name stays in the same genus (the botanical meaning)
            acc_name, _ = _official_accepted(c.get("wfo_id"))
            if acc_name and acc_name.split()[0].lower() == genus:
                return c, "fuzzy"
        return ties[0], "fuzzy"
    how = "exact" if best[3] and len([t for t in ok if t[0] == best[0]]) == 1 else "fuzzy"
    return best[4], how


def _official_match(cleaned, author_hint=None, debug=False):
    """(matched_name, wfo_id, how) from the official matching API, or (None, None, None)."""
    try:
        r = requests.get(WFO_MATCH, params={"input_string": cleaned}, timeout=30)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        raise ServiceDown(str(e))
    if debug:
        print(json.dumps(data, indent=1)[:3000])
    if " " not in cleaned:                                    # genus lookup
        m = data.get("match")
        if m and split_name(m.get("full_name_plain")) and split_name(m["full_name_plain"])[0] == cleaned.lower():
            return m.get("full_name_plain"), m.get("wfo_id"), "exact"
        for c in data.get("candidates") or []:
            parts = split_name(c.get("full_name_plain"))
            if parts and parts[0] == cleaned.lower() and not parts[1]:
                return c.get("full_name_plain"), c.get("wfo_id"), "exact"
        return None, None, None
    pool = ([data["match"]] if data.get("match") else []) + list(data.get("candidates") or [])
    match_id = (data.get("match") or {}).get("wfo_id")
    chosen, how = pick_candidate(cleaned, pool, author_hint, match_id)
    if chosen:
        return chosen.get("full_name_plain"), chosen.get("wfo_id"), how
    return None, None, None


def _official_accepted(wfo_id):
    """(accepted name, accepted id) for a WFO name id; falls back to the id itself."""
    try:
        r = requests.post(WFO_GQL, json={"query": ACCEPTED_QUERY, "variables": {"id": wfo_id}}, timeout=30)
        r.raise_for_status()
        node = (r.json().get("data") or {}).get("taxonNameById") or {}
        usage = (node.get("currentPreferredUsage") or {}).get("hasName") or {}
        return usage.get("fullNameStringPlain"), usage.get("id")
    except (requests.RequestException, ValueError):
        return None, None


# ---------- hackathon wrapper (fallback) ----------
def _hackathon_match(cleaned, author_hint=None):
    """SHAFA: fill in from the wrapper's /docs page (HACKATHON_URL + '/docs').
    Must return (matched_name, wfo_id, how) like _official_match, how = 'exact' or 'fuzzy',
    or (None, None, None) if the name is unknown. Raise ServiceDown on network errors."""
    raise ServiceDown("hackathon wrapper not connected yet")


# ---------- public ----------
def check_name(name, rank="species", author_hint=None, debug=False):
    """author_hint: e.g. 'L.' when the source says 'of Linnaeus' (picks the right homonym)."""
    cleaned = clean_name(name, rank)
    result = {"input": name, "cleaned": cleaned, "rank": rank, "matched_name": None, "wfo_id": None,
              "accepted_name": None, "accepted_wfo_id": None, "match_type": "not_found", "service": None}
    if not cleaned or (rank == "species" and " " not in cleaned):
        return result
    key = f"{rank}|{cleaned}|{author_hint or ''}"
    if key in _cache and not debug:
        return _cache[key]

    def lookup(query):
        try:
            return _official_match(query, author_hint, debug) + ("official",)
        except ServiceDown:
            try:
                return _hackathon_match(query, author_hint) + ("hackathon",)
            except ServiceDown as e:
                raise ServiceDown(f"both services failed: {e}")

    try:
        matched, wfo_id, how, service = lookup(cleaned)
        if not matched and rank == "species":                  # species unknown: try the genus
            g_matched, g_id, _, service = lookup(cleaned.split()[0])
            if g_matched:
                matched, wfo_id, how = g_matched, g_id, "genus"
        if matched:
            acc_name, acc_id = _official_accepted(wfo_id) if service == "official" else (None, None)
            result.update(matched_name=matched, wfo_id=wfo_id, service=service,
                          accepted_name=acc_name or matched, accepted_wfo_id=acc_id or wfo_id,
                          match_type="synonym" if how == "exact" and acc_id and acc_id != wfo_id else how)
        time.sleep(0.2)                                         # be polite to the servers
    except ServiceDown as e:
        result.update(match_type="error", error=str(e)[:200])
        return result                                           # not cached: retried next run
    _cache[key] = result
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, indent=1, ensure_ascii=False))
    return result


# ---------- step 5: native distribution (hackathon WCVP wrapper) ----------
# Decision: wider ancient world = WGSRPD level-2 regions 12 SW Europe, 13 SE Europe,
# 20 Northern Africa, 32 Middle Asia, 33 Caucasus, 34 Western Asia, 35 Arabian Peninsula,
# plus the Roman trade regions 40 Indian Subcontinent and 24 Northeast Tropical Africa
# (basil, cucumber, pepper, costus, myrrh reached Rome from there).
ANCIENT_WORLD_L3 = {
    "BAL", "COR", "FRA", "POR", "SAR", "SPA",                          # 12 Southwestern Europe
    "ALB", "BUL", "GRC", "ITA", "KRI", "SIC", "TUE", "YUG",            # 13 Southeastern Europe
    "ALG", "EGY", "LBY", "MOR", "TUN", "WSA",                          # 20 Northern Africa
    "KAZ", "KGZ", "TKM", "TZK", "UZB",                                 # 32 Middle Asia
    "NCS", "TCS",                                                      # 33 Caucasus
    "AFG", "CYP", "EAI", "IRN", "IRQ", "LBS", "PAK", "PAL", "SIN", "TUR",   # 34 Western Asia
    "GST", "KUW", "OMA", "SAU", "YEM",                                 # 35 Arabian Peninsula
    "ASS", "BAN", "EHM", "IND", "LDV", "MDV", "NEP", "SRL", "WHM",     # 40 Indian Subcontinent
    "CHA", "DJI", "ERI", "ETH", "SOC", "SOM", "SUD",                   # 24 Northeast Tropical Africa
}
WCVP_URL = TAX.get("hackathon_wcvp_url", "http://wcvp.ethcstwin.di.uoa.gr:65000")


def _wcvp_native_areas(accepted_name):
    """SHAFA: fill in from the WCVP wrapper's /docs page (WCVP_URL + '/docs').
    Must return the list of WGSRPD level-3 codes where the taxon is NATIVE (not introduced),
    [] if WCVP knows the taxon but lists no native areas, or None if the taxon is unknown.
    Raise ServiceDown on network errors."""
    raise ServiceDown("hackathon WCVP wrapper not connected yet")


def native_check(accepted_name):
    """{'native_areas': [...] or None, 'plausible': True / False / None}.
    plausible = False only when native areas are known and none lies in the ancient world;
    unknown distributions (e.g. crops known only from cultivation) stay None and are kept."""
    name = plain(accepted_name)
    if " " not in name:                                     # genus-level: no geography check
        return {"native_areas": None, "plausible": None}
    key = f"native|{name}"
    if key in _cache:
        return _cache[key]
    try:
        areas = _wcvp_native_areas(accepted_name)
    except ServiceDown as e:
        return {"native_areas": None, "plausible": None, "error": str(e)[:200]}   # not cached
    plausible = None if not areas else bool(set(areas) & ANCIENT_WORLD_L3)
    _cache[key] = {"native_areas": areas, "plausible": plausible}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, indent=1, ensure_ascii=False))
    return _cache[key]


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--debug"]
    for n in args or ["Atriplex hortensis", "Menta silvestris", "Lactuca silvestris", "Coluber cerastes"]:
        print(json.dumps(check_name(n, debug="--debug" in sys.argv), indent=2, ensure_ascii=False))
