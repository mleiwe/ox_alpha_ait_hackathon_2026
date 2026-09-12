# Plan — Phase 3: Benchmark

## Objectives
1. Pick the retrieval strategy that ships (NetworkX vs LLMwiki vs Neo4j vs hybrid) with evidence.
2. Prove staleness handling and regulatory coverage — does the KB reflect Reg 2026/1744 (Omnibus
   delays, new Art 5 prohibitions), risk-tier obligations, and GPAI rules (Arts 53–55, fine-tuning)?
3. Produce metrics that feed the judging criteria (Technical Execution) and the phase 4/5 check-in.

## Judging-criteria mapping

| Criterion (`judging_criteria.md`) | Benchmark component |
|---|---|
| Core Requirements & Functionality | compliance-flagging eval (mode 3) — the core workflow end to end |
| Innovation & Theme Alignment | agentic LLMwiki navigation eval (strategy 5) — the IDE-native pattern |
| Technical Execution & Integration | retrieval-only + QA modes, per-backend comparison, `REPORT.md` |
| Usefulness & Agentic Experience | scenario category + flagging precision/recall |

## Retrieval strategies

Strategies sit *on top of* the `KBBackend` ABC — they are not new backends. The ladder:

| # | Strategy | Uses | Infra | Expected edge |
|---|----------|------|-------|---------------|
| 0 | Substring keyword (current `NetworkXKB.search`) | content/title match | none | baseline floor |
| 1 | Lexical ranked (BM25) over node content | `search` + rank | pure Python (`rank_bm25`) | big win over #0 on legal terminology |
| 2 | Dense embeddings (flat RAG) — embed node content, cosine | `search` variant | embedding model | wins on paraphrase ("CV-screening" → "recruitment") |
| 3 | Structured graph queries — `obligations_for`, `path`, typed-edge filters | ABC directly | none | trivially wins structured questions |
| 4 | Hybrid GraphRAG — BM25/dense seeds → expand 1–2 hops via `REFERENCES`/`IMPOSES_ON`/`USES_DEFINITION` → re-rank by edge weight | `search` + `references` | none beyond #1/#2 | wins multi-hop chains |
| 5 | Agentic LLMwiki navigation — grep INDEX → open page → follow `[[wiki-links]]` | generated wiki | none | the real IDE-agent pattern; eval by simulating the loop |

Graph-native variants worth naming: **recital context expansion** (article hit → pull `INTERPRETS`
recitals into context) and **granularity** (article-level vs clause-level retrieval).

### Edge-weight & directionality variants

The KB layer already types edges (9 kinds, base weights `REFERENCES` 3.0 > `IMPOSES_ON` 2.5 >
`USES_DEFINITION`/`DEFINES`/`IS_ROLE_OF` 2.0 > `INTERPRETS`/`CLASSIFIES_AS`/`HAS_OBLIGATION` 1.5 >
`HAS_SUBUNIT` 1.0, multiplicity boost, dedup) and stores them on a `DiGraph` — direction exists
structurally. The benchmark must test whether that structure *earns its keep*:

1. **Directionality of expansion** (named variant): out-only vs in-only vs both — asymmetric by
   node type. For a Definition hit, incoming `USES_DEFINITION` edges are the useful direction
   (who relies on this term); for an Article hit, outgoing `REFERENCES` matter. Uniform
   bidirectional expansion drowns article hits in `HAS_SUBUNIT` noise.
2. **Weight-aware re-ranking** (named variant): weighted vs unweighted expansion; specify how
   weights combine along a path (sum vs max vs hop-decay).
3. **Kind-filtered expansion** (named variant): expand via `REFERENCES`/`IMPOSES_ON`/
   `USES_DEFINITION` only; exclude structural `HAS_SUBUNIT`.
4. **Meta-evaluation of the weight scheme**: does weight-aware re-ranking actually beat
   unweighted? If not, the scheme is decorative. This validates PR #2's design decisions with
   evidence. Chain recall is inherently directional (expected chains have direction), so the eval
   exercises directionality for free.

### RAG vs GraphRAG framing
- Both are **strategies over the same corpus**, not new backends. RAG = flat retrieval over node
  content, edges ignored; GraphRAG = retrieval that traverses typed edges. The graph is *curated
  legal structure*, not auto-extracted entities — a genuine advantage over generic GraphRAG.
- Chunking is mostly solved: nodes are pre-chunked by legal hierarchy. The only granularity knob
  is article-vs-clause retrieval — a named variant, not a tuned parameter.
