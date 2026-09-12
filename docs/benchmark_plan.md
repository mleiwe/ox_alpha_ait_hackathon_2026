# Plan — Phase 3: Benchmark (amended after review)

## Framing: agent first, benchmark second

The hackathon rubric scores the **agent** ("does the core workflow function end to end"), not the
benchmark. This phase therefore inverts the original ordering:

1. **Ship the agent demo first** — PRD snippet → compliance flags, live in the IDE. This *is*
   mode 3: it is a product, not a benchmark mode. One artifact, two jobs (demo + measurement).
2. **Time-box the benchmark to ≤1 day, 2 people** — a decision tool for one question:
   *which retrieval strategy powers the agent?* Not a research program.
3. **Produce a 2-minute `REPORT.md`** — the only page judges will read about the benchmark.

Pre-committed scope (written down so creep is visible to the team, not silent):

- Strategies **0 / 1 / 4** benchmarked; strategy 5 (agentic navigation) as a qualitative IDE demo;
  strategy 2 (dense) optional stretch via TF-IDF (zero-infra proxy, already a dev dependency).
- Backends: **networkx + llmwiki only**. Neo4j is excluded from the benchmark (needs a service,
  cannot ship inside an offline IDE agent) — visualisation demo only.
- **~30 linted gold questions.** Everything core runs offline via `uv run` with no API keys;
  the LLM-judge is strictly optional so the harness runs anywhere.

## Objectives
1. Pick the retrieval strategy that powers the agent (NetworkX vs LLMwiki) with measured,
   reproducible evidence.
2. Measure the agent's core workflow (PRD snippet → compliance flags) on ~10 hand-authored
   snippets.
3. Produce metrics + a scannable `REPORT.md` feeding Technical Execution and the phase 4/5
   check-in.

## Judging-criteria mapping

| Criterion (`judging_criteria.md`) | Benchmark component |
|---|---|
| Core Requirements & Functionality | the agent itself (PRD → flags), measured by flag precision/recall on ~10 snippets |
| Innovation & Theme Alignment | strategy-comparison narrative + one chart; `viz/article-graph.html` shows the graph live |
| Technical Execution & Integration | retrieval-only comparison, latency budget, one-command reproducibility, `REPORT.md` |
| Usefulness & Agentic Experience | scenario category (IDE/PRD phrasing) + unanswerable-question handling |

## Prerequisites (deliverables of this branch)

The benchmark inherits the graph, so three fixes ride in this branch:

1. **Parser fix (verified bug).** `build_graph` computes `parent_id` *before* the stack pop, so
   same-level headings chain linearly: the emotion-recognition clause lives at
   `article-5.1.a.b.ba.bb.c.i.ii.d.e.f`, not `article-5.1.f`. All Point/SubPoint IDs and
   `HAS_SUBUNIT` traversal are affected. Fix: pop before computing parent.
2. **ABC additions.** The current `KBBackend` cannot express strategy 4: no incoming edges, no
   kind-filtered expansion, no `USES_DEFINITION`/`IMPOSES_ON` access by unit (`obligations_for`
   is actor-keyed only). Add `edges(unit_id, direction, kinds) -> list[Edge]`; LLMwiki's
   `edges.csv` gains a `weight` column; `stats()` keys unified across backends.
3. **Gold lint.** `bench/lint_gold.py`: every `expected_units` entry must exist as a node and
   every expected chain must be realizable via `path()`/expansion. The benchmark does not run on
   a red lint.

Corpus hygiene while here: exclude the stray
`union-legislative-acts-on-large-scale-it-systems…` annex (duplicates Annex X content, pollutes
search); file the Art 51(2) superscript corruption (`10^25` lost in HTML→markdown conversion) as
phase 1 debt. Add `rank_bm25` to `pyproject.toml`.

## Retrieval strategies

Strategies sit *on top of* the `KBBackend` ABC — not new backends. Chunking is solved (nodes are
pre-chunked by legal hierarchy). Benchmarked matrix:

