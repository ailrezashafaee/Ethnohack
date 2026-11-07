"""Stage 6: knowledge graph of Pliny's remedies and the modern evidence.

Usage (from the pliny/ folder, after stage 5):
    python src/build_graph.py

Graph model
  (:Plant)      Pliny's plant, with its modern scientific name (WFO)
  (:Condition)  the modern condition or effect (MeSH)
  (:Claim)      one remedy or harm claim, with Pliny's exact words and its place in the text
  (:Source)     who the claim is attributed to: Pliny, a named authority, or hearsay
  (:Paper)      a modern paper that really tests the plant for the condition (Europe PMC)

  (Claim)-[:ABOUT]->(Plant)            (Claim)-[:FOR]->(Condition)
  (Claim)-[:STATED_BY]->(Source)       (Plant)-[:PLINY_REMEDY {claims, verdict}]->(Condition)
  (Paper)-[:TESTS {study_type, result}]->(Plant), (Paper)-[:TESTS]->(Condition)

Outputs in data/06_graph/:
  nodes_*.csv, rels_*.csv, load_neo4j.cypher   import into Neo4j (copy the CSVs to its import folder)
  graph.json                                   the same graph as JSON
  explorer.html                                open in any browser: no server, no installation
"""
import csv, json, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/06_graph"


