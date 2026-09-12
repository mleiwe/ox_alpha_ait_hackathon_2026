"""Query CLI for the knowledge-base backends.

Usage:
    uv run python -m kb.query --backend networkx --unit article-5
    uv run python -m kb.query --backend networkx --obligations-for actor-provider
    uv run python -m kb.query --backend networkx --path article-6 annex-iii
    uv run python -m kb.query --backend networkx --search "CV screening"
    uv run python -m kb.query --backend llmwiki --stats
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import get_kb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="networkx", choices=["networkx", "llmwiki", "neo4j"])
    parser.add_argument("--corpus-dir", default="data/eu-ai-act", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--unit", help="Fetch a unit by id")
    group.add_argument("--references", help="Outgoing references of a unit")
    group.add_argument("--obligations-for", help="Obligations imposed on an actor")
    group.add_argument("--path", nargs=2, metavar=("SRC", "DST"), help="Shortest path")
    group.add_argument("--search", help="Keyword search")
    group.add_argument("--stats", action="store_true", help="Graph stats")
    args = parser.parse_args()

    kb = get_kb(args.backend, args.corpus_dir)

    if args.unit:
        node = kb.get_unit(args.unit)
        if node is None:
            print(f"not found: {args.unit}")
            return 1
        print(node.content or node.title)
    elif args.references:
        print(json.dumps(kb.references(args.references), indent=2))
    elif args.obligations_for:
        for ob in kb.obligations_for(args.obligations_for):
            print(f"[{ob.id}] {ob.title}")
    elif args.path:
        print(" -> ".join(kb.path(*args.path)) or "no path")
    elif args.search:
        for nid in kb.search(args.search)[:20]:
            print(nid)
    elif args.stats:
        print(json.dumps(kb.stats(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
