# Graph schema — nodes, edges, and semantics

The canonical graph model lives in `kb/graph.py`. This document describes every node type and edge kind, what it means legally, and how it is extracted.

## Node types

| Type | Count | ID scheme | Source |
|------|-------|-----------|--------|
| `Article` | 113 | `article-5` | consolidated text (CELEX `02024R1689-20260727`) |
| `Paragraph` | 662 | `article-5.1` | heading `## 1` in article markdown |
| `Point` | 340 | `article-5.1.a` | heading `### (a)` |
| `Sub-point` | 247 | `article-5.1.a.i` | heading `#### (i)` |
| `Recital` | 180 | `recital-42` | original OJ (CELEX `32024R1689`) |
| `Annex` | 15 | `annex-iii` | consolidated text |
| `Definition` | 67 | `def-ai-system` | Article 3 `'term' means ...` |
| `Actor` | 5 | `actor-provider` | the five regulated roles |
| `Obligation` | 785 | `obligation-article-16-3` | sentences containing "shall" |
| `RiskTier` | 2 | `risk-high` | prohibited / high-risk classification |

## Edge kinds & semantics

### `INTERPRETS` — the interpretive link

**What it is:** a `Recital → Article` edge meaning *"this recital explains, contextualises, or bounds the interpretation of this article."*

**Why it matters:** EU regulations have two layers of authority:
- **Articles** are **binding law** — they state what the rules *are*.
- **Recitals** are the **reasons and interpretive guidance** — courts (and compliance agents) read them to understand *how* articles should be applied. Recital 19, for example, defines what counts as a "publicly accessible space", which directly bounds the Art 5(1)(f)–(h) biometric prohibitions.

**How extracted:** regex over the recital text for explicit article citations (`Article 6(2)`, `Article 5(1)(a)`). Base weight 1.5 (persuasive, not binding).

**Known limitation:** recitals rarely cite articles by number — they interpret by *using defined terms*. That is why `USES_DEFINITION` edges from recitals matter more (see below). After adding those, only 12 of 180 recitals remain isolated (genuinely self-contained ones like recital 1's purpose statement).

### `USES_DEFINITION` — the grounding link

**What it is:** a `clause/recital → Definition` edge meaning *"this text uses a term whose legal meaning is fixed by Article 3."*

**Why it matters:** this is the **grounding layer for IDE agents**. A PRD saying "the vendor must…" resolves via `def-provider → actor-provider → IMPOSES_ON obligations`. Without it, "vendor" is just a word; with it, it's a legally-defined role with attached obligations.

**How extracted:** word-boundary phrase match of any of the 67 defined terms (quoted `'AI system'` or unquoted) in clause/recital text. Base weight 2.0.

### `REFERENCES` — the direct citation

**What it is:** a `unit → Article/Annex` edge meaning *"this text explicitly cites that unit."* The strongest signal — the drafter intended a legal dependency.

**Granularity:** first-class at **clause level** — `article-101.1.a.b → article-91` (a sub-clause citing another article, across articles). Also aggregated at unit level for rollup.

**How extracted:** regex for `Article N(letter)(para)` and `Annex [IVX]+` in unit/clause text. Base weight 3.0 (highest).

### `IMPOSES_ON` — the binding link

**What it is:** an `Obligation → Actor` edge meaning *"this obligation legally binds this role."*

**How extracted:** sentences containing "shall" in articles; the actor is inferred from which defined role appears in the sentence (provider/deployer/importer/distributor/manufacturer). Base weight 2.5.

### Structural edges

| Edge | Meaning | Base weight |
|------|---------|-------------|
| `HAS_SUBUNIT` | containment: article → paragraph → point → sub-point | 1.0 |
| `HAS_OBLIGATION` | article contains an obligation node | 1.5 |
| `DEFINES` | Article 3 defines a term | 2.0 |
| `IS_ROLE_OF` | definition maps to an actor | 2.0 |
| `CLASSIFIES_AS` | unit classifies as a risk tier | 1.5 |

## Edge strength/weight scheme

**Principle:** weight = how strongly the edge implies semantic dependency.

$$weight = base + (multiplicity - 1)$$

- Base weights live in `EDGE_BASE_WEIGHTS` in `kb/graph.py` (hand-tuned heuristics, trivially adjustable).
- Repeated citations accumulate: Annex XIV cites Annex I in 24 places → one deduplicated edge, weight 24.0.
- Edges are **deduplicated** — repeated identical links collapse to one weighted edge.
- **Direct references only** (design decision): no transitive/inferred edges. Multi-hop questions are answered by traversal, not pre-computed edges.

## Example traversals

**Obligation resolution** (IDE agent flags a PRD mentioning CV screening):
```
annex-iii.4.a (CV-sorting software)
  ← CLASSIFIES_AS ← article-6.2 (high-risk)
  → HAS_SUBUNIT chain → article-8..15 (requirements)
  → article-16.1 → IMPOSES_ON → actor-provider
```

**Definition grounding** (PRD says "deployer must monitor"):
```
"deployer" → def-deployer → actor-deployer
  ← IMPOSES_ON ← obligation-article-26-*
```

**Interpretive context** (why does Art 5(1)(f) ban emotion recognition?):
```
article-5.1.f ← INTERPRETS ← recital-44 (workplace/education emotion recognition)
article-5.1.f ← USES_DEFINITION ← def-publicly-accessible-space ← recital-19
```

## Extraction status & ceilings

- All extraction is **deterministic regex** over the markdown corpus — no LLM in the loop (keeps the benchmark honest).
- Ceiling: 12 isolated recitals remain; some interpretive links are paraphrased ("the notion of … should be interpreted in light of") rather than cited. LLM-assisted linking is a phase-3 option.
- Obligation→actor inference is keyword-based; negations and passive voice can misattribute. Phase-3 option: LLM re-extraction with validation.
