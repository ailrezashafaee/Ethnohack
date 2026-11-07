"""Stage 2: extract remedy and harm claims from each chapter with a local LLM (Ollama).

Usage:
    python src/extract.py --chapters 20            # one chapter (e.g. a dev chapter)
    python src/extract.py --all                     # every chapter in chapters.jsonl
    python src/extract.py --chapters 20 --dry-run   # print the prompts, no LLM call
    python src/extract.py --chapters 20 --redo      # extract a finished chapter again

The LLM gets the chapter in paragraph windows (max_chars_per_call) with a few preceding sentences
as context, and returns one entry per treatment with a list of indications; the script expands that
into one claim per condition. A quote is located in the sentence ignoring case, punctuation and
spacing and stored as the exact source span; quotes that cannot be found are dropped and logged.
Finished chapters (logged as chapter_done without LLM errors) are skipped on rerun.
"""
import argparse, json, re, sys, time, unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/config.json").read_text())
EXT = CFG["extraction"]

FIELDS = ["sent_id", "quote", "claim_type", "indications", "plant_name_raw", "plant_part",
          "preparation", "route", "route_inferred", "attribution", "attributed_to", "stance"]
SHARED = [f for f in FIELDS if f != "indications"]
OUT_FIELDS = ["claim_type", "sent_id", "quote", "plant_name_raw", "plant_part", "preparation",
              "route", "route_inferred", "indication_raw", "attribution", "attributed_to", "stance"]
ENUMS = {
    "claim_type": ["remedy", "harm"],
    "plant_part": ["leaf", "root", "seed", "fruit", "flower", "bark", "juice", "bulb", "whole", "other"],
    "route": ["oral", "topical", "inhaled", "amulet_ritual", "other"],
    "attribution": ["pliny", "named", "magi", "hearsay"],
    "stance": ["endorses", "neutral", "doubtful"],
}
NULLABLE = {"plant_part", "preparation", "route", "attributed_to"}

RULES = (
    "You extract medical claims from Pliny the Elder's Natural History (English translation, 1855).\n"
    '\n'
    'A claim says that a plant, a part of it, or a product made from it\n'
    '- treats, prevents, relieves or helps with a condition of the human body: "remedy";\n'
    '- causes or worsens a condition of the human body: "harm".\n'
    '\n'
    'Counts as a claim:\n'
    '- medicinal uses, including against bites, stings and poisons;\n'
    '- effects on the body of eating or drinking the plant as food ("acts as an aperient", "eaten as a remedy for indigestion");\n'
    '- cosmetic uses on the body (hair, skin, complexion);\n'
    '- uses as an amulet or charm (attached to the body, worn, carried).\n'
    'Does not count: what the plant looks like, where it grows, gardening, harvesting, storing, cooking or taste;\n'
    'effects on animals or other plants; statements too vague to check ("it causes numerous diseases", "it is wholesome").\n'
    '\n'
    'Input: the chapter title, then numbered sentences such as [2.3]. Lines marked [context] only help you\n'
    'resolve "it", "they" or "he"; never take claims from them.\n'
    '\n'
    'Output one entry per treatment. A treatment is one way of using the plant (one preparation and one route)\n'
    'together with every condition the text links to it:\n'
    '- "good for A, B and C" is one entry with indications ["A", "B", "C"];\n'
    '- the same condition treated in two different ways gives two entries;\n'
    '- a remedy and a harm are always separate entries.\n'
    '\n'
    'Fields:\n'
    '- sent_id: id of the sentence where the quote starts.\n'
    '- quote: the shortest span stating the treatment and its conditions, copied exactly from the sentence.\n'
    '  Never paraphrase and never change words inside the span.\n'
    '- claim_type: "remedy" or "harm".\n'
    "- indications: each condition in Pliny's words, without the verb of treating and without the preparation\n"
    '  ("scrofulous sores", not "cleanses scrofulous sores"). Use "to ..." or "as an ..." for purposes\n'
    '  ("to purge the bowels", "as an emetic").\n'
    '- plant_name_raw: the plant as Pliny names it, singular, with any qualifier ("wild orage", "white beet").\n'
    '  For "it" or "they", use the plant referred to, usually the plant of the chapter.\n'
    '- plant_part: leaf, root, seed, fruit, flower, bark, juice, bulb or whole when that part is used; other for\n'
    '  any other part (peel, rind, shavings); null when no part is named. When "it" continues a sentence about\n'
    '  the juice, the part is still juice.\n'
    '- preparation: how it is prepared, mixed or applied, short and in Pliny\'s words ("boiled in wine",\n'
    '  "mixed with honey, as a liniment", "taken in red wine", "eaten"). Null only if nothing is said.\n'
    '- route: oral (eaten, drunk, chewed, taken, gargled, given as food or drink); topical (applied, rubbed on,\n'
    '  liniment, ointment, poultice, put into the ears, eyes or nostrils, used on skin, hair, nails or wounds);\n'
    '  inhaled (smelled, fumes); amulet_ritual (attached to or worn on the body); other (pessary, suppository,\n'
    '  anything else); null if it cannot be told.\n'
    '- route_inferred: true when the route is not stated in the quote but follows from it; otherwise false.\n'
    '- attribution: "pliny" when no source is given; "named" when a person or school is named; "magi" for the\n'
    '  Magi; "hearsay" for "it is said", "some persons", "many persons", "they say", "some writers" and any other\n'
    '  unnamed source. "He" and "they" refer back to the last source named. "It is said that X, and that Y"\n'
    '  makes both X and Y hearsay.\n'
    '- attributed_to: the name(s) when attribution is "named", separated by "; "; otherwise null.\n'
    '- stance: "endorses" only for explicit praise ("excellent", "remarkably efficacious", "particularly good",\n'
    '  "still more efficacious"); "doubtful" only for explicit doubt ("if true", "absurd", "I am at a loss");\n'
    '  otherwise "neutral". Plain words like "good", "useful" or "advantageously" are neutral.\n'
    '\n'
    'Return JSON only: {"claims": [ ... ]}. Return {"claims": []} when the sentences contain no claim.\n'
)

