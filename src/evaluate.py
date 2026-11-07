"""Compare extracted claims with the gold set.

Usage:
    python src/evaluate.py --split dev          # dev chapters (prompt development)
    python src/evaluate.py --split test         # held-out chapters (final numbers only!)

Matching: a predicted claim matches a gold claim in the same chapter with the same
claim_type when the indications are similar (difflib ratio >= threshold) and the
sentences are the same or adjacent. Each gold claim matches at most one prediction.
Reports claim-level precision/recall/F1, then field accuracy on matched pairs.
"""
import argparse, json
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/config.json").read_text())
FIELDS = ["plant_part", "route", "attribution", "attributed_to", "stance"]
FUZZY = ["preparation"]


def load(path):
    p = ROOT / path
    return [json.loads(l) for l in p.open(encoding="utf-8")] if p.exists() else []


def sim(a, b):
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    return SequenceMatcher(None, a, b).ratio() if a and b else float(a == b)


def sent_close(a, b):
    try:
        (pa, sa), (pb, sb) = [tuple(map(int, x.split("."))) for x in (a, b)]
        return pa == pb and abs(sa - sb) <= 1
    except (ValueError, AttributeError):
        return False


def match(gold, pred, threshold):
    pairs, used = [], set()
    cands = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(pred):
            if g["chapter"] == p["chapter"] and g["claim_type"] == p["claim_type"] \
                    and sent_close(g["sent_id"], p["sent_id"]):
                s = sim(g["indication_raw"], p["indication_raw"])
                if s >= threshold:
                    cands.append((s, gi, pi))
    gdone = set()
    for s, gi, pi in sorted(cands, reverse=True):     # greedy best-first one-to-one matching
        if gi not in gdone and pi not in used:
            pairs.append((gold[gi], pred[pi])); gdone.add(gi); used.add(pi)
    return pairs


def prf(tp, n_gold, n_pred):
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--show-errors", action="store_true")
    ap.add_argument("--pred", help="claims file to score (default: claims_out in config)")
    a = ap.parse_args()
    gold = [g for g in load(CFG["paths"]["gold"]) if g.get("split") == a.split]
    chs = sorted({g["chapter"] for g in gold})
    excluded = [c for c in chs if c in CFG["few_shot_chapters"]] if a.split == "dev" else []
    chs = [c for c in chs if c not in excluded]      # few-shot chapters would be cheating
    gold = [g for g in gold if g["chapter"] in chs]
    pred = [p for p in load(a.pred or CFG["paths"]["claims_out"]) if p["chapter"] in chs]
    if not gold:
        print(f"No gold claims for split '{a.split}'"
              + (f" (few-shot chapters {excluded} are excluded)" if excluded else "")); return
    if not pred:
        print(f"No extracted claims yet for chapters {chs}; run src/extract.py --chapters {' '.join(map(str, chs))}"); return
    pairs = match(gold, pred, a.threshold)
    print(f"Split: {a.split} | chapters {chs} | gold {len(gold)} | predicted {len(pred)} | matched {len(pairs)}")
    for t in ("remedy", "harm", None):
        g = [x for x in gold if t is None or x["claim_type"] == t]
        p = [x for x in pred if t is None or x["claim_type"] == t]
        tp = sum(1 for x, _ in pairs if t is None or x["claim_type"] == t)
        P, R, F = prf(tp, len(g), len(p))
        print(f"  {t or 'all':7s} precision {P:.2f}  recall {R:.2f}  F1 {F:.2f}  (tp {tp}, gold {len(g)}, pred {len(p)})")
    print("Field accuracy on matched claims:")
    for f in FIELDS + FUZZY:
        if f in FUZZY:
            ok = sum(sim(g.get(f), p.get(f)) >= 0.6 for g, p in pairs)
        else:
            ok = sum((g.get(f) or "").lower() == (p.get(f) or "").lower() for g, p in pairs)
        print(f"  {f:14s} {ok / len(pairs):.2f}  ({ok}/{len(pairs)})" if pairs else f"  {f}: -")
    if a.show_errors:
        mg = {id(g) for g, _ in pairs}; mp = {id(p) for _, p in pairs}
        print("\nMissed (in gold, not extracted):")
        for g in gold:
            if id(g) not in mg: print(f"  ch{g['chapter']} {g['sent_id']} {g['claim_type']}: {g['indication_raw']}")
        print("Extra (extracted, not in gold):")
        for p in pred:
            if id(p) not in mp: print(f"  ch{p['chapter']} {p['sent_id']} {p['claim_type']}: {p['indication_raw']}")
        print("Field disagreements:")
        for g, p in pairs:
            for f in FIELDS:
                if (g.get(f) or "").lower() != (p.get(f) or "").lower():
                    print(f"  ch{g['chapter']} {g['sent_id']} {g['indication_raw']!r}: {f} gold={g.get(f)} pred={p.get(f)}")


if __name__ == "__main__":
    main()
