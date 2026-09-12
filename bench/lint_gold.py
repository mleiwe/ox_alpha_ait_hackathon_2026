"""Gold-set lint — the benchmark does not run on a red lint.

Checks (plan prerequisites 3 + reasoning qualification lint):
  1. every `expected_units` / `expected_hops` / `distractor_hops` entry exists
     as a node in the graph;
  2. every expected chain is realizable: consecutive `expected_hops` connect
     via a real path over the KBBackend ABC;
  3. reasoning qualification: an item counts as reasoning only if the verdict
     is NOT derivable from any single node — either (a) expected_hops span
     >= 2 distinct articles with the verdict-determining unit in a different
     article than the rule unit, or (b) the verdict requires applying an
     exception unit distinct from the rule unit;
  4. unanswerable items must have empty expected_units/hops;
  5. schema sanity: required fields present, verdict labels enumerated.

Usage:
    uv run bench/lint_gold.py            # lint everything
    uv run bench/lint_gold.py --verbose  # print per-item detail
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from kb import get_kb  # noqa: E402

BENCH_DIR = Path(__file__).parent
GOLD_DIR = BENCH_DIR / "gold"
REASONING_DIR = GOLD_DIR / "reasoning"

REQUIRED_RETRIEVAL = {"id", "category", "question", "expected_units", "expected_answer"}
REQUIRED_REASONING = {"id", "category", "question", "expected_hops", "expected_verdict"}

# Enumerated verdict labels (plan: exact-match, never free-text judged)
VERDICT_LABELS = {
    "prohibited",
    "not-prohibited",
    "high-risk",
    "not-high-risk",
    "in-scope",
    "out-of-scope",
    "provider-obligations",
    "deployer-obligations",
    "importer-obligations",
    "distributor-obligations",
    "limited-articles",
    "no-basis-in-corpus",
}


def load_jsonl(path: Path) -> list[dict]:
    items = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}:{i}: invalid JSON: {e}")
    return items


def root_article(unit_id: str) -> str:
    """article-5.1.f -> article-5 ; annex-iii -> annex-iii ; def-provider -> def-provider."""
    if unit_id.startswith(("article-", "annex-")):
        parts = unit_id.split(".")
        return parts[0] if len(parts) == 1 else parts[0] + ("-" + parts[1] if parts[0].startswith("annex") and len(parts) > 1 and not parts[1].isdigit() and not _is_roman(parts[1]) else "")
    return unit_id


def _is_roman(s: str) -> bool:
    return all(c in "ivxl" for c in s.lower()) and bool(s)


def article_root(unit_id: str) -> str:
    """Root article of a unit: article-5.1.f -> article-5, annex-iii -> annex-iii."""
    if unit_id.startswith("article-"):
        return unit_id.split(".")[0]
    return unit_id


def chain_realizable(kb, hops: list[str]) -> tuple[bool, str]:
    """Consecutive hops must connect via a real path over the ABC."""
    for a, b in zip(hops, hops[1:]):
        p = kb.path(a, b)
        if not p or p[-1] != b:
            return False, f"no path {a} -> {b}"
    return True, ""


def qualifies_as_reasoning(item: dict) -> tuple[bool, str]:
    """Qualification lint: verdict not derivable from any single node.

    (a) expected_hops span >= 2 distinct articles AND the verdict-determining
        unit (last hop) is in a different article than the rule unit (first
        article-rooted hop), OR
    (b) the item's category is exception-application (verdict requires
        applying an exception unit distinct from the rule unit).
    """
    hops = item.get("expected_hops", [])
    articles = {article_root(h) for h in hops if h.startswith(("article-", "annex-"))}
    if item.get("category") == "exception-application":
        return True, "exception unit distinct from rule unit"
    if len(articles) >= 2:
        first_article = article_root(hops[0]) if hops[0].startswith(("article-", "annex-")) else None
        last_article = article_root(hops[-1]) if hops[-1].startswith(("article-", "annex-")) else None
        if first_article and last_article and first_article != last_article:
            return True, f"spans {len(articles)} articles ({first_article} -> {last_article})"
        return False, "hops span >=2 articles but rule and verdict units share an article"
    return False, f"verdict derivable from a single article ({articles or 'none'})"


def lint_retrieval(kb, verbose: bool) -> tuple[list[str], int]:
    errors: list[str] = []
    n = 0
    for path in sorted(GOLD_DIR.glob("*.jsonl")):
        for item in load_jsonl(path):
            n += 1
            loc = f"{path.name}:{item.get('id', '?')}"
            missing_fields = REQUIRED_RETRIEVAL - set(item)
            if missing_fields:
                errors.append(f"{loc}: missing fields {sorted(missing_fields)}")
                continue
            if item["category"] == "unanswerable":
                if item["expected_units"]:
                    errors.append(f"{loc}: unanswerable item has expected_units")
                if item["expected_answer"] != "I don't know":
                    errors.append(f"{loc}: unanswerable expected_answer must be \"I don't know\"")
                continue
            for unit in item["expected_units"]:
                if kb.get_unit(unit) is None:
                    errors.append(f"{loc}: expected unit does not exist: {unit}")
    if verbose:
        print(f"  retrieval items linted: {n}")
    return errors, n


def lint_reasoning(kb, verbose: bool) -> tuple[list[str], int]:
    errors: list[str] = []
    n = 0
    qualified = 0
    for path in sorted(REASONING_DIR.glob("*.jsonl")):
        for item in load_jsonl(path):
            n += 1
            loc = f"reasoning/{path.name}:{item.get('id', '?')}"
            missing_fields = REQUIRED_REASONING - set(item)
            if missing_fields:
                errors.append(f"{loc}: missing fields {sorted(missing_fields)}")
                continue
            # Node existence
            for hop in item.get("expected_hops", []) + item.get("distractor_hops", []):
                if kb.get_unit(hop) is None:
                    errors.append(f"{loc}: hop does not exist: {hop}")
            # Chain realizability
            hops = item.get("expected_hops", [])
            if hops:
                ok, why = chain_realizable(kb, hops)
                if not ok:
                    errors.append(f"{loc}: expected chain not realizable ({why})")
            # Verdict label
            verdict = item.get("expected_verdict", "")
            if verdict.startswith("temporal:"):
                date = verdict.split(":", 1)[1]
                if len(date) != 10 or date[4] != "-" or date[7] != "-":
                    errors.append(f"{loc}: temporal verdict must be YYYY-MM-DD, got {date!r}")
            elif verdict not in VERDICT_LABELS:
                errors.append(f"{loc}: verdict {verdict!r} not in enumerated labels")
            # Unanswerable reasoning
            if item["category"] == "unanswerable-reasoning":
                if hops:
                    errors.append(f"{loc}: unanswerable item has expected_hops")
                if verdict != "no-basis-in-corpus":
                    errors.append(f"{loc}: unanswerable verdict must be no-basis-in-corpus")
                continue
            # Qualification lint (skip for unanswerable — no hops by design)
            ok, why = qualifies_as_reasoning(item)
            if ok:
                qualified += 1
                if verbose:
                    print(f"  QUALIFIED {loc}: {why}")
            else:
                errors.append(f"{loc}: FAILS qualification lint — {why} (move to retrieval tiers)")
    if verbose:
        print(f"  reasoning items linted: {n} (qualified: {qualified})")
    return errors, n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    kb = get_kb("networkx")
    stats = kb.stats()
    print(f"graph: {sum(v for k, v in stats.items() if k != 'EDGES')} nodes, {stats['EDGES']} edges")

    errors: list[str] = []
    n_ret, n_rea = 0, 0
    e, n_ret = lint_retrieval(kb, args.verbose)
    errors += e
    e, n_rea = lint_reasoning(kb, args.verbose)
    errors += e

    print(f"\nlinted {n_ret} retrieval + {n_rea} reasoning items")
    if errors:
        print(f"\nRED LINT — {len(errors)} error(s):")
        for err in errors:
            print(f"  ✗ {err}")
        return 1
    print("GREEN LINT — gold set is realizable and qualified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
