"""Stage 1: ingest Pliny's Natural History (Bostock & Riley, Perseus TEI P4).

Usage:
    python src/ingest_perseus.py --xml phi0978.phi001.perseus-eng1.xml --books 20

Outputs (in data/01_text/):
    chapters.jsonl  one record per chapter: passage_id, book, chapter, title,
                    stated_remedies, printed_page, paragraphs -> sentences
    notes.jsonl     one record per footnote: note_id, passage_id, paragraph,
                    char_offset (in the paragraph text), text, duplicate
    manifest.json   provenance and counts
"""
import argparse, copy, hashlib, html, json, re
from datetime import date
from pathlib import Path
from lxml import etree

URN = "urn:cts:latinLit:phi0978.phi001.perseus-eng1"
MARK = re.compile(r"\ue000(\d+)\ue001")          # temporary footnote marker
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
           "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
           "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
           "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


def load_tei(path):
    """Parse the TEI P4 file: drop the DOCTYPE and turn named entities into Unicode."""
    raw = Path(path).read_text(encoding="utf-8")
    raw = re.sub(r"<!DOCTYPE.*?\]>", "", raw, flags=re.S)

    def entity(m):
        name = m.group(1)
        if name in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        out = html.unescape(f"&{name};")
        return out if out != f"&{name};" else f"[{name}]"

    raw = re.sub(r"&([A-Za-z][A-Za-z0-9]*);", entity, raw)
    return etree.fromstring(raw.encode("utf-8")), hashlib.sha256(Path(path).read_bytes()).hexdigest()


def split_sentences(text):
    """Simple rule-based splitter; identical to the one used for the gold-set workbook."""
    return [s for s in re.split(r"(?<=[.;!?])\s+(?=[A-Z\"'(])", text) if s.strip()]


def stated_remedies(title):
    total = 0
    for m in re.finditer(r"([A-Z][A-Z\- ]+?)\s+REMED", title):
        n = 0
        for w in re.split(r"[-\s]+", m.group(1).lower()):
            n += NUMBERS.get(w, 0)
        total += n
    return total or None


def ingest(xml_path, books, out_dir):
    root, sha = load_tei(xml_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    chapters, notes = [], []
    for book in books:
        bdiv = root.xpath(f"//div1[@type='book'][@n='{book}']")[0]
        page = None
        start_page = {}
        for el in bdiv.iter():                     # printed page where each chapter starts
            if el.tag == "pb":
                page = el.get("n")
            elif el.tag == "div2":
                start_page[el.get("n")] = page
        for cdiv in bdiv.xpath("./div2[@type='chapter']"):
            ch = cdiv.get("n")
            pid = f"{URN}:{book}.{ch}"
            c = copy.deepcopy(cdiv)
            note_texts = []
            for el in c.xpath(".//note|.//pb"):    # replace notes by markers, drop page breaks
                token = ""
                if el.tag == "note":
                    note_texts.append(ws("".join(el.itertext())))
                    token = f"\ue000{len(note_texts)}\ue001"
                parent, prev = el.getparent(), el.getprevious()
                tail = token + (el.tail or "")
                if prev is not None:
                    prev.tail = (prev.tail or "") + tail
                else:
                    parent.text = (parent.text or "") + tail
                parent.remove(el)
            head = c.xpath("./head")
            title = ws(MARK.sub("", "".join(head[0].itertext()))) if head else f"CHAP. {ch}."
            paragraphs = []
            for pi, p in enumerate(c.xpath(".//p"), 1):
                with_marks = ws("".join(p.itertext()))
                text = ws(MARK.sub("", with_marks))
                sents, offset = [], 0
                for si, s in enumerate(split_sentences(text), 1):
                    start = text.find(s, offset)
                    offset = start + len(s)
                    sents.append({"sent_id": f"{pi}.{si}", "start": start, "end": offset, "text": s})
                paragraphs.append({"paragraph": pi, "text": text, "sentences": sents})
                for m in MARK.finditer(with_marks):  # footnote position = end of preceding context
                    ctx = ws(MARK.sub("", with_marks[:m.start()]))[-40:]
                    pos = text.find(ctx) + len(ctx) if ctx else 0
                    n = int(m.group(1))
                    notes.append({"note_id": f"{pid}#n{n}", "passage_id": pid, "paragraph": pi,
                                  "char_offset": pos, "anchor_context": ctx[-25:],
                                  "text": note_texts[n - 1]})
            pg = start_page.get(ch)
            chapters.append({"passage_id": pid, "book": int(book), "chapter": int(ch),
                             "title": title, "stated_remedies": stated_remedies(title),
                             "printed_page": int(pg[1:]) if pg else None,
                             "paragraphs": paragraphs})
    seen = {}
    for n in notes:                                  # flag repeated note texts within a chapter
        key = (n["passage_id"], n["text"])
        n["duplicate"] = key in seen
        seen.setdefault(key, n["note_id"])
    write_jsonl(out_dir / "chapters.jsonl", chapters)
    write_jsonl(out_dir / "notes.jsonl", notes)
    manifest = {"source": "Pliny the Elder, Natural History, tr. J. Bostock & H. T. Riley (1855)",
                "urn": URN, "file": Path(xml_path).name, "sha256": sha,
                "licence": "CC BY-SA 3.0 US", "attribution": "Perseus Digital Library, Tufts University",
                "retrieved": date.today().isoformat(), "books": books,
                "counts": {"chapters": len(chapters), "notes": len(notes),
                           "duplicate_notes": sum(n["duplicate"] for n in notes),
                           "sentences": sum(len(p["sentences"]) for c in chapters for p in c["paragraphs"]),
                           "stated_remedies": sum(c["stated_remedies"] or 0 for c in chapters)}}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--books", nargs="+", default=["20"])
    ap.add_argument("--out", default="data/01_text")
    a = ap.parse_args()
    print(json.dumps(ingest(a.xml, a.books, Path(a.out))["counts"], indent=2))
