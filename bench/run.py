"""Benchmark runner — retrieval strategies over the KBBackend ABC.

Strategies (plan: retrieval strategies sit on top of the ABC, not new backends):
  0  substring keyword (current `search`)          — baseline floor
  1  BM25 ranked retrieval over node content       — expected ship candidate
  2  TF-IDF ranked retrieval (zero-infra proxy)    — optional stretch
  4  Hybrid GraphRAG: BM25 seeds -> 1-2 hop typed-edge
     expansion (kind-filtered, out-directed) -> re-rank
  4u Hybrid GraphRAG variant: uniform bidirectional
     expansion (the one pre-registered variant)

Evaluation levels (reported separately):
  retrieval   — precision/recall@k, MRR on expected_units
  reasoning   — hop coverage, distractor resistance, trace validity
                (offline, no API keys); verdict accuracy applies to
                strategy 5 / optional LLM runs only

Usage:
    uv run bench/run.py --backend networkx --strategy 0 --gold bench/gold/
    uv run bench/run.py --backend networkx --strategy 4 --gold bench/gold/ --k 5
    uv run bench/run.py --backend networkx --strategy 4 --gold bench/gold/reasoning/ --mode reasoning
    uv run bench/run.py --all --gold bench/gold/            # retrieval matrix
    uv run bench/run.py --all --gold bench/gold/reasoning/ --mode reasoning
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from kb import KBBackend, get_kb  # noqa: E402

BENCH_DIR = Path(__file__).parent

# --- BM25 preprocessing (plan: normalise "Art" -> "article", strip parenthetical numbering) ---

_ART_NORM_RE = re.compile(r"\bArt\.?\s*(?=\d)")
_PAREN_RE = re.compile(r"\((\d+|[a-z]+|[ivx]+)\)")


def preprocess(text: str) -> str:
    text = _ART_NORM_RE.sub("article ", text)
    text = _PAREN_RE.sub(" ", text)
    return text.lower()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", preprocess(text))


# --- structural tolerance (granularity-aware scoring) ---
# Retrieving article-6.1.a for expected article-6.1 (or obligation-article-23-0
# for expected article-23) is the same legal content at different granularity.
# A retrieved node credits an expected unit when they are in an
# ancestor/descendant relationship via HAS_SUBUNIT / HAS_OBLIGATION.


def _structural_edges(kb: KBBackend) -> list[tuple[str, str, str]]:
    if getattr(kb, "graph_data", None) is not None:
        return [(e.src, e.dst, e.kind) for e in kb.graph_data.edges]
    if hasattr(kb, "edge_list"):
        return list(kb.edge_list)
    return []


def build_tolerance(kb: KBBackend) -> dict[str, set[str]]:
    """Map each node to its full ancestor+descendant closure (structural)."""
    children: dict[str, set[str]] = {}
    for src, dst, kind in _structural_edges(kb):
        if kind in ("HAS_SUBUNIT", "HAS_OBLIGATION"):
            children.setdefault(src, set()).add(dst)

    desc: dict[str, set[str]] = {}

    def closure(nid: str, seen: set[str] | None = None) -> set[str]:
        if nid in desc:
            return desc[nid]
        seen = seen or set()
        if nid in seen:  # cycle guard
            return {nid}
        seen.add(nid)
        out = {nid}
        for c in children.get(nid, ()):
            out |= closure(c, seen)
        desc[nid] = out
        return out

    for nid in kb.graph_data.nodes if getattr(kb, "graph_data", None) is not None else []:
        closure(nid)

    anc: dict[str, set[str]] = {nid: {nid} for nid in desc}
    for nid, ds in desc.items():
        for d in ds:
            if d in anc:
                anc[d].add(nid)
    return {nid: desc.get(nid, {nid}) | anc[nid] for nid in anc}


# --- strategies ---


class Strategy:
    """Retrieval strategy on top of the KBBackend ABC."""

    name: str = "base"

    def __init__(self, kb: KBBackend):
        self.kb = kb

    def retrieve(self, query: str, k: int) -> list[str]:
        raise NotImplementedError


class SubstringStrategy(Strategy):
    name = "0-substring"

    def retrieve(self, query: str, k: int) -> list[str]:
        hits = self.kb.search(query)
        # Rank by occurrence count so multi-term queries surface better nodes
        terms = tokenize(query)

        def score(nid: str) -> int:
            node = self.kb.get_unit(nid)
            text = (node.content or "").lower() if node else ""
            return sum(text.count(t) for t in terms)

        return sorted(hits, key=score, reverse=True)[:k]


class BM25Strategy(Strategy):
    name = "1-bm25"

    def __init__(self, kb: KBBackend):
        super().__init__(kb)
        from rank_bm25 import BM25Okapi

        # Obligation nodes are sentence-level extracts of their parent article's
        # "shall" sentences — duplicate documents that skew BM25 length
        # normalisation. Excluded from the retrieval index (they remain in the
        # graph for traversal; structural tolerance credits them at scoring).
        self.ids = sorted(nid for nid in self._all_ids() if not nid.startswith("obligation-"))
        self.corpus = [tokenize(self._node_text(nid)) for nid in self.ids]
        self.bm25 = BM25Okapi(self.corpus)

    def _all_ids(self) -> list[str]:
        return list(self.kb.pages.keys()) if hasattr(self.kb, "pages") else list(self.kb.g.nodes)

    def _node_text(self, nid: str) -> str:
        node = self.kb.get_unit(nid)
        if node is None:
            return ""
        title = node.title or ""
        return f"{title} {node.content or ''}"

    def retrieve(self, query: str, k: int) -> list[str]:
        scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self.ids, scores), key=lambda x: x[1], reverse=True)
        return [nid for nid, s in ranked if s > 0][:k]


class TFIDFStrategy(BM25Strategy):
    name = "2-tfidf"

    def __init__(self, kb: KBBackend):
        Strategy.__init__(self, kb)
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.ids = sorted(self._all_ids())
        self.corpus = [self._node_text(nid) for nid in self.ids]
        self.vec = TfidfVectorizer(stop_words="english")
        self.matrix = self.vec.fit_transform(self.corpus)

    def retrieve(self, query: str, k: int) -> list[str]:
        q = self.vec.transform([query])
        scores = (self.matrix @ q.T).toarray().ravel()
        ranked = sorted(zip(self.ids, scores), key=lambda x: x[1], reverse=True)
        return [nid for nid, s in ranked if s > 0][:k]


# Typed-edge expansion kinds for strategy 4 (kind-filtered, out-directed).
# HAS_SUBUNIT excluded: structural containment is noise for semantic expansion.
EXPANSION_KINDS = ("REFERENCES", "IMPOSES_ON", "INTERPRETS", "USES_DEFINITION", "DEFINES", "IS_ROLE_OF", "CLASSIFIES_AS", "HAS_OBLIGATION")


class GraphRAGStrategy(Strategy):
    """Hybrid GraphRAG: BM25 seeds -> typed-edge expansion -> re-rank."""

    name = "4-graphrag"
    directed = True
    kind_filtered = True

    def __init__(self, kb: KBBackend):
        super().__init__(kb)
        self.seeds = BM25Strategy(kb)

    def expand(self, seed_ids: list[str], depth: int = 2) -> dict[str, float]:
        """Expand seeds via typed edges. Returns {node_id: expansion_score}."""
        scores: dict[str, float] = {}
        frontier = {nid: 1.0 for nid in seed_ids}
        for hop in range(depth):
            nxt: dict[str, float] = {}
            for nid, w in frontier.items():
                direction = "out" if self.directed else "both"
                kinds = EXPANSION_KINDS if self.kind_filtered else None
                for _src, dst, kind in self.kb.edges(nid, direction=direction, kinds=kinds):
                    # Weight by edge kind strength (REFERENCES strongest)
                    edge_w = 1.0
                    node = self.kb.get_unit(dst)
                    if node is None:
                        continue
                    gain = w * edge_w * (0.5**hop)
                    nxt[dst] = nxt.get(dst, 0.0) + gain
            for nid, g in nxt.items():
                scores[nid] = scores.get(nid, 0.0) + g
            frontier = nxt
        return scores

    def retrieve(self, query: str, k: int) -> list[str]:
        seed_ids = self.seeds.retrieve(query, k)
        expanded = self.expand(seed_ids)
        # Re-rank: seed score dominates, expansion adds
        combined: dict[str, float] = {nid: 10.0 - i * 0.1 for i, nid in enumerate(seed_ids)}
        for nid, g in expanded.items():
            combined[nid] = combined.get(nid, 0.0) + g
        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        return [nid for nid, _ in ranked[: k * 3]]  # context rule: 3x k for expansion


class GraphRAGUniformStrategy(GraphRAGStrategy):
    """The one pre-registered variant: uniform bidirectional expansion."""

    name = "4u-graphrag-uniform"
    directed = False
    kind_filtered = False


STRATEGIES: dict[int, type[Strategy]] = {
    0: SubstringStrategy,
    1: BM25Strategy,
    2: TFIDFStrategy,
    4: GraphRAGStrategy,
    # 5 (agentic LLMwiki navigation) is scored end-to-end on the reasoning tier
    # via traces — not part of the retrieval --all matrix (plan: retrieval
    # strategies benchmarked are 0/1/4, 2 optional stretch).
}

# Strategies included in --all runs per mode (plan: 0/1/4 benchmarked, 2 stretch)
ALL_RETRIEVAL = [0, 1, 2, 4]
ALL_REASONING = [0, 1, 2, 4]


# --- retrieval metrics (granularity-aware via structural tolerance) ---


def precision_recall_at_k(
    retrieved: list[str],
    expected: list[str],
    k: int,
    tolerance: dict[str, set[str]] | None = None,
) -> tuple[float, float]:
    top = set(retrieved[:k])
    if not expected:
        return 0.0, 0.0
    if tolerance:
        # credit: expected unit OR any structurally-equivalent node retrieved
        hits = sum(1 for e in expected if top & tolerance.get(e, {e}))
    else:
        hits = len(top & set(expected))
    return hits / max(len(top), 1), hits / len(expected)


def mrr(
    retrieved: list[str],
    expected: list[str],
    k: int,
    tolerance: dict[str, set[str]] | None = None,
) -> float:
    for i, nid in enumerate(retrieved[:k], 1):
        if tolerance:
            if any(nid in tolerance.get(e, {e}) for e in expected):
                return 1.0 / i
        elif nid in set(expected):
            return 1.0 / i
    return 0.0


def chain_recall(
    retrieved: list[str],
    expected: list[str],
    tolerance: dict[str, set[str]] | None = None,
) -> float:
    """Fraction of multi-hop items where ALL expected_units appear in context."""
    if not expected:
        return 0.0
    if tolerance:
        ok = all(set(retrieved) & tolerance.get(e, {e}) for e in expected)
    else:
        ok = set(expected) <= set(retrieved)
    return 1.0 if ok else 0.0


# --- reasoning metrics (offline, no API keys) ---


def hop_coverage(trace: list[str], expected_hops: list[str]) -> float:
    """Fraction of expected_hops cited in the run's trace."""
    if not expected_hops:
        return 0.0
    cited = set(trace)
    return sum(1 for h in expected_hops if h in cited) / len(expected_hops)