def read_jsonl(path):
    with open(ROOT / path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_csv(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def condition_id(c):
    return c.get("condition_mesh_id") or "term:" + (c.get("condition_search_term") or c["condition_term"])


def source_name(c):
    if c.get("attribution") == "named" and c.get("attributed_to"):
        return c["attributed_to"]
    return {"pliny": "Pliny", "hearsay": "hearsay", "magi": "the Magi"}.get(c.get("attribution"), "Pliny")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    claims = [c for c in read_jsonl("data/05_evidence/claims_with_evidence.jsonl")
              if c.get("evidence_pair") and c.get("verdict") not in (None, "not_checked", "error")]
    pairs = {p["pair_id"]: p for p in read_jsonl("data/05_evidence/pairs.jsonl")}
    plants_info = {p["plant_id"]: p for p in read_jsonl("data/03_plants/plants.jsonl")}

    # papers that count: the stage 5 relevance rule (LLM says relevant + title/abstract names both)
    from check_evidence import really_relevant
    counted = {pid: [x for x in p.get("papers", []) if really_relevant(x, p)] for pid, p in pairs.items()}

    plants, conditions, sources, papers = {}, {}, {}, {}
    remedy = defaultdict(lambda: {"claims": [], "verdict": None, "pair": None})
    for c in claims:
        info = plants_info.get(c["plant_id"], {})
        plants[c["plant_id"]] = {"id": c["plant_id"], "name": info.get("name", c["plant_name_raw"]),
                                 "scientific": c.get("plant_accepted_name"), "wfo_id": c.get("plant_wfo_id"),
                                 "status": c.get("plant_status"), "level": c.get("plant_level")}
        cid = condition_id(c)
        conditions[cid] = {"id": cid, "label": c.get("condition_mesh_label") or c.get("condition_search_term"),
                           "mesh_id": c.get("condition_mesh_id"), "category": c.get("condition_category")}
        src = source_name(c)
        sources[src] = {"id": src, "kind": c.get("attribution")}
        r = remedy[(c["plant_id"], cid)]
        r["claims"].append(c)
        r["verdict"], r["pair"] = c["verdict"], c["evidence_pair"]
        for x in counted.get(c["evidence_pair"], []):
            papers[x["id"]] = {"id": x["id"], "title": x["title"], "year": x.get("year")}

    # ---------- Neo4j CSV + Cypher
    write_csv("nodes_plants.csv", ["id", "name", "scientific", "wfo_id", "status", "level"],
              [[p[k] for k in ("id", "name", "scientific", "wfo_id", "status", "level")] for p in plants.values()])
    write_csv("nodes_conditions.csv", ["id", "label", "mesh_id", "category"],
              [[c[k] for k in ("id", "label", "mesh_id", "category")] for c in conditions.values()])
    write_csv("nodes_sources.csv", ["id", "kind"], [[s["id"], s["kind"]] for s in sources.values()])
    write_csv("nodes_claims.csv", ["id", "type", "pliny_term", "quote", "passage", "sentence", "verdict"],
              [[c["claim_id"], c["claim_type"], c["indication_raw"], c["quote"], c["passage_id"], c["sent_id"],
                c["verdict"]] for c in claims])
    write_csv("nodes_papers.csv", ["id", "title", "year"], [[p["id"], p["title"], p["year"]] for p in papers.values()])
    write_csv("rels_claim_about_plant.csv", ["claim", "plant"], [[c["claim_id"], c["plant_id"]] for c in claims])
    write_csv("rels_claim_for_condition.csv", ["claim", "condition"], [[c["claim_id"], condition_id(c)] for c in claims])
    write_csv("rels_claim_stated_by.csv", ["claim", "source"], [[c["claim_id"], source_name(c)] for c in claims])
    write_csv("rels_pliny_remedy.csv", ["plant", "condition", "claims", "verdict"],
              [[pl, co, len(r["claims"]), r["verdict"]] for (pl, co), r in remedy.items()])
    tests = []
    for (pl, co), r in remedy.items():
        for x in counted.get(r["pair"], []):
            tests.append([x["id"], pl, co, x.get("study_type"), x.get("result")])
    write_csv("rels_paper_tests.csv", ["paper", "plant", "condition", "study_type", "result"], tests)
    (OUT / "load_neo4j.cypher").write_text(CYPHER, encoding="utf-8")

    # ---------- JSON + explorer
    graph = {
        "plants": sorted(plants.values(), key=lambda p: p["name"]),
        "conditions": list(conditions.values()),
        "remedies": [{
            "plant": pl, "condition": co, "verdict": r["verdict"],
            "claims": [{"type": c["claim_type"], "term": c["indication_raw"], "quote": c["quote"],
                        "chapter": c["chapter"], "sentence": c["sent_id"], "source": source_name(c),
                        "preparation": c.get("preparation")} for c in r["claims"]],
            "papers": [{"id": x["id"], "title": x["title"], "year": x.get("year"),
                        "study_type": x.get("study_type"), "result": x.get("result")}
                       for x in counted.get(r["pair"], [])],
        } for (pl, co), r in remedy.items()],
    }
    (OUT / "graph.json").write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    page = (Path(__file__).with_name("explorer_template.html")).read_text(encoding="utf-8")
    data = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    (OUT / "explorer.html").write_text(page.replace("__GRAPH_DATA__", data), encoding="utf-8")
    print(f"{len(plants)} plants, {len(conditions)} conditions, {len(claims)} claims, "
          f"{len(sources)} sources, {len(papers)} papers, {len(remedy)} plant-condition remedies")
    print(f"outputs in {OUT}  (open explorer.html in a browser)")


CYPHER = """// Copy data/06_graph/*.csv into Neo4j's import folder, then run this script.
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Plant) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Condition) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Claim) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Source) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Paper) REQUIRE n.id IS UNIQUE;

LOAD CSV WITH HEADERS FROM 'file:///nodes_plants.csv' AS r
MERGE (n:Plant {id: r.id}) SET n.name = r.name, n.scientific = r.scientific, n.wfo_id = r.wfo_id,
  n.status = r.status, n.level = r.level;
LOAD CSV WITH HEADERS FROM 'file:///nodes_conditions.csv' AS r
MERGE (n:Condition {id: r.id}) SET n.label = r.label, n.mesh_id = r.mesh_id, n.category = r.category;
LOAD CSV WITH HEADERS FROM 'file:///nodes_sources.csv' AS r
MERGE (n:Source {id: r.id}) SET n.kind = r.kind;
LOAD CSV WITH HEADERS FROM 'file:///nodes_claims.csv' AS r
MERGE (n:Claim {id: r.id}) SET n.type = r.type, n.pliny_term = r.pliny_term, n.quote = r.quote,
  n.passage = r.passage, n.sentence = r.sentence, n.verdict = r.verdict;
LOAD CSV WITH HEADERS FROM 'file:///nodes_papers.csv' AS r
MERGE (n:Paper {id: r.id}) SET n.title = r.title, n.year = r.year;

LOAD CSV WITH HEADERS FROM 'file:///rels_claim_about_plant.csv' AS r
MATCH (c:Claim {id: r.claim}), (p:Plant {id: r.plant}) MERGE (c)-[:ABOUT]->(p);
LOAD CSV WITH HEADERS FROM 'file:///rels_claim_for_condition.csv' AS r
MATCH (c:Claim {id: r.claim}), (d:Condition {id: r.condition}) MERGE (c)-[:FOR]->(d);
LOAD CSV WITH HEADERS FROM 'file:///rels_claim_stated_by.csv' AS r
MATCH (c:Claim {id: r.claim}), (s:Source {id: r.source}) MERGE (c)-[:STATED_BY]->(s);
LOAD CSV WITH HEADERS FROM 'file:///rels_pliny_remedy.csv' AS r
MATCH (p:Plant {id: r.plant}), (d:Condition {id: r.condition})
MERGE (p)-[e:PLINY_REMEDY]->(d) SET e.claims = toInteger(r.claims), e.verdict = r.verdict;
LOAD CSV WITH HEADERS FROM 'file:///rels_paper_tests.csv' AS r
MATCH (x:Paper {id: r.paper}), (p:Plant {id: r.plant}), (d:Condition {id: r.condition})
MERGE (x)-[t1:TESTS]->(p) SET t1.study_type = r.study_type, t1.result = r.result
MERGE (x)-[t2:TESTS]->(d) SET t2.study_type = r.study_type, t2.result = r.result;

// Example: Pliny's supported remedies and the papers behind them
// MATCH (p:Plant)-[e:PLINY_REMEDY {verdict:'supported'}]->(d:Condition)<-[:TESTS]-(x:Paper)-[:TESTS]->(p)
// RETURN p.name, p.scientific, d.label, x.title;
"""

if __name__ == "__main__":
    main()
