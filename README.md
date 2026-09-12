# Compliance Agents — Data Layer

Hackathon project for [AITinkerers "Agents Everywhere"](https://aitinkerers.org/hackathons/global/agents-everywhere).

**Goal:** agents that flag compliance issues *as you code and write PRDs*, embedded where work happens — IDE (VS Code, OpenCode, etc.), browser (Google Docs), and office documents (docx, xlsx).

**This repo (phase 1)** builds the data foundation: legislation as structured markdown, a knowledge-base layer for LLM access, and a benchmark to pick the best KB.

## Roadmap

| Step | Deliverable | Status |
|------|-------------|--------|
| 1 | EU AI Act (incl. recitals + Omnibus) as structured markdown, with an auto-update script | 🚧 branch `ml_eu-ai-act-markdown` |
| 2 | LLM access layer — Neo4j vs NetworkX vs LLMwiki vs hybrid RAG | ⬜ |
| 3 | Benchmark to select the knowledge base | ⬜ |
| 4 | Expand to GDPR, HK PDPO, and other legislation | ⬜ |
| 5 | Cross-legislation interaction + visualisation | ⬜ |

See [`docs/plan.md`](docs/plan.md) for the full plan, data schema, and graph design.

## Repo layout (planned)

```
data/
  eu-ai-act/
    articles/          # one file per article, frontmatter metadata
    recitals/          # one file per recital (or chunked ranges)
    annexes/           # annex I..XIII
    amendments/        # omnibus + amending regulations, with diffs
    guidance/          # Commission guidelines (prohibited practices, AI system definition, ...)
    INDEX.md           # machine-readable manifest of the corpus
kb/                   # phase 2: knowledge-base layer
  graph.py            # canonical graph model (nodes + edges from the corpus)
  networkx_kb.py      # in-process backend (zero infra)
  llmwiki_kb.py       # wiki-style markdown backend (agents navigate/grep)
  neo4j_kb.py         # Neo4j loader + Cypher queries (docker compose up -d neo4j)
  query.py            # uniform CLI: uv run python -m kb.query --backend networkx --stats
scripts/
  update_sources.py   # scheduled scraper: EUR-Lex consolidated text -> markdown, diff -> PR
  visualize.py        # graph visualisations -> viz/
benchmarks/
  questions/           # gold Q&A sets (single-hop, multi-hop, temporal, cross-legislation)
  run_benchmark.py
viz/                  # generated visuals (PNG charts + interactive HTML)
```

## Visualisations

`uv run python scripts/visualize.py` generates into `viz/`:

| File | Shows |
|------|-------|
| `node-types.png` | Node counts by type |
| `edge-types.png` | Edge counts by kind |
| `obligations-by-actor.png` | Compliance burden per actor |
| `article-graph.png` | Article ↔ Annex reference network |
| `definitions-network.png` | Article 3 definitions → actors |
| `graph-interactive.html` | Full graph (pyvis, colour by type) |
| `article-graph.html` | Article-level subgraph (interactive) |

See [`docs/visualisation.md`](docs/visualisation.md) for the options comparison.

## Licence / attribution

EU legislation is reusable under [Commission Decision 2011/833/EU](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32011D0833) — attribution to the Publications Office of the EU (EUR-Lex) is required and included in every generated file's frontmatter.
