// Copy data/06_graph/*.csv into Neo4j's import folder, then run this script.
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
