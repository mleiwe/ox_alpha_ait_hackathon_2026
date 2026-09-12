# Plan — Compliance Agents Data Layer

## Phase 1: EU AI Act → structured markdown (this branch)

### Objectives
1. Full text of Regulation (EU) 2024/1689 (EU AI Act) as markdown, split into addressable units:
   - **Articles** (1–113) — one file per article, with chapter/section grouping.
   - **Recitals** (1–180) — one file per recital (or small ranges); recitals carry interpretive weight for compliance flagging.
   - **Annexes** (I–XIII) — one file per annex.
2. **Stay current** — the Act is being amended:
   - **AI Omnibus** (Reg (EU) 2026/1744, OJ 24 Jul 2026, in force 27 Jul 2026): delays Annex III high-risk obligations to **2 Dec 2027**, Annex I to **2 Aug 2028**; adds Art 5(1)(ba)/(bb) + 5(1a)/(1b) prohibitions (non-consensual intimate imagery / CSAM), applicable **2 Dec 2026**.
   - Commission **guidelines** (prohibited practices Feb 2025, AI system definition Feb 2025, Art 6(5) draft May 2026, transparency obligations Jul 2026) — non-binding but essential for practical compliance flagging.
   - Delegated/implementing acts, codes of practice (GPAI CoP), and future amendments.
3. **Regular update script** — scheduled (GitHub Actions cron, e.g. weekly) that:
   - Fetches the **consolidated** text from EUR-Lex via ELI: `https://eur-lex.europa.eu/eli/reg/2024/1689/oj` (HTML; also `.../eng` for language variants).
   - Converts to markdown, splits into articles/recitals/annexes, writes frontmatter metadata.
   - Diffs against the committed corpus; if changed → opens a PR (`chore: eur-lex update YYYY-MM-DD`) with the diff summary.
   - Records source URL, retrieval date, and CELEX ID in `data/eu-ai-act/INDEX.md`.

### Data schema (frontmatter per file)

```yaml
---
id: article-5            # or recital-42, annex-iii
type: article            # article | recital | annex | guidance | amendment
celex: 32024R1689
eli: http://data.europa.eu/eli/reg/2024/1689/oj
title: "Prohibited AI practices"
chapter: 2
section: null
amended_by: ["32026R1744"]   # CELEX of amending acts, if any
in_force_from: 2025-02-02    # per-article application date (Art 113)
source_url: https://eur-lex.europa.eu/eli/reg/2024/1689/oj
retrieved: 2026-09-12
attribution: "© European Union, http://eur-lex.europa.eu"
---
```

### Why markdown (not raw HTML/PDF)
- Diffable in git → update PRs are reviewable.
- Directly consumable by IDE agents (Copilot instructions, custom agents) and by KB loaders.
- Stable IDs (`article-5`, `recital-42`) become graph node keys in phase 2.

### Merge back to main
Once the corpus + update script land and one scheduled run succeeds, merge `ml_eu-ai-act-markdown` → `main`.

---

## Phase 2: LLM access layer (candidates)

| Candidate | Strengths | Risks |
|-----------|-----------|-------|
| **Neo4j** | Native graph queries (Cypher), cross-article references, visualisation, MCP server exists | Ops overhead, needs service |
| **NetworkX** | Pure Python, in-process, zero infra, easy benchmarking | No persistence, no query language, memory-bound |
| **LLMwiki / wiki-style markdown** | Agents read files directly (grep/navigate), zero infra, IDE-native | No joins, retrieval is naive |
| **Hybrid: markdown + embeddings + graph index** | Best of both; graph for traversal, vector for semantic recall | More moving parts |

Graph schema sketch (phase 2):
- Nodes: `Article`, `Recital`, `Annex`, `Definition` (Art 3 terms), `Obligation`, `Actor` (provider/deployer/importer), `RiskTier`, `Guideline`, `Amendment`.
- Edges: `DEFINES`, `REFERENCES` (e.g. Art 6 → Annex III), `IMPOSES_ON`, `AMENDED_BY`, `INTERPRETED_BY`, `APPLIES_FROM`.

---

## Phase 3: Benchmark

Gold question set across categories:
1. **Single-hop** — "What does Article 5 prohibit?"
2. **Multi-hop** — "Which obligations apply to a CV-screening tool, and when?" (Art 6(2) → Annex III → Art 113(c) → Omnibus delay)
3. **Temporal** — "What is the deadline for watermarking pre-existing generative-AI systems?" (Art 111(4) → 2 Dec 2026)
4. **Cross-legislation** (phase 4) — "Does this HK PDPO clause conflict with GDPR Art 22?"

Metrics: answer accuracy (LLM-judge + exact-match on dates/IDs), retrieval precision/recall, latency, cost, staleness detection (does the KB know about the Omnibus delay?).

---

## Phase 4/5 (post-team-check-in)

- GDPR (CELEX 32016R0679), HK PDPO (Cap. 486), EU DSA/DMA, China CAC measures, US state laws.
- Cross-KB edges: shared concepts (personal data, automated decision-making, transparency), conflicts, extraterritorial reach.
- Visualisation: shared-concept heatmaps, conflict graphs, jurisdiction overlap.

---

## Open questions for the team
1. Do IDE agents need offline capability (markdown/NetworkX wins) or is a hosted Neo4j acceptable?
2. Should recitals be first-class graph nodes or flattened into article context?
3. Benchmark judge: LLM-as-judge vs human legal review for the gold set?