- **Tautology trap**: "which obligations apply to X" is `obligations_for` in disguise — graph
  backends win those *by construction*, which is not evidence. Gold questions are tagged
  **structured** (graph-query-expressible; comparison is ops cost) vs **natural-language entry**
  (fuzzy seed; the genuine competition is #1 vs #2 vs #4).
- **Staleness is a corpus property, not a retrieval property.** No strategy answers an Omnibus
  question if Reg 2026/1744 isn't in the corpus — the staleness category measures the *corpus +
  update pipeline* (phase 1's job), run once per corpus version, not per strategy.

### Hypotheses
- **H1:** BM25 > substring everywhere (cheap win).
- **H2:** Dense > BM25 on paraphrase-heavy multi-hop; tie or lose on exact legal terminology.
- **H3:** Hybrid GraphRAG wins **chain recall** on multi-hop — flat RAG retrieves the seed
  (Art 6(2)) but drops the chain (→ Annex III → Art 113 → Omnibus delay). Report *chain recall*
  alongside endpoint recall@k.
- **H4:** Agentic navigation is competitive single-hop, degrades with hop count, but is the only
  zero-infra IDE-native option.

### No hyper-parameter tuning in phase 3
- ~60 questions is too small to tune against the set we report on — that is fitting the test set.
- The benchmark's job is strategy selection; defaults are defensible, overfit numbers are not.
- Fix for **fairness**, not tuning: same `k` across strategies (report curves over k ∈ {3, 5, 10},
  never pick k from results), same context token budget for QA, one embedding model, BM25 library
  defaults.
- Expansion depth (1-hop vs 2-hop) and granularity (article vs clause) are **named strategy
  variants**, not tuned parameters.
- If any knob is touched at all: hold out a split (40 dev / 10 test). Real tuning belongs to
  post-selection production hardening, on dev questions only.

## Gold set
- Format: one YAML/JSONL file per category, machine-checkable expected answers.
- Every question carries `expected_units` (node IDs) + `expected_answer` (exact-match where possible).
- Categories & sizing (~60 questions total):
  - **single-hop** (~15) — "What does Article 5 prohibit?" → `article-5`
  - **multi-hop** (~15) — "Which obligations apply to a CV-screening tool, and when?"
    → `article-6.2` → `annex-iii` → `article-113` → Omnibus delay
  - **temporal** (~10) — "Deadline for watermarking pre-existing generative-AI systems?"
    → `article-111.4` → 2026-12-02
  - **staleness** (~10) — questions whose correct answer *requires* Reg 2026/1744 knowledge
    (delays to 2 Dec 2027 / 2 Aug 2028; Art 5(1)(ba)/(bb) prohibitions from 2 Dec 2026)
  - **scenario** (~10) — phrased as they'd arrive in IDE/PRD context (the product surface):
    - "I'm adding CV screening to our hiring tool — what obligations apply and when?"
      → `article-6.2` → `annex-iii` → `article-113` + Omnibus delay
    - "Does my support chatbot need to disclose it's AI?" → `article-50`
    - "Can we deploy emotion recognition in the workplace?" → `article-5.1.f`
    - "What must I do before releasing my GPAI model?" → `article-53`/`article-55`
    - PRD-snippet variants: paste a PRD paragraph → "what compliance flags?"
  - **tier-requirements** (~10) — obligations of particular AI system tiers and GPAI rules:
    - "What are the transparency duties for a limited-risk chatbot?" → `article-50`
    - "What documentation must a high-risk system provider keep?" → `article-11`/`article-18`
    - "What are the fine-tuning limits for GPAI models?" → `article-53`/`article-55`
    - "When does a GPAI model become systemic-risk?" → `article-55` (10^25 FLOPs threshold)
- Every question is tagged **structured** vs **natural-language entry** (see Retrieval strategies).

## Runner
- `bench/run.py --backend networkx|llmwiki|neo4j --gold bench/gold/`
- Codes against the `KBBackend` ABC only (`kb/__init__.py`) — never concrete backends.
- BM25 is token-based: light preprocessing needed for citation forms ("Art 6(2)" vs
  "Article 6 paragraph 2") — normalise "Art" → "article", strip parenthetical numbering.
- Two evaluation levels, reported separately:
  1. **Retrieval-only**: precision@k, recall@k, MRR on `expected_units` — isolates backend
     differences from LLM noise.
  2. **End-to-end QA**: retrieval + LLM answer — exact-match for dates/IDs, LLM-judge for free text.
  3. **Compliance-flagging**: feed PRD snippets / feature descriptions, measure precision/recall
     on the flags the agent raises — the product surface itself, and what the judging criteria
     actually score.

## Metrics
| Metric | Level | Notes |
|--------|-------|-------|
| precision/recall@k, MRR | retrieval | primary backend discriminator; report curves over k ∈ {3, 5, 10} |
| chain recall | retrieval | multi-hop only: full chain retrieved, not just the seed (tests H3) |
| exact-match accuracy | QA | dates, CELEX IDs, article IDs |
| LLM-judge score | QA | free-text answers only |
| flag precision/recall | flagging | mode 3: compliance flags raised on PRD snippets |
| latency, cost | both | per backend |
| staleness pass rate | QA | the Omnibus probe |

## Statistical methodology

This is a **paired, deterministic benchmark**, not A/B testing: every strategy runs on the same
questions, retrieval at fixed config is deterministic, and there is no user noise. Variance comes
from gold-set sampling and the LLM-judge — not from system noise.

- **Paired tests, not two-proportion tests**: McNemar's exact test for accuracy-type metrics;
  paired bootstrap CIs for MRR/recall@k.
- **Per-category breakdown** (single-hop / multi-hop / temporal / scenario / tier-requirements) —
  effects concentrate there; pooling hides them.
- **Pre-registered decision rule** (declared before running): a strategy ships if it wins ≥2
  categories AND ΔMRR ≥ 0.05. Ties → decide on latency/cost/infra. Practical significance over
  chasing p-values; the decision is reversible (ABC interface), so directional evidence suffices.
- **Power reality check**: at n≈60, McNemar only sees discordant pairs (~12–18) — detectable gaps
  are ~15–18pp. Smaller differences are invisible; that is acceptable because large effects decide
  the selection anyway. Do not invest in a formal power analysis for phase 3.
- **Paraphrase augmentation (optional)**: LLM-paraphrase each gold question (same expected units)
  → ~150 items cheaply. Paraphrases are not independent → **cluster bootstrap by source question**.
- **Judge reliability (QA level)**: temperature 0, 3 repeat runs reported as mean ± CI, and a
  judge-agreement check (κ vs human labels on a ~10-question subset) — the validation that
  actually matters for the LLM-judge.

## Generalisability

The plan targets more than the EU AI Act (phase 4/5: GDPR, HK PDPO, DSA/DMA, CAC measures).
Three layers transfer differently:

| Layer | Generalises? | Why |
|-------|-------------|-----|
| Infrastructure (runner, gold schema, metrics, `KBBackend` ABC) | ✅ fully | corpus-agnostic by construction |
| Methodology (paired stats, decision rules, no-tuning policy) | ✅ fully | properties of the evaluation design, not the corpus |
| Empirical findings (which strategy wins, by how much) | ⚠️ conditional | every ranking is conditioned on this corpus's statistics |

What is corpus-specific:
- **Graph schema is EU AI Act-shaped** (`Recital`, `Annex`, `RiskTier`; `IMPOSES_ON`,
  `CLASSIFIES_AS`). GDPR is structurally homologous — findings should transfer. HK PDPO, US state
  laws, CAC measures have different anatomy; parser + schema need per-corpus adaptation first.
- **Corpus statistics drive retrieval dynamics**: the AI Act is large (2,420 nodes) and densely
  cross-referential (6,267 edges) — the environment where graph expansion shines. Sparse statutes
  flatten the BM25-vs-dense-vs-hybrid differences. Rankings may hold; margins won't.
- **Reference-extraction regexes are tuned to EU citation style** ("Article 6(2)"). US ("§ 1798.120")
  or translated Chinese measures break them — broken edge extraction silently degrades GraphRAG,
  masquerading as "graph doesn't help" in phase 4/5.
- **Gold set is AI Act-specific** — only the schema carries forward, not the questions.

Buying generalisability cheaply:
1. **Corpus fingerprint in every `REPORT.md`**: node count, edge density, avg node length,
   reference density, vocabulary size → later correlate "which strategy wins" with corpus
   properties (converts one-off findings into generalisable knowledge).
2. **Label conclusions as conditional**: "hybrid GraphRAG wins multi-hop *on a densely
   cross-referenced EU regulation*" — not "graph expansion wins multi-hop".
3. **Replication ladder**: GDPR first (same-family replication), then one non-EU statute
   (different-family — the real limit test). Two replications beat any amount of AI Act tuning.
4. **Version the schema** in reports — otherwise a finding change is indistinguishable from a
   schema change.

One-line framing: *the benchmark is a reusable harness; findings are corpus-conditional until
replicated on GDPR (same family) and one non-EU statute (different family).*

## Deliverables
- `bench/gold/*.yaml`, `bench/run.py`, `bench/REPORT.md` (per-backend comparison, incl. corpus
  fingerprint and schema version)
- Branch: `ml_benchmark` stacked on `ml_kb-layer`

## Open questions
- LLM-judge vs human legal review for the gold set (plan.md Q3) — proposal: human legal
  review to *author* the gold set, LLM-judge to *score* free-text at run time.