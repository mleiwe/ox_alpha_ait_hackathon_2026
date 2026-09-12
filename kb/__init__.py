"""Shared query interface for knowledge-base backends.

All backends expose the same surface so the phase-3 benchmark can swap them:

    from kb import get_kb
    kb = get_kb("networkx")   # or "llmwiki", "neo4j"
"""

from __future__ import annotations

import abc
from pathlib import Path

from .graph import Graph, Node


class KBBackend(abc.ABC):
    """Uniform query surface across backends."""

    @abc.abstractmethod
    def get_unit(self, unit_id: str) -> Node | None:
        """Fetch a node by id (single-hop)."""

    @abc.abstractmethod
    def references(self, unit_id: str) -> list[str]:
        """Outgoing REFERENCES targets (cross-reference traversal)."""

    @abc.abstractmethod
    def obligations_for(self, actor_id: str) -> list[Node]:
        """Obligations imposed on an actor (e.g. actor-provider)."""

    @abc.abstractmethod
    def path(self, src: str, dst: str) -> list[str]:
        """Shortest path between two nodes (multi-hop)."""

    @abc.abstractmethod
    def search(self, query: str) -> list[str]:
        """Keyword search over node content. Returns node ids."""

    @abc.abstractmethod
    def stats(self) -> dict[str, int]:
        """Node counts by type + edges."""


def get_kb(backend: str, corpus_dir: Path | None = None, directed: bool = True) -> KBBackend:
    """Instantiate a backend by name.

    directed=True (default): traversal respects legal edge direction
    (cites, imposes-on, contains) with undirected fallback for path().
    directed=False: fully undirected graph.
    """
    corpus_dir = corpus_dir or Path("data/eu-ai-act")
    if backend == "networkx":
        from .networkx_kb import NetworkXKB

        return NetworkXKB(corpus_dir, directed=directed)
    if backend == "llmwiki":
        from .llmwiki_kb import LLMwikiKB

        return LLMwikiKB(corpus_dir)
    if backend == "neo4j":
        from .neo4j_kb import Neo4jKB

        return Neo4jKB(corpus_dir)
    raise ValueError(f"unknown backend: {backend!r} (expected networkx|llmwiki|neo4j)")
