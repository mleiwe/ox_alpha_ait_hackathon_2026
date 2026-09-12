# Phase 2 — Knowledge-Base Layer (planning)

> Branch: `ml_kb-layer` (off `ml_eu-ai-act-markdown`, PR #1). Retarget to `main` after PR #1 merges.

## Status: implemented ✅

- Canonical graph: 113 Articles, 662 Paragraphs, 340 Points, 247 Sub-points, 180 Recitals, 15 Annexes, 67 Definitions, 5 Actors, 789 Obligations — 3,209 edges.
- Backends: NetworkX ✅, LLMwiki ✅ (2,420 wiki pages), Neo4j loader ✅ (docker-compose provided).
- Tests: 13/13 passing (`tests/test_kb.py`).
- CLI: `uv run python -m kb.query --backend networkx --path article-6 annex-iii`

## Node hierarchy (final)

The corpus markdown encodes the legal hierarchy as headings; the graph builder
parses them into addressable sub-unit nodes:

| Level | Heading | Node ID | Example |
|-------|---------|---------|---------|
| Article | `# Article 6 — Title` | `article-6` | Article 6 |
| Paragraph | `## 1` | `article-6.1` | Art 6(1) |
| Point | `### (a)` | `article-6.1.a` | Art 6(1)(a) |
| Sub-point | `#### (i)` | `article-6.1.a.i` | Art 6(1)(a)(i) |

Containment edges (`HAS_SUBUNIT`) let agents roll up from a point to its parent
article. Article 3 definitions (`‘term’ means ...`) become `Definition` nodes
with `DEFINES` edges; the five regulated roles map to `Actor` nodes.

## Goal

Make the EU AI Act corpus (`data/eu-ai-act/`) queryable by LLMs and IDE agents, and compare candidate knowledge bases so phase 3 can benchmark them on equal footing.

## Design principles

1. **One graph, many backends.** Parse the corpus into a single canonical graph model (nodes + edges), then serialize to each backend. No backend-specific logic in the parser.
2. **Zero-infra first.** NetworkX (in-process) and LLMwiki (plain markdown) must work with no services; Neo4j is optional via docker-compose.
3. **Agent-native.** Every backend must be reachable from an IDE agent: Python API (NetworkX), file navigation + grep (LLMwiki), Cypher/MCP (Neo4j).

## Canonical graph model

### Nodes

| Type | ID | Source | Attributes |
|------|----|--------|-----------|
| `Article` | `article-5` | `articles/*.md` frontmatter | title, chapter, celex, in_force_from |
| `Recital` | `recital-42` | `recitals/*.md` | celex |
| `Annex` | `annex-iii` | `annexes/*.md` | title, celex |
| `Definition` | `def-ai-system` | parsed from Art 3 | term, article ref |
| `Obligation` | `obligation-<article>-<n>` | parsed from normative text ("shall") | text, actor |
| `Actor` | `actor-provider` | Art 3 definitions | role |
| `RiskTier` | `risk-unacceptable` | Art 5 / Annex III / Annex I | level |
| `Guideline` | `guideline-<slug>` | `guidance/` (phase 1.5) | title, date |
| `Amendment` | `amendment-32026R1744` | `amendments/` | celex, in_force |

### Edges

| Edge | From → To | Example |
|------|-----------|---------|
| `REFERENCES` | Article → Article/Annex | Art 6(2) → Annex III |
| `IMPOSES_ON` | Obligation → Actor | Art 16 obligations → provider |
| `DEFINES` | Article → Definition | Art 3(1) → "AI system" |
| `CLASSIFIES_AS` | Article/Annex → RiskTier | Annex III → high-risk |
| `AMENDED_BY` | Article → Amendment | Art 5 → Reg 2026/1744 |
| `INTERPRETED_BY` | Article → Recital | Art 5 → recitals 26–55 |
| `APPLIES_FROM` | Article → date attr | Art 113(c) → 2027-12-02 |

### Extraction approach (v1, deterministic)

- **Definitions**: regex over Article 3 numbered paragraphs (`'term' means ...`).
- **Cross-references**: regex `Article \d+([a-z])?(\(\d+\))?` and `Annex [IVX]+` across all units → `REFERENCES` edges.
- **Obligations**: sentences containing "shall" in articles → `Obligation` nodes (actor inferred from nearest definition mention).
- **Recital links**: recital N ↔ articles it cites → `INTERPRETED_BY`.
- No LLM in the loop for v1 — deterministic extraction keeps the benchmark honest (phase 3 measures retrieval, not extraction quality). LLM-assisted extraction is a v2 option.

## Backends

| Backend | Module | Status | Infra |
|---------|--------|--------|-------|
| **NetworkX** | `kb/networkx_kb.py` | ✅ build | none (in-process) |
| **LLMwiki** | `kb/llmwiki_kb.py` | ✅ build | none (markdown files + INDEX) |
| **Neo4j** | `kb/neo4j_kb.py` | ✅ loader + docker-compose | docker |

### LLMwiki layout (generated)

```
kb/wiki/
  INDEX.md              # table of all nodes, links to pages
  pages/
    article-5.md        # content + "References: [[annex-iii]], [[article-6]]"
    recital-42.md
    ...
  edges.csv             # machine-readable edge list (for benchmark diffing)
```

Wiki-links (`[[article-5]]`) make the graph navigable by agents and humans; `edges.csv` keeps it machine-checkable.

## Query interface (uniform across backends)

```python
from kb import get_kb

kb = get_kb("networkx")          # or "llmwiki", "neo4j"
kb.get_unit("article-5")          # node + content
kb.references("article-5")        # outgoing REFERENCES
kb.obligations_for("actor-provider")   # obligations imposed on an actor
kb.path("article-6", "annex-iii") # traversal for multi-hop questions
kb.search("CV screening")         # keyword search (backend-dependent)
```

## Benchmark hooks (phase 3 preview)

Each backend must expose the same query surface so the benchmark can swap them:
- **single-hop**: `get_unit("article-5")` correctness
- **multi-hop**: `path("article-6", "annex-iii")` + obligation resolution
- **temporal**: `APPLIES_FROM` attributes (Omnibus-shifted dates)
- **staleness**: does the KB reflect the consolidated text (post-Omnibus)?

## Out of scope (v1)

- Embeddings/vector search (phase 3 candidate if keyword search underperforms)
- LLM-assisted extraction of obligations/actors
- Cross-legislation edges (phase 5)