# Worked examples from chapters that are not scored (never from gold dev/test chapters).
EXAMPLES = json.loads(r'''
[
{"chapter": 4, "sent_ids": ["2.1"], "claims": [{"sent_id": "2.1", "quote": "Elaterium promotes the menstrual discharge", "claim_type": "remedy", "indications": ["to promote the menstrual discharge"], "plant_name_raw": "elaterium", "plant_part": null, "preparation": null, "route": "oral", "route_inferred": true, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.1", "quote": "if taken by females when pregnant, it is productive of abortion", "claim_type": "harm", "indications": ["abortion"], "plant_name_raw": "elaterium", "plant_part": null, "preparation": null, "route": "oral", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}]},
{"chapter": 6, "sent_ids": ["2.1", "2.2"], "claims": [{"sent_id": "2.1", "quote": "The smell of the cucumber itself is a restorative in fainting fits", "claim_type": "remedy", "indications": ["fainting fits"], "plant_name_raw": "cucumber", "plant_part": null, "preparation": "smelled", "route": "inhaled", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}]},
{"chapter": 21, "sent_ids": ["2.4"], "claims": [{"sent_id": "2.4", "quote": "Leeks are eaten, too, in cases of poisoning by fungi", "claim_type": "remedy", "indications": ["poisoning by fungi"], "plant_name_raw": "leek", "plant_part": null, "preparation": "eaten", "route": "oral", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.4", "quote": "are applied topically to wounds", "claim_type": "remedy", "indications": ["wounds"], "plant_name_raw": "leek", "plant_part": null, "preparation": null, "route": "topical", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.4", "quote": "they act also as an aphrodisiac, allay thirst, and dispel the effects of drunkenness", "claim_type": "remedy", "indications": ["as an aphrodisiac", "thirst", "the effects of drunkenness"], "plant_name_raw": "leek", "plant_part": null, "preparation": null, "route": "oral", "route_inferred": true, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.4", "quote": "they have the effect of weakening the sight and causing flatulency, it is said", "claim_type": "harm", "indications": ["weakening the sight", "flatulency"], "plant_name_raw": "leek", "plant_part": null, "preparation": null, "route": "oral", "route_inferred": true, "attribution": "hearsay", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.4", "quote": "act as an aperient", "claim_type": "remedy", "indications": ["as an aperient"], "plant_name_raw": "leek", "plant_part": null, "preparation": null, "route": "oral", "route_inferred": true, "attribution": "hearsay", "attributed_to": null, "stance": "neutral"}]},
{"chapter": 27, "sent_ids": ["3.1"], "claims": [{"sent_id": "3.1", "quote": "A liniment of white beet-root applied to the forehead, arrests defluxions of the eyes", "claim_type": "remedy", "indications": ["defluxions of the eyes"], "plant_name_raw": "white beet", "plant_part": "root", "preparation": "as a liniment, applied to the forehead", "route": "topical", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "3.1", "quote": "mixed with a little alum it is an excellent remedy for erysipelas", "claim_type": "remedy", "indications": ["erysipelas"], "plant_name_raw": "white beet", "plant_part": "root", "preparation": "mixed with a little alum", "route": "topical", "route_inferred": true, "attribution": "pliny", "attributed_to": null, "stance": "endorses"}]},
{"chapter": 47, "sent_ids": ["1.2", "1.3"], "claims": [{"sent_id": "1.3", "quote": "Taken in drink or applied topically, it is an excellent remedy for the stings of serpents", "claim_type": "remedy", "indications": ["stings of serpents"], "plant_name_raw": "buselinon", "plant_part": null, "preparation": "taken in drink", "route": "oral", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "endorses"}, {"sent_id": "1.3", "quote": "Taken in drink or applied topically, it is an excellent remedy for the stings of serpents", "claim_type": "remedy", "indications": ["stings of serpents"], "plant_name_raw": "buselinon", "plant_part": null, "preparation": null, "route": "topical", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "endorses"}]},
{"chapter": 52, "sent_ids": ["2.3", "2.4"], "claims": [{"sent_id": "2.3", "quote": "The juice of it is injected into the ears for worms breeding there", "claim_type": "remedy", "indications": ["worms breeding in the ears"], "plant_name_raw": "wild mint", "plant_part": "juice", "preparation": "injected into the ears", "route": "topical", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.3", "quote": "it is taken also for jaundice", "claim_type": "remedy", "indications": ["jaundice"], "plant_name_raw": "wild mint", "plant_part": "juice", "preparation": null, "route": "oral", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.3", "quote": "is employed in liniments for scrofulous sores", "claim_type": "remedy", "indications": ["scrofulous sores"], "plant_name_raw": "wild mint", "plant_part": "juice", "preparation": "in liniments", "route": "topical", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.4", "quote": "It prevents the recurrence of lascivious dreams", "claim_type": "remedy", "indications": ["the recurrence of lascivious dreams"], "plant_name_raw": "wild mint", "plant_part": "juice", "preparation": null, "route": "oral", "route_inferred": true, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "2.4", "quote": "taken in vinegar, it expels tape-worm", "claim_type": "remedy", "indications": ["tape-worm"], "plant_name_raw": "wild mint", "plant_part": "juice", "preparation": "taken in vinegar", "route": "oral", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}]},
{"chapter": 84, "sent_ids": ["3.4", "3.5"], "claims": [{"sent_id": "3.4", "quote": "With the addition of human saliva, the mallow cleanses scrofulous sores, imposthumes of the parotid glands, and inflammatory tumours", "claim_type": "remedy", "indications": ["scrofulous sores", "imposthumes of the parotid glands", "inflammatory tumours"], "plant_name_raw": "mallow", "plant_part": null, "preparation": "with human saliva", "route": "topical", "route_inferred": true, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "3.5", "quote": "The seed of it, taken in red wine, disperses phlegm and relieves nausea", "claim_type": "remedy", "indications": ["phlegm", "nausea"], "plant_name_raw": "mallow", "plant_part": "seed", "preparation": "taken in red wine", "route": "oral", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}, {"sent_id": "3.5", "quote": "the root, attached to the person with black wool, is a remedy for affections of the mamillæ", "claim_type": "remedy", "indications": ["affections of the mamillæ"], "plant_name_raw": "mallow", "plant_part": "root", "preparation": "attached to the person with black wool", "route": "amulet_ritual", "route_inferred": false, "attribution": "pliny", "attributed_to": null, "stance": "neutral"}]}
]
''')