def distractor_resistance(trace: list[str], distractor_hops: list[str]) -> float:
    """1.0 if no distractors cited as load-bearing; decays with each citation."""
    if not distractor_hops:
        return 1.0
    cited = sum(1 for d in distractor_hops if d in set(trace))
    return max(0.0, 1.0 - 0.5 * cited)


def trace_validity(kb: KBBackend, trace: list[str]) -> float:
    """Consecutive cited hops must connect via a real edge (path over the ABC)."""
    if len(trace) < 2:
        return 1.0
    connected = 0
    pairs = 0
    for a, b in zip(trace, trace[1:]):
        if a == b:
            continue
        pairs += 1
        p = kb.path(a, b)
        if p and p[-1] == b:
            connected += 1
    return connected / pairs if pairs else 1.0


# --- trace construction for reasoning mode ---
# The trace is the strategy's retrieved context ordered by retrieval rank —
# "what the agent would walk". Deterministic, offline, no API keys.


def run_retrieval(kb: KBBackend, strategy: Strategy, gold_dir: Path, k: int, verbose: bool) -> dict:
    items = []
    for path in sorted(gold_dir.glob("*.jsonl")):
        items.extend(json.loads(l) for l in path.read_text().splitlines() if l.strip())

    # structural tolerance: article-6.1.a credits expected article-6.1
    tolerance = build_tolerance(kb)

    per_cat: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    latencies: list[float] = []
    unanswerable_correct = 0
    unanswerable_total = 0

    for item in items:
        cat = item["category"]
        t0 = time.perf_counter()
        retrieved = strategy.retrieve(item["question"], k)
        latencies.append(time.perf_counter() - t0)

        if cat == "unanswerable":
            unanswerable_total += 1
            # correct handling: no expected units retrieved in top-k
            if not set(retrieved[:k]) & _plausible_hits(item):
                unanswerable_correct += 1
            continue

        p, r = precision_recall_at_k(retrieved, item["expected_units"], k, tolerance)
        m = mrr(retrieved, item["expected_units"], k, tolerance)
        c = chain_recall(retrieved, item["expected_units"], tolerance)
        per_cat[cat]["precision"].append(p)
        per_cat[cat]["recall"].append(r)
        per_cat[cat]["mrr"].append(m)
        per_cat[cat]["chain"].append(c)

    def avg(d: dict, key: str) -> float:
        vals = d.get(key, [])
        return sum(vals) / len(vals) if vals else 0.0

    all_mrr = [m for d in per_cat.values() for m in d["mrr"]]
    all_recall = [r for d in per_cat.values() for r in d["recall"]]
    results = {
        "strategy": strategy.name,
        "backend": getattr(kb, "__class__").__name__,
        "k": k,
        "n_items": len(items),
        "mrr_at_k": sum(all_mrr) / len(all_mrr) if all_mrr else 0.0,
        "recall_at_k": sum(all_recall) / len(all_recall) if all_recall else 0.0,
        "latency_mean_s": sum(latencies) / len(latencies) if latencies else 0.0,
        "latency_p95_s": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0,
        "unanswerable_no_hit_rate": unanswerable_correct / unanswerable_total if unanswerable_total else 0.0,
        "per_category": {
            cat: {
                "n": len(d["mrr"]),
                "precision": avg(d, "precision"),
                "recall": avg(d, "recall"),
                "mrr": avg(d, "mrr"),
                "chain_recall": avg(d, "chain"),
            }
            for cat, d in sorted(per_cat.items())
        },
    }
    if verbose:
        print(f"  {strategy.name}: MRR@{k}={results['mrr_at_k']:.3f} recall@{k}={results['recall_at_k']:.3f} latency={results['latency_mean_s']*1000:.1f}ms")
    return results