| # | Strategy | Backend | Infra | Role |
|---|----------|---------|-------|------|
| 0 | Substring keyword (current `search`) | networkx + llmwiki | none | baseline floor |
| 1 | Lexical ranked (BM25, `rank_bm25`) over node content | networkx + llmwiki | pure Python | expected ship candidate |
| 2 | TF-IDF ranked retrieval (zero-infra dense proxy) | networkx | scikit-learn (dev dep) | optional stretch |
| 4 | Hybrid GraphRAG — BM25 seeds → 1–2 hop typed-edge expansion (kind-filtered, out-directed) → re-rank | networkx | none beyond #1 | expected multi-hop winner |
| 5 | Agentic LLMwiki navigation — grep INDEX → open page → follow `[[wiki-links]]` | llmwiki | none | qualitative IDE demo, not benchmarked |

**One named variant, pre-registered:** does kind-filtered, out-directed expansion beat uniform
bidirectional expansion on chain recall? This is the only variant with a plausible mechanism and
directly answers whether PR #2's typed/directed structure earns its keep. The 12-variant grid
(out/in/both × weighted/unweighted × kind-filtered) and the weight-scheme meta-evaluation are cut
to post-hackathon (the current weighted/unweighted binary conflates kind weights with the
multiplicity boost, making null results unattributable).

### Hypotheses
- **H1:** BM25 > substring everywhere (cheap win).
- **H3:** Hybrid GraphRAG wins chain recall on multi-hop — flat retrieval gets the seed
  (Art 6(2)) but drops the chain (→ Annex III → Art 113 → Omnibus delay).
- **H4:** Agentic navigation is competitive single-hop, degrades with hop count — covered
  qualitatively by the live IDE demo.

### No hyper-parameter tuning
~30 questions cannot support tuning against the set we report on — that is fitting the test set.
Same `k` across strategies (report curves over k ∈ {3, 5, 10}, never pick k from results), same
context token budget, BM25 library defaults. Expansion depth and granularity are named variants,
not tuned parameters.

## Gold set (~30 questions, linted)

Format: JSONL (no YAML dependency), one file per category. Every question carries
`expected_units` (node IDs) + `expected_answer` (exact-match where possible) + a
**structured** vs **natural-language** tag. The tautology trap ("which obligations apply to X" is
`obligations_for` in disguise) is handled by the tag + uncited paraphrases below.

| Category | n | Notes |
|---|---|---|
| single-hop | ~8 | **half uncited paraphrases** ("Is social scoring banned?") so strategies 1/2/4 compete — explicit-citation items are query-parsing tests that structured lookup wins by construction |
| multi-hop | ~8 | e.g. CV-screening tool → `article-6.2` → `annex-iii` → `article-113` → Omnibus delay (verified directed path) |
| temporal | ~6 | merged with staleness: find the date in Art 113/111 (e.g. watermarking pre-existing systems → `article-111.4` → 2026-12-02). Staleness as a strategy-discriminating category is cut — the corpus is consolidated text with amendments merged inline (`amendments/` and `guidance/` dirs do not exist), so every strategy scores identically; staleness becomes a one-time corpus smoke test |
| scenario | ~6 | IDE/PRD phrasing — the usefulness proxy. Emotion recognition in the workplace → `article-5.1.f` (post-parser-fix; currently `article-5.1.a.b.ba.bb.c.i.ii.d.e.f`); support-chatbot disclosure → `article-50`; GPAI release duties → `article-53`/`article-55` |
| unanswerable | ~4 | no-hit questions so the agent's "I don't know" path is measured, not just the happy path (judges reward failure handling) |

Broken examples replaced (verified against the corpus):
- ~~"Fine-tuning limits for GPAI models" → `article-53`/`article-55`~~ — no such limits exist in
  the corpus ("fine-tun" appears only in recitals 97/104/109/111 and Annex XI). Replaced with
  Art 53 technical-documentation / downstream-provider duties.
- ~~"10^25 FLOPs threshold → `article-55`"~~ — the threshold is in `article-51.2`, and the
  superscript is corrupted in the corpus text. Exact-match on the article ID, not the number.

## Runner

