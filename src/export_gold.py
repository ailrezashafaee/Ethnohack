"""Convert the annotation workbook (Claims sheet) into gold/gold.jsonl.

Usage:
    python src/export_gold.py --xlsx gold_set_ch83_ch20_ch13.xlsx

Chapters listed as test_chapters in config/config.json get split "test", all others "dev".
"""
import argparse, json
from pathlib import Path
from openpyxl import load_workbook

FIELDS = ["claim_id", "chapter", "claim_type", "sent_id", "quote", "plant_name_raw",
          "plant_part", "preparation", "route", "indication_raw", "attribution",
          "attributed_to", "stance", "notes", "annotator"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--book", type=int, default=20)
    ap.add_argument("--out", default="gold/gold.jsonl")
    a = ap.parse_args()
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config/config.json").read_text())
    test = set(cfg["test_chapters"])
    ws = load_workbook(a.xlsx, data_only=True)["Claims"]
    header = [c.value for c in ws[1]]
    rows = []
    for vals in ws.iter_rows(min_row=2, values_only=True):
        r = dict(zip(header, vals))
        if not r.get("quote") or "EXAMPLE" in str(r.get("notes") or ""):
            continue
        rec = {k: (str(r[k]).strip() if r.get(k) not in (None, "") else None) for k in FIELDS}
        rec["book"], rec["chapter"], rec["split"] = a.book, int(rec["chapter"]), None
        rec["split"] = "test" if rec["chapter"] in test else "dev"
        rec["route_inferred"] = "route inferred" in (rec["notes"] or "").lower()
        rows.append(rec)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    old = [json.loads(l) for l in out.open()] if out.exists() else []
    chapters = {r["chapter"] for r in rows}
    keep = [r for r in old if r["chapter"] not in chapters]   # re-export replaces those chapters
    with out.open("w", encoding="utf-8") as f:
        for r in keep + rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for ch in sorted(chapters):
        n = sum(r["chapter"] == ch for r in rows)
        print(f"chapter {ch}: {n} gold claims ({'test' if ch in test else 'dev'})")
    print(f"-> {out}")