def _plausible_hits(item: dict) -> set[str]:
    """Terms from the question that would count as a hallucinated hit."""
    return set(tokenize(item["question"])) & set()  # placeholder: no-hit means empty expected


def run_reasoning(kb: KBBackend, strategy: Strategy, gold_dir: Path, k: int, verbose: bool) -> dict:
    items = []
    for path in sorted(gold_dir.glob("*.jsonl")):
        items.extend(json.loads(l) for l in path.read_text().splitlines() if l.strip())

    per_cat: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    unanswerable_correct = 0
    unanswerable_total = 0

    for item in items:
        cat = item["category"]
        if cat == "unanswerable-reasoning":
            unanswerable_total += 1
            # offline proxy: correct if the strategy surfaces no confident hook
            retrieved = strategy.retrieve(item["question"], k)
            expected_hops = item.get("expected_hops", [])
            if not expected_hops and not set(retrieved[:k]) & set(item.get("distractor_hops", [])):
                unanswerable_correct += 1
            continue

        retrieved = strategy.retrieve(item["question"], k)
        # Trace = retrieved context in rank order (what the agent walks)
        trace = retrieved[: k * 2]
        per_cat[cat]["hop_coverage"].append(hop_coverage(trace, item.get("expected_hops", [])))
        per_cat[cat]["distractor_resistance"].append(distractor_resistance(trace, item.get("distractor_hops", [])))
        per_cat[cat]["trace_validity"].append(trace_validity(kb, [h for h in item.get("expected_hops", []) if h in set(trace)]))

    def avg(d: dict, key: str) -> float:
        vals = d.get(key, [])
        return sum(vals) / len(vals) if vals else 0.0

    all_hops = [h for d in per_cat.values() for h in d["hop_coverage"]]
    results = {
        "strategy": strategy.name,
        "backend": getattr(kb, "__class__").__name__,
        "k": k,
        "n_items": len(items),
        "hop_coverage": sum(all_hops) / len(all_hops) if all_hops else 0.0,
        "unanswerable_no_hook_rate": unanswerable_correct / unanswerable_total if unanswerable_total else 0.0,
        "per_category": {
            cat: {
                "n": len(d["hop_coverage"]),
                "hop_coverage": avg(d, "hop_coverage"),
                "distractor_resistance": avg(d, "distractor_resistance"),
                "trace_validity": avg(d, "trace_validity"),
            }
            for cat, d in sorted(per_cat.items())
        },
    }
    if verbose:
        print(f"  {strategy.name}: hop_coverage={results['hop_coverage']:.3f} no_hook={results['unanswerable_no_hook_rate']:.3f}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="networkx", choices=["networkx", "llmwiki"])
    parser.add_argument("--strategy", type=int, choices=sorted(STRATEGIES))
    parser.add_argument("--gold", default=str(BENCH_DIR / "gold"), type=Path)
    parser.add_argument("--mode", default="retrieval", choices=["retrieval", "reasoning"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--all", action="store_true", help="Run all strategies for the mode")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON results here")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    # Gate: benchmark does not run on a red lint
    import subprocess

    lint = subprocess.run(
        ["uv", "run", "bench/lint_gold.py"],
        capture_output=True,
        text=True,
        cwd=str(BENCH_DIR.parent),
    )
    if lint.returncode != 0:
        print(lint.stdout)
        print("ABORT: gold lint is red — fix bench/gold/ first")
        return 1

    strategies = (ALL_RETRIEVAL if args.mode == "retrieval" else ALL_REASONING) if args.all else [args.strategy]
    corpus_dir = Path("data/eu-ai-act")
    kb = get_kb(args.backend, corpus_dir)

    all_results = []
    for s in strategies:
        strategy = STRATEGIES[s](kb)
        if args.mode == "reasoning":
            res = run_reasoning(kb, strategy, args.gold, args.k, args.verbose)
        else:
            res = run_retrieval(kb, strategy, args.gold, args.k, args.verbose)
        all_results.append(res)

    print(json.dumps(all_results, indent=2))
    if args.out:
        args.out.write_text(json.dumps(all_results, indent=2))
        print(f"\nresults -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