```
uv run bench/lint_gold.py                                  # gate: must pass first
uv run bench/run.py --backend networkx --strategy 0|1|2|4 --gold bench/gold/
uv run bench/run.py --backend llmwiki  --strategy 0|5      # 5 = demo trace
```

- Codes against the `KBBackend` ABC only (with the additions above) — never concrete backends.
- BM25 preprocessing: normalise "Art" → "article", strip parenthetical numbering.
- Three evaluation levels, reported separately:
  1. **Retrieval-only** — precision/recall@k, MRR on `expected_units`; isolates backend
     differences from LLM noise.
  2. **End-to-end QA** (optional, only if LLM budget allows) — retrieval + LLM answer;
     exact-match for dates/IDs.
  3. **Compliance-flagging = the agent.** Spec: flag = `{article_id, obligation_id?, rationale}`;
     gold = hand-authored flag sets; corpus = ~10 PRD snippets with **≥5 negatives** (snippets
     with no issues — without them precision is undefined); score = set-based precision/recall
     with partial credit for the right article at the wrong clause.

## Metrics

| Metric | Level | Notes |
|---|---|---|
| MRR@5, recall@5 | retrieval | primary discriminator; curves over k ∈ {3, 5, 10} |
| chain recall | retrieval | multi-hop only; defined: fraction of multi-hop items where all `expected_units` appear in the strategy's retrieved context under a fixed per-strategy context rule |
| flag precision/recall | agent | mode 3 as specified above |
| latency | both | **budget <1s/query** — an IDE agent answering in 10s fails usefulness regardless of MRR |
| unanswerable handling | both | no-hit questions answered with "I don't know", not hallucinated units |
| corpus fingerprint | report | node count, edge density, avg node length, reference density, vocab size, **parser version + known extraction gaps** (point-level refs like "5(1)(f)" are dropped by `ARTICLE_REF_RE`) |

## Decision rule (pre-registered, simple)

1. Rank strategies by overall MRR@5.
2. Top-2 pairwise: ships if it wins the **multi-hop** category (where H3 lives) AND ΔMRR ≥ 0.05.
   Ties → latency/infra.
3. Per-category breakdowns are **descriptive**; no inference at n≈10 per category (~30pp
   detectable gaps — that is noise, not signal).
4. The decision is reversible (ABC interface), so directional evidence suffices.

Full battery — McNemar's exact test, paired bootstrap CIs, judge-reliability κ, paraphrase
augmentation with cluster bootstrap, formal power analysis — moves to the post-hackathon appendix.

## Deliverables
- `bench/gold/*.jsonl`, `bench/lint_gold.py`, `bench/run.py`, `bench/REPORT.md` (per-strategy
  comparison + corpus fingerprint + schema version)
- ABC additions in `kb/` + parser fix + `rank_bm25` dependency
- **The agent (PRD → flags)** — the phase's primary artifact, demoed live
- Branch: `ml_benchmark` stacked on `ml_kb-layer` — keep the diff small so rebasing after #2
  merges is trivial; benchmark work must not block agent work

## Post-hackathon appendix (out of scope now)

- **Stats battery:** McNemar's exact test + paired bootstrap CIs for MRR/recall@k; judge
  reliability (temperature 0, repeats judge-side only, κ smoke check on ~10 items); optional LLM
  paraphrase augmentation with cluster bootstrap by source question.
- **Weight-scheme meta-evaluation:** proper ablation (unweighted / kind-only / multiplicity-only /
  both). Conclusion framed as "the specific base weights don't change rankings on this corpus" —
  a finding about the numbers, not a verdict on PR #2's design.
- **Generalisability:** infrastructure (runner, gold schema, metrics, ABC) and methodology
  (paired stats, no-tuning policy) transfer fully; empirical findings are corpus-conditional.
  Replication ladder: GDPR first (parser + citation-style transfer; schema needs `RiskTier`
  removal — GDPR has no risk tiers), then one non-EU statute. Corpus fingerprint in every report
  converts one-off findings into generalisable knowledge.
- **Neo4j comparison** if a hosted deployment ever becomes the product surface.

## Open questions
- Gold-set authoring: human legal review to *author*, LLM-judge (optional) to *score* free text
  at run time (plan.md Q3).