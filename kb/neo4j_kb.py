"""Neo4j backend: loader + Cypher queries. Requires docker-compose service.

Start:  docker compose up -d neo4j
Load:   uv run python -m kb.neo4j_kb --load
Query:  via the KBBackend interface or the Neo4j Browser (http://localhost:7474)
"""

from __future__ import annotations

import os
from pathlib import Path

from . import KBBackend
from .graph import Node, build_graph, graph_stats

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "compliance-agents")


def load_graph(corpus_dir: Path) -> int:
    """Load the canonical graph into Neo4j. Returns node count."""
    from neo4j import GraphDatabase

    g = build_graph(corpus_dir)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        for node in g.nodes.values():
            session.run(
                "CREATE (n:Entity {id: $id, type: $type, title: $title, content: $content})",
                id=node.id, type=node.type, title=node.title, content=node.content[:5000],
            )
        for e in g.edges:
            session.run(
                "MATCH (a:Entity {id: $src}), (b:Entity {id: $dst}) "
                "CREATE (a)-[:REL {kind: $kind}]->(b)",
                src=e.src, dst=e.dst, kind=e.kind,
            )
        count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    driver.close()
    return count


class Neo4jKB(KBBackend):
    """Query Neo4j. Requires the docker service and a loaded graph."""

    def __init__(self, corpus_dir: Path, connect: bool = True):
        self.corpus_dir = corpus_dir
        self.driver = None
        if connect:
            from neo4j import GraphDatabase

            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def _run(self, query: str, **params):
        if self.driver is None:
            raise RuntimeError("Neo4j not connected — start docker compose service first")
        with self.driver.session() as session:
            return list(session.run(query, **params))

    def get_unit(self, unit_id: str) -> Node | None:
        rows = self._run("MATCH (n:Entity {id: $id}) RETURN n LIMIT 1", id=unit_id)
        if not rows:
            return None
        n = rows[0]["n"]
        return Node(id=n["id"], type=n.get("type", ""), title=n.get("title", ""), content=n.get("content", ""))

    def references(self, unit_id: str) -> list[str]:
        rows = self._run(
            "MATCH (a:Entity {id: $id})-[:REL {kind: 'REFERENCES'}]->(b) RETURN b.id AS id",
            id=unit_id,
        )
        return [r["id"] for r in rows]

    def edges(
        self,
        unit_id: str,
        direction: str = "out",
        kinds: tuple[str, ...] | None = None,
    ) -> list[tuple[str, str, str]]:
        if direction == "out":
            match = f"MATCH (a:Entity {{id: $id}})-[r:REL]->(b)"
        elif direction == "in":
            match = f"MATCH (a:Entity)-[r:REL]->(b:Entity {{id: $id}})"
        else:
            match = f"MATCH (a:Entity)-[r:REL]-(b:Entity {{id: $id}})"
        if kinds:
            match += " WHERE r.kind IN $kinds"
        rows = self._run(match + " RETURN a.id AS src, b.id AS dst, r.kind AS kind", id=unit_id, kinds=list(kinds or ()))
        return [(r["src"], r["dst"], r["kind"]) for r in rows]

    def obligations_for(self, actor_id: str) -> list[Node]:
        rows = self._run(
            "MATCH (a:Entity)-[:REL {kind: 'IMPOSES_ON'}]->(b:Entity {id: $id}) RETURN a.id AS id",
            id=actor_id,
        )
        return [self.get_unit(r["id"]) for r in rows if self.get_unit(r["id"])]

    def path(self, src: str, dst: str) -> list[str]:
        rows = self._run(
            "MATCH p = shortestPath((a:Entity {id: $src})-[*]-(b:Entity {id: $dst})) "
            "RETURN [n IN nodes(p) | n.id] AS ids",
            src=src, dst=dst,
        )
        return rows[0]["ids"] if rows else []

    def search(self, query: str) -> list[str]:
        rows = self._run(
            "MATCH (n:Entity) WHERE toLower(n.content) CONTAINS toLower($q) "
            "OR toLower(n.title) CONTAINS toLower($q) RETURN n.id AS id LIMIT 50",
            q=query,
        )
        return [r["id"] for r in rows]

    def stats(self) -> dict[str, int]:
        return graph_stats(build_graph(self.corpus_dir))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", action="store_true", help="Load corpus into Neo4j")
    parser.add_argument("--corpus-dir", default="data/eu-ai-act", type=Path)
    args = parser.parse_args()
    if args.load:
        n = load_graph(args.corpus_dir)
        print(f"Loaded {n} nodes into Neo4j at {NEO4J_URI}")
    else:
        parser.print_help()