SCHEMA = {'$defs': {'Attribution': {'enum': ['pliny', 'named', 'magi', 'hearsay'],
                           'title': 'Attribution',
                           'type': 'string'},
           'ClaimType': {'enum': ['remedy', 'harm'], 'title': 'ClaimType', 'type': 'string'},
           'LLMClaim': {'additionalProperties': False,
                        'properties': {'sent_id': {'title': 'Sent Id', 'type': 'string'},
                                       'quote': {'minLength': 1,
                                                 'title': 'Quote',
                                                 'type': 'string'},
                                       'claim_type': {'$ref': '#/$defs/ClaimType'},
                                       'indications': {'items': {'type': 'string'},
                                                       'title': 'Indications',
                                                       'type': 'array'},
                                       'plant_name_raw': {'title': 'Plant Name Raw',
                                                          'type': 'string'},
                                       'plant_part': {'anyOf': [{'$ref': '#/$defs/PlantPart'},
                                                                {'type': 'null'}]},
                                       'preparation': {'anyOf': [{'type': 'string'},
                                                                 {'type': 'null'}],
                                                       'title': 'Preparation'},
                                       'route': {'anyOf': [{'$ref': '#/$defs/Route'},
                                                           {'type': 'null'}]},
                                       'route_inferred': {'title': 'Route Inferred',
                                                          'type': 'boolean'},
                                       'attribution': {'$ref': '#/$defs/Attribution'},
                                       'attributed_to': {'anyOf': [{'type': 'string'},
                                                                   {'type': 'null'}],
                                                         'title': 'Attributed To'},
                                       'stance': {'$ref': '#/$defs/Stance'}},
                        'required': ['sent_id',
                                     'quote',
                                     'claim_type',
                                     'indications',
                                     'plant_name_raw',
                                     'plant_part',
                                     'preparation',
                                     'route',
                                     'route_inferred',
                                     'attribution',
                                     'attributed_to',
                                     'stance'],
                        'title': 'LLMClaim',
                        'type': 'object'},
           'PlantPart': {'enum': ['leaf',
                                  'root',
                                  'seed',
                                  'fruit',
                                  'flower',
                                  'bark',
                                  'juice',
                                  'bulb',
                                  'whole',
                                  'other'],
                         'title': 'PlantPart',
                         'type': 'string'},
           'Route': {'enum': ['oral', 'topical', 'inhaled', 'amulet_ritual', 'other'],
                     'title': 'Route',
                     'type': 'string'},
           'Stance': {'enum': ['endorses', 'neutral', 'doubtful'],
                      'title': 'Stance',
                      'type': 'string'}},
 'additionalProperties': False,
 'properties': {'claims': {'items': {'$ref': '#/$defs/LLMClaim'},
                           'title': 'Claims',
                           'type': 'array'}},
 'required': ['claims'],
 'title': 'LLMExtraction',
 'type': 'object'}


