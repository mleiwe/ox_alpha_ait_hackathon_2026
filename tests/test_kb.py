"""Tests for the KB layer: graph builder + NetworkX/LLMwiki backends.

Runs against the real corpus (data/eu-ai-act) — phase 1 output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kb.graph import build_graph, graph_stats
from kb.llmwiki_kb import LLMwikiKB, generate_wiki
from kb.networkx_kb import NetworkXKB

CORPUS = Path(__file__).parent.parent / "data" / "eu-ai-act"


@pytest.fixture(scope="module")
def graph():
    return build_graph(CORPUS)


@pytest.fixture(scope="module")
def nx_kb(graph):
    return NetworkXKB(CORPUS)


def test_corpus_exists():
    assert (CORPUS / "articles" / "article-5.md").exists()
    assert (CORPUS / "recitals" / "recital-1.md").exists()


def test_graph_has_units(graph):
    stats = graph_stats(graph)
    assert stats.get("Article", 0) >= 100
    assert stats.get("Recital", 0) >= 170
    assert stats.get("Annex", 0) >= 10
    assert stats["EDGES"] > 0


def test_definitions_extracted(graph):
    defs = [n for n in graph.nodes.values() if n.type == "Definition"]
    assert len(defs) >= 20  # Article 3 defines ~70 terms
    def_ids = {d.id for d in defs}
    assert "def-ai-system" in def_ids


def test_actors_extracted(graph):
    actors = {n.id for n in graph.nodes.values() if n.type == "Actor"}
    assert "actor-provider" in actors
    assert "actor-deployer" in actors


def test_cross_references(graph):
    # Article 6(2) references Annex III
    refs = [e.dst for e in graph.edges if e.src == "article-6" and e.kind == "REFERENCES"]
    assert "annex-iii" in refs


def test_recital_interpretation(graph):
    interprets = [e for e in graph.edges if e.kind == "INTERPRETS"]
    assert len(interprets) > 40  # deduplicated; repeated links collapse to one weighted edge


def test_definition_usage_edges(graph):
    """Clauses/sub-clauses that use an Art 3 term get USES_DEFINITION edges."""
    uses = [e for e in graph.edges if e.kind == "USES_DEFINITION"]
    assert len(uses) > 1000
    # clause-level sources (article-1.1 etc.)
    assert any("." in e.src for e in uses)


def test_clause_level_references(graph):
    """Clauses/sub-clauses referencing other articles (direct refs)."""
    clause_refs = [e for e in graph.edges if e.kind == "REFERENCES" and "." in e.src]
    assert len(clause_refs) > 300


def test_edge_weights(graph):
    """All edges carry a weight; direct citations weigh more than containment."""
    assert all("weight" in e.attrs for e in graph.edges)
    ref = next(e for e in graph.edges if e.kind == "REFERENCES")
    sub = next(e for e in graph.edges if e.kind == "HAS_SUBUNIT")
    assert float(ref.attrs["weight"]) > float(sub.attrs["weight"])


def test_obligations_imposed(graph):
    provider_obs = [e for e in graph.edges if e.kind == "IMPOSES_ON" and e.dst == "actor-provider"]
    assert len(provider_obs) > 0


def test_networkx_single_hop(nx_kb):
    node = nx_kb.get_unit("article-5")
    assert node is not None
    assert "prohibited" in node.content.lower()


def test_networkx_multi_hop(nx_kb):
    path = nx_kb.path("article-6", "annex-iii")
    assert path, "expected a path from article-6 to annex-iii"
    assert path[0] == "article-6" and path[-1] == "annex-iii"


def test_networkx_obligations(nx_kb):
    obs = nx_kb.obligations_for("actor-provider")
    assert len(obs) > 0


def test_networkx_search(nx_kb):
    hits = nx_kb.search("biometric")
    assert "article-5" in hits or any("biometric" in h for h in hits)


def test_llmwiki_roundtrip(tmp_path, graph):
    wiki_dir = tmp_path / "wiki"
    generate_wiki(graph, wiki_dir)
    assert (wiki_dir / "INDEX.md").exists()
    assert (wiki_dir / "edges.csv").exists()
    assert (wiki_dir / "pages" / "article-5.md").exists()

    kb = LLMwikiKB(CORPUS, wiki_dir=wiki_dir)
    node = kb.get_unit("article-5")
    assert node is not None
    assert "annex-iii" in kb.references("article-6")
    assert len(kb.obligations_for("actor-provider")) > 0
    assert kb.path("article-6", "annex-iii")


def test_backends_agree(nx_kb, graph, tmp_path):
    """NetworkX and LLMwiki must return identical traversal results."""
    wiki_dir = tmp_path / "wiki"
    generate_wiki(graph, wiki_dir)
    wiki_kb = LLMwikiKB(CORPUS, wiki_dir=wiki_dir)

    assert nx_kb.references("article-6") == wiki_kb.references("article-6")
    assert len(nx_kb.obligations_for("actor-provider")) == len(wiki_kb.obligations_for("actor-provider"))


def test_parser_parent_fix(graph):
    """Same-level headings chain to their true parent, not linearly (verified bug).

    article-5.1.f (emotion inference) must exist at paragraph depth, not as
    article-5.1.a.b.ba.bb.c.i.ii.d.e.f (the old linear-chain bug).
    """
    assert "article-5.1.f" in graph.nodes
    assert "article-5.1.a.b.ba.bb.c.i.ii.d.e.f" not in graph.nodes
    node = graph.nodes["article-5.1.f"]
    assert "emotion" in node.content.lower()
    # parent chain: article-5.1.f -> article-5.1 -> article-5
    parents = [e.src for e in graph.edges if e.dst == "article-5.1.f" and e.kind == "HAS_SUBUNIT"]
    assert parents == ["article-5.1"]


def test_corpus_hygiene_excluded_files(graph):
    """The stray large-scale-IT-systems annex (duplicates Annex X) is excluded."""
    assert not any("union-legislative" in nid for nid in graph.nodes)


def test_backend_edges_method(nx_kb, graph, tmp_path):
    """ABC edges(unit, direction, kinds) works on both backends (strategy 4 surface)."""
    wiki_dir = tmp_path / "wiki"
    generate_wiki(graph, wiki_dir)
    wiki_kb = LLMwikiKB(CORPUS, wiki_dir=wiki_dir)

    for kb in (nx_kb, wiki_kb):
        out = kb.edges("article-6", direction="out", kinds=("REFERENCES",))
        assert out, "expected outgoing REFERENCES from article-6"
        assert all(kind == "REFERENCES" for _s, _d, kind in out)
        both = kb.edges("article-6", direction="both", kinds=("HAS_SUBUNIT",))
        assert both, "expected HAS_SUBUNIT edges touching article-6"
        # kind filter is respected
        kinds = {kind for _s, _d, kind in kb.edges("article-6", direction="both", kinds=("REFERENCES", "IMPOSES_ON"))}
        assert kinds <= {"REFERENCES", "IMPOSES_ON"}


def test_gold_lint_green():
    """The benchmark does not run on a red lint — gold set must pass."""
    import subprocess

    result = subprocess.run(
        ["uv", "run", "bench/lint_gold.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"gold lint red:\n{result.stdout}"
