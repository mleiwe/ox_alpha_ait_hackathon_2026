"""NetworkX backend: in-process graph, zero infra.

Best for: benchmarking, offline IDE agents, quick traversal queries.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from . import KBBackend
from .graph import Node, build_graph, graph_stats


class NetworkXKB(KBBackend):
    def __init__(self, corpus_dir: Path, directed: bool = True):
        self.graph_data = build_graph(corpus_dir)
        self.directed = directed
        self.g: nx.Graph | nx.DiGraph = nx.DiGraph() if directed else nx.Graph()
        for node in self.graph_data.nodes.values():
            self.g.add_node(node.id, **{"type": node.type, "title": node.title, "content": node.content, **node.attrs})
        for e in self.graph_data.edges:
            self.g.add_edge(e.src, e.dst, kind=e.kind, weight=float(e.attrs.get("weight", 1.0)))

    def get_unit(self, unit_id: str) -> Node | None:
        if unit_id not in self.g:
            return None
        data = self.g.nodes[unit_id]
        return Node(id=unit_id, type=data.get("type", ""), title=data.get("title", ""), content=data.get("content", ""))

    def references(self, unit_id: str) -> list[str]:
        refs = {dst for _, dst, d in self.g.out_edges(unit_id, data=True) if d.get("kind") == "REFERENCES"}
        return sorted(refs)

    def obligations_for(self, actor_id: str) -> list[Node]:
        results = []
        for src, _dst, d in self.g.in_edges(actor_id, data=True):
            if d.get("kind") == "IMPOSES_ON":
                node = self.get_unit(src)
                if node:
                    results.append(node)
        return results

    def path(self, src: str, dst: str) -> list[str]:
        try:
            if self.directed:
                # Directed traversal first (respects legal direction: cites,
                # imposes-on, contains). Fall back to undirected if no path.
                try:
                    return nx.shortest_path(self.g, src, dst)
                except nx.NetworkXNoPath:
                    undirected = self.g.to_undirected()
                    return nx.shortest_path(undirected, src, dst)
            return nx.shortest_path(self.g, src, dst)
        except (nx.NodeNotFound, nx.NetworkXNoPath):
            return []

    def search(self, query: str) -> list[str]:
        q = query.lower()
        return [nid for nid, data in self.g.nodes(data=True) if q in (data.get("content") or "").lower() or q in (data.get("title") or "").lower()]

    def stats(self) -> dict[str, int]:
        return graph_stats(self.graph_data)