# ---------------------------------------------------------------- text helpers
def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def fold(text):
    """Letters and digits only, case-folded and without accents; index maps back to text."""
    chars, index = [], []
    for pos, ch in enumerate(text):
        for part in unicodedata.normalize("NFKD", ch):
            if part.isalnum():
                f = part.casefold()
                chars.append(f)
                index.extend([pos] * len(f))
    return "".join(chars), index


def find_span(text, fragment, min_chars=3):
    """(start, end) of fragment in text, ignoring case, punctuation and spacing; or None."""
    needle, _ = fold(fragment)
    if len(needle) < min_chars:
        return None
    hay, index = fold(text)
    at = hay.find(needle)
    if at < 0:
        return None
    return index[at], index[at + len(needle) - 1] + 1


def load_jsonl(path):
    p = ROOT / path
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()] if p.exists() else []


def write_jsonl(path, rows, mode="w"):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open(mode, encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def sentences(ch):
    return [(p, s) for p in ch["paragraphs"] for s in p["sentences"]]


def sent_key(sent_id):
    return [int(x) for x in sent_id.split(".")]


# ---------------------------------------------------------------- prompts
def render(ch, window, context=()):
    lines = [ch["title"]] + [f"[context] {s['text']}" for s in context]
    return "\n".join(lines + [f"[{s['sent_id']}] {s['text']}" for _, s in window])


def windows(ch):
    """Paragraph groups up to max_chars_per_call, each with the preceding context sentences."""
    groups, cur, size = [], set(), 0
    for p in ch["paragraphs"]:
        if cur and size + len(p["text"]) > EXT["max_chars_per_call"]:
            groups.append(cur); cur, size = set(), 0
        cur.add(p["paragraph"]); size += len(p["text"])
    groups.append(cur)
    pairs = sentences(ch)
    for g in groups:
        idx = [i for i, (p, _) in enumerate(pairs) if p["paragraph"] in g]
        if idx:
            first = idx[0]
            context = [s for _, s in pairs[max(0, first - EXT["context_sentences"]):first]]
            yield [pairs[i] for i in idx], context


def sentence_window(ch, sent_ids):
    window = [(p, s) for p, s in sentences(ch) if s["sent_id"] in set(sent_ids)]
    missing = set(sent_ids) - {s["sent_id"] for _, s in window}
    if missing:
        raise ValueError(f"chapter {ch['chapter']} has no sentences {sorted(missing)}")
    return window


def answer(claims):
    """The assistant message for a worked example, in the same compact form as the model's answers."""
    return json.dumps({"claims": [{k: c[k] for k in FIELDS} for c in claims]},
                      ensure_ascii=False, separators=(",", ":"))


def gold_as_answer(rows):
    """Gold claims (one per condition) grouped back into treatments with a list of indications."""
    grouped = {}
    for g in sorted(rows, key=lambda g: sent_key(g["sent_id"])):
        shared = {k: g.get(k) for k in SHARED}
        key = json.dumps(shared, sort_keys=True)
        grouped.setdefault(key, {**shared, "indications": []})["indications"].append(g["indication_raw"])
    return list(grouped.values())


def check_examples(by_ch, gold):
    scored = {g["chapter"] for g in gold} - set(CFG["few_shot_chapters"])
    for ex in EXAMPLES:
        if ex["chapter"] in scored:
            raise ValueError(f"prompt example taken from scored gold chapter {ex['chapter']}")
        window = sentence_window(by_ch[ex["chapter"]], ex["sent_ids"])
        for c in ex["claims"]:
            if locate(c["quote"], c["sent_id"], window) is None:
                raise ValueError(f"prompt example quote not found in chapter {ex['chapter']}: {c['quote']!r}")


def few_shot_messages(by_ch, gold, exclude):
    msgs = []
    for n in CFG["few_shot_chapters"]:
        if n == exclude or n in CFG["test_chapters"] or n not in by_ch:
            continue
        rows = [g for g in gold if g["chapter"] == n and g.get("split") == "dev"]
        if rows:
            ch = by_ch[n]
            msgs += [{"role": "user", "content": render(ch, sentences(ch))},
                     {"role": "assistant", "content": answer(gold_as_answer(rows))}]
    for ex in EXAMPLES:
        if ex["chapter"] == exclude:
            continue
        ch = by_ch[ex["chapter"]]
        msgs += [{"role": "user", "content": render(ch, sentence_window(ch, ex["sent_ids"]))},
                 {"role": "assistant", "content": answer(ex["claims"])}]
    return msgs


def build_prompts(ch, by_ch, gold):
    shots = few_shot_messages(by_ch, gold, exclude=ch["chapter"])
    for window, context in windows(ch):
        yield window, [{"role": "system", "content": RULES}, *shots,
                       {"role": "user", "content": render(ch, window, context)}]


# ---------------------------------------------------------------- LLM
def call_llm(messages):
    llm = CFG["llm"]
    body = {"model": llm["model"], "messages": messages, "stream": False, "format": SCHEMA,
            "think": llm.get("think", False),
            "options": {"temperature": llm["temperature"], "num_ctx": llm["num_ctx"],
                        "num_predict": EXT["num_predict"], "repeat_penalty": EXT["repeat_penalty"]}}
    error = None
    for attempt in range(1, EXT["retries"] + 1):
        try:
            r = requests.post(llm["ollama_url"], json=body, timeout=llm["timeout_s"])
            r.raise_for_status()
            return r.json()["message"]["content"]
        except (requests.RequestException, KeyError, ValueError) as e:
            error = e
            if attempt < EXT["retries"]:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Ollama call failed after {EXT['retries']} attempts: {error}")


def salvage(content):
    """Complete claim objects from a truncated JSON answer."""
    start = content.find("[")
    if start < 0:
        return []
    decoder, claims, pos = json.JSONDecoder(), [], start + 1
    while True:
        while pos < len(content) and content[pos] in " \t\r\n,":
            pos += 1
        try:
            item, pos = decoder.raw_decode(content, pos)
        except json.JSONDecodeError:
            return claims
        if isinstance(item, dict):
            claims.append(item)


def problem(raw):
    """Why an LLM entry is not a valid treatment, or None."""
    if not isinstance(raw, dict):
        return "not an object"
    if set(raw) != set(FIELDS):
        return f"fields {sorted(set(raw) ^ set(FIELDS))}"
    for k in ("sent_id", "quote", "plant_name_raw", "preparation", "attributed_to"):
        if not isinstance(raw[k], str) and not (k in NULLABLE and raw[k] is None):
            return f"{k} is not a string"
    if not raw["quote"]:
        return "empty quote"
    if not isinstance(raw["indications"], list) or not all(isinstance(i, str) for i in raw["indications"]):
        return "indications is not a list of strings"
    if not isinstance(raw["route_inferred"], bool):
        return "route_inferred is not a boolean"
    for k, allowed in ENUMS.items():
        if raw[k] not in allowed and not (k in NULLABLE and raw[k] is None):
            return f"{k} {raw[k]!r} not allowed"
    return None


def parse(content, chapter, log):
    try:
        raw_claims = json.loads(content)["claims"]
    except json.JSONDecodeError:
        raw_claims = salvage(content)
        log.append({"chapter": chapter, "issue": "truncated_response", "salvaged": len(raw_claims)})
    except (KeyError, TypeError) as e:
        log.append({"chapter": chapter, "issue": "invalid_json", "error": str(e)[:200]})
        return []
    good = []
    for raw in raw_claims:
        why = problem(raw)
        if why:
            log.append({"chapter": chapter, "issue": "invalid_claim", "error": why, "raw": raw})
        else:
            good.append(raw)
    return good


# ---------------------------------------------------------------- quotes and claims
def locate(quote, sent_id, window):
    """(paragraph, sent_id, start, end) of the quote: the given sentence first, then any sentence
    of the window, then across sentence boundaries within a paragraph."""
    preferred = [(p, s) for p, s in window if s["sent_id"] == sent_id]
    for p, s in preferred + window:
        span = find_span(s["text"], quote)
        if span:
            return p["paragraph"], s["sent_id"], s["start"] + span[0], s["start"] + span[1]
    ranges = {}
    for p, s in window:
        _, lo, hi = ranges.get(p["paragraph"], (p, s["start"], s["end"]))
        ranges[p["paragraph"]] = (p, min(lo, s["start"]), max(hi, s["end"]))
    for p, lo, hi in ranges.values():
        span = find_span(p["text"][lo:hi], quote)
        if span:
            start, end = lo + span[0], lo + span[1]
            s = next(s for q, s in reversed(window) if q["paragraph"] == p["paragraph"] and s["start"] <= start)
            return p["paragraph"], s["sent_id"], start, end
    return None


def collect(drafts, window, chapter, log, seen):
    """One claim per indication, with the exact source span; duplicates dropped."""
    texts = {p["paragraph"]: p["text"] for p, _ in window}
    found = []
    for d in drafts:
        loc = locate(d["quote"], d["sent_id"], window)
        if loc is None:
            log.append({"chapter": chapter, "issue": "quote_not_found", "quote": d["quote"]})
            continue
        paragraph, sent_id, start, end = loc
        if sent_id != d["sent_id"]:
            log.append({"chapter": chapter, "issue": "sent_id_corrected", "from": d["sent_id"], "to": sent_id})
        quote = texts[paragraph][start:end]
        claims = [{**{k: d[k] for k in OUT_FIELDS if k not in ("sent_id", "quote", "indication_raw")},
                   "sent_id": sent_id, "quote": quote, "indication_raw": norm(i)}
                  for i in d["indications"] if norm(i)]
        if not claims:
            log.append({"chapter": chapter, "issue": "no_indication", "quote": d["quote"]})
        for c in claims:
            c = {k: c[k] for k in OUT_FIELDS}
            key = json.dumps([loc, c], ensure_ascii=False)
            if key in seen:
                log.append({"chapter": chapter, "issue": "duplicate_dropped", "quote": c["quote"],
                            "indication": c["indication_raw"]})
                continue
            seen.add(key)
            found.append((c, loc))
    return found


def extract_chapter(ch, by_ch, gold):
    log, seen, found = [], set(), []
    for window, messages in build_prompts(ch, by_ch, gold):
        try:
            content = call_llm(messages)
        except RuntimeError as e:
            log.append({"chapter": ch["chapter"], "issue": "llm_error", "error": str(e)})
            continue
        found += collect(parse(content, ch["chapter"], log), window, ch["chapter"], log, seen)
    run = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    counters, claims = Counter(), []
    for c, (paragraph, _, start, end) in sorted(found, key=lambda x: (x[1][0], x[1][2])):
        t = "r" if c["claim_type"] == "remedy" else "h"
        counters[t] += 1
        claims.append({**c, "claim_id": f"pliny-{ch['book']}.{ch['chapter']}-{t}{counters[t]:02d}",
                       "passage_id": ch["passage_id"], "book": ch["book"], "chapter": ch["chapter"],
                       "paragraph": paragraph, "char_start": start, "char_end": end,
                       "provenance": {"model": CFG["llm"]["model"], "prompt_version": CFG["llm"]["prompt_version"],
                                      "run_date": run, "reviewed_by": None}})
    log.append({"chapter": ch["chapter"], "issue": "chapter_done", "claims": len(claims),
                "remedies_extracted": counters["r"], "remedies_stated": ch.get("stated_remedies"),
                "llm_errors": sum(e["issue"] == "llm_error" for e in log)})
    return claims, log


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chapters", nargs="+", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    if not a.all and not a.chapters:
        sys.exit("give --chapters N ... or --all")
    paths = CFG["paths"]
    by_ch = {c["chapter"]: c for c in load_jsonl(paths["chapters"])}
    if not by_ch:
        sys.exit(f"No chapters in {paths['chapters']}; run src/ingest_perseus.py first")
    wanted = sorted(by_ch) if a.all else [n for n in a.chapters if n in by_ch]
    done = set() if a.redo or a.dry_run else {
        e["chapter"] for e in load_jsonl(paths["log"])
        if e["issue"] == "chapter_done" and e.get("llm_errors", 0) == 0}
    todo = [n for n in wanted if n not in done]
    if not todo:
        print("all requested chapters are already done (use --redo to extract them again)")
        return
    gold = load_jsonl(paths["gold"])
    check_examples(by_ch, gold)
    if a.dry_run:
        for n in todo:
            for _, messages in build_prompts(by_ch[n], by_ch, gold):
                print("\n\n".join(f"--- {m['role']} ---\n{m['content']}" for m in messages))
        return
    claims = [c for c in load_jsonl(paths["claims_out"]) if c["chapter"] not in todo]
    write_jsonl(paths["claims_out"], claims)
    write_jsonl(paths["log"], [e for e in load_jsonl(paths["log"]) if e["chapter"] not in todo])
    print(f"model {CFG['llm']['model']}, prompt {CFG['llm']['prompt_version']} -> {paths['claims_out']}")
    t0, total = time.time(), 0
    for n in todo:
        claims, log = extract_chapter(by_ch[n], by_ch, gold)
        write_jsonl(paths["claims_out"], claims, mode="a")
        write_jsonl(paths["log"], log, mode="a")
        total += len(claims)
        done_e = log[-1]
        dropped = sum(e["issue"] == "quote_not_found" for e in log)
        stated = done_e["remedies_stated"] if done_e["remedies_stated"] is not None else "?"
        print(f"chapter {n:3d}: {len(claims):3d} claims ({done_e['remedies_extracted']}/{stated} "
              f"remedies vs heading), {dropped} dropped, {time.time() - t0:.0f}s elapsed")
    print(f"done: {total} new claims")


if __name__ == "__main__":
    main()
