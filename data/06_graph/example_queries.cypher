// Example queries for the "Was Pliny right?" knowledge graph.
// Load the graph first with load_neo4j.cypher.

// 1. RQ1: how do Pliny's remedies hold up? (claims per verdict)
MATCH (c:Claim)
RETURN c.verdict AS verdict, count(*) AS claims
ORDER BY claims DESC;

// 2. Supported remedies and the papers behind them
MATCH (p:Plant)-[e:PLINY_REMEDY {verdict: 'supported'}]->(d:Condition)
MATCH (x:Paper)-[:TESTS]->(p), (x)-[:TESTS]->(d)
RETURN p.name AS pliny_name, p.scientific AS plant, d.label AS condition, x.title AS paper, x.year AS year
ORDER BY plant;

// 3. RQ2: does the source of a claim matter? (verdicts per kind of source)
MATCH (c:Claim)-[:STATED_BY]->(s:Source)
RETURN s.kind AS source_kind, c.verdict AS verdict, count(*) AS claims
ORDER BY source_kind, claims DESC;

// 4. RQ3: untested leads, reported by more than one source
MATCH (c:Claim {verdict: 'untested'})-[:ABOUT]->(p:Plant), (c)-[:FOR]->(d:Condition), (c)-[:STATED_BY]->(s:Source)
WHERE p.status IN ['footnote', 'footnote+llm', 'manual'] AND p.level = 'species'
WITH p, d, collect(DISTINCT s.id) AS sources, count(c) AS claims
WHERE size(sources) > 1
RETURN p.scientific AS plant, d.label AS condition, sources, claims
ORDER BY claims DESC;

// 5. Everything Pliny says about one plant, with his own words
MATCH (c:Claim)-[:ABOUT]->(p:Plant {name: 'garlic'}), (c)-[:FOR]->(d:Condition), (c)-[:STATED_BY]->(s:Source)
RETURN d.label AS condition, c.verdict AS verdict, c.quote AS pliny_wrote, s.id AS source, c.passage AS passage
ORDER BY verdict, condition;

// 6. Conditions Pliny treated with the most different plants
MATCH (p:Plant)-[:PLINY_REMEDY]->(d:Condition)
RETURN d.label AS condition, count(p) AS plants
ORDER BY plants DESC LIMIT 15;

// 7. Visual: one plant's neighbourhood (use the graph view in Neo4j Browser)
MATCH path = (p:Plant {name: 'rue'})-[:PLINY_REMEDY]->(d:Condition)
RETURN path;
