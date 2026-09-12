# Compliance Agents — EU AI Act review where you build

Hackathon project for [AITinkerers "Agents Everywhere"](https://aitinkerers.org/hackathons/global/agents-everywhere).

**The agent:** an EU AI Act compliance reviewer embedded in the developer's harness (OpenCode). It reviews AI product work at the moment it's written — including the coding agent's own output. When the agent writes to a product file or PRD, a plugin intercepts the write *before it lands* and runs a millisecond deterministic scan. A violation raises a toast flag to the **user** — rule, article citation, report path — and a block refuses the write, instructing the agent to stop iterating and offer the user the choice: **fix** the flagged lines, or record an explicit **override** (`compliance_override` records the user's decision in the ledger — a record, never a bypass). The human stays in the loop, the Art. 14 oversight pattern: e.g. automatic account suspension is restructured into a human review queue + human decision. Ambient KB-first reviews fire on file edits and session idle; a `compliance_review` tool gives on-demand verdicts; a CI workflow scans every PR; a global install brings the same gate to blank, unrelated workspaces.

**Verified live end to end** — see [`compliance/DEMO.md`](compliance/DEMO.md) for the block-and-self-correct loop with ledger evidence.

## How it works

```
developer / coding agent writes to src/** or a PRD
        │
        ▼
OpenCode plugin (.opencode/plugins/compliance-gate.ts)   ← intercepts BEFORE the write lands
        │  invokes
        ▼
compliance-check --fast        Tier 1: deterministic rules (ms) → clean / warn / BLOCK
        │ on warn/block
        ▼
compliance-check --llm         Tier 2: KB-first review against the knowledge graph
        │                      (relevant obligations per artifact + LLM adjudication)
        ▼
.compliance/ledger.jsonl       audit trail (the CLI is the only writer)
```

## The knowledge base

The agent's Tier-2 review is grounded in a structured knowledge graph of the EU AI Act (Reg (EU) 2024/1689 incl. recitals + the 2026 Omnibus amendment), parsed from 308 EUR-Lex files into an Article → Paragraph → Point hierarchy: **2,347 nodes / 6,135 edges**.

Retrieval strategy was selected by a pre-registered benchmark ([`bench/REPORT.md`](bench/REPORT.md)): **GraphRAG (BM25 seeds + typed-edge expansion on NetworkX)** — BM25 led raw MRR@5 (0.456 vs 0.418, within the Δ0.05 margin), but GraphRAG won the pre-registered composition tiebreak: multi-hop chain recall **0.60 vs 0.20** (3×) and reasoning-tier hop coverage 0.300 vs 0.233, at 9 ms mean latency (50× under a 1 s IDE budget). NetworkX ships as the backend (LLMwiki preserves rankings at −0.2 MRR).

## Repo layout

```
compliance/            # the agent middleware
  compliance-check     # the CLI — the only writer (ledger + reports)
  rules.json           # Tier-1 deterministic rules (pattern groups, severities, article citations)
  config.json          # KB path, stage globs, ledger/report paths, LLM adjudicator hook
  DEMO.md              # verified end-to-end flow + reproduce script
.opencode/
  plugins/compliance-gate.ts   # OpenCode adapter: gate, ambient toasts, compliance_review tool
kb/                    # knowledge-base layer
  graph.py             # canonical graph model (nodes + edges from the corpus)
  networkx_kb.py       # in-process backend (ships)
  llmwiki_kb.py        # wiki-style markdown backend (benchmarked)
  neo4j_kb.py          # Neo4j loader + Cypher (optional)
  query.py             # uniform CLI: uv run python -m kb.query --backend networkx --stats
bench/                 # benchmark: gold sets, lint gate, runner, plots
  REPORT.md            # results + pre-registered decision rule
  gold/                # 40 retrieval + 35 reasoning questions (linted)
data/eu-ai-act/        # legislation as structured markdown (articles/recitals/annexes/guidance)
scripts/
  update_sources.py    # EUR-Lex consolidated text → markdown, diff → PR
  visualize.py         # graph visualisations → viz/
src/                   # demo artifacts (fraud-demo.ts: compliant-by-construction example)
tests/                 # 20/20 passing
viz/                   # generated charts + interactive graph HTML
```

## Run it

```bash
# knowledge graph stats
uv run python -m kb.query --backend networkx --stats

# Tier-1 scan of a file (ms; exit 0 clean / 1 warn / 2 block)
compliance/compliance-check --fast --file src/fraud-demo.ts

# KB-first review with relevant obligations
compliance/compliance-check --llm --file src/fraud-demo.ts

# audit ledger
compliance/compliance-check --ledger --tail 5
```

The OpenCode plugin auto-loads when OpenCode starts in this repo (or globally via `~/.config/opencode/`) — see [`compliance/DEMO.md`](compliance/DEMO.md) for the full demo script, including the blank-workspace global install.

## Visualisations

`uv run python scripts/visualize.py` generates into `viz/`:

| File | Shows |
|------|-------|
| `graph-interactive.html` | Full graph (pyvis, colour by type) — 2,347 nodes |
| `article-graph.html` | Article-level subgraph (interactive) |
| `bench-mrr.png` / `bench-recall.png` / `bench-chain.png` / `bench-latency.png` | benchmark results |
| `node-types.png` / `edge-types.png` / `obligations-by-actor.png` | corpus composition |
| `definitions-network.png` | Article 3 definitions → actors |

## Roadmap

| Step | Deliverable | Status |
|------|-------------|--------|
| 1 | EU AI Act (incl. recitals + Omnibus) as structured markdown, with an auto-update script | ✅ |
| 2 | LLM access layer — NetworkX vs LLMwiki vs Neo4j vs hybrid RAG | ✅ (NetworkX ships) |
| 3 | Benchmark to select the knowledge base | ✅ ([`bench/REPORT.md`](bench/REPORT.md)) |
| 4 | Compliance agent in the harness (OpenCode gate, ambient review, CI) | ✅ |
| 5 | Expand to GDPR, HK PDPO, and other legislation | ⬜ |
| 6 | More surfaces: VS Code extension, browser (web text fields; Google Docs via API on save) | ⬜ |

## Licence / attribution

EU legislation is reusable under [Commission Decision 2011/833/EU](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32011D0833) — attribution to the Publications Office of the EU (EUR-Lex) is required and included in every generated file's frontmatter.
