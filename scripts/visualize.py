#!/usr/bin/env python3
"""Generate visualisations of the EU AI Act knowledge graph.

Outputs into `viz/`:
  - matplotlib PNGs (render inline in GitHub PRs)
  - pyvis interactive HTML (open in browser)
  - t-SNE embedding projection (semantic clusters by node type)

Edge weights: REFERENCES edges are weighted by citation count (how many times
unit A cites unit B across the corpus). Weight drives edge thickness (static)
and width (interactive). Other edge kinds are unweighted (structural).

Usage:
    uv run python scripts/visualize.py [--corpus-dir data/eu-ai-act] [--out viz]
"""

from __future__ import annotations

import argparse
import collections
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from kb.graph import build_graph, graph_stats

# Colour per node type (interactive graph + legends)
TYPE_COLOURS = {
    "Article": "#4C72B0",
    "Paragraph": "#7FA6D9",
    "Point": "#A8C4E8",
    "SubPoint": "#CDDCF2",
    "Recital": "#DD8452",
    "Annex": "#937860",
    "Definition": "#55A868",
    "Actor": "#C44E52",
    "RiskTier": "#8172B3",
    "Obligation": "#CCB974",
}

EDGE_KINDS = ["REFERENCES", "HAS_SUBUNIT", "DEFINES", "IS_ROLE_OF", "HAS_OBLIGATION", "IMPOSES_ON", "CLASSIFIES_AS", "INTERPRETS"]


def type_legend(ax_handles=None, types=None) -> list[Line2D]:
    """Legend handles for node types."""
    keys = types or list(TYPE_COLOURS.keys())
    return [Line2D([0], [0], marker="o", color="w", markerfacecolor=TYPE_COLOURS[k], markersize=9, label=k) for k in keys]


def bar_chart(ax, items: list[tuple[str, int]], title: str, colour: str) -> None:
    labels, values = zip(*items) if items else ([], [])
    ax.barh(range(len(items)), values, color=colour)
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_title(title)
    for i, v in enumerate(values):
        ax.text(v, i, f" {v}", va="center", fontsize=9)


def static_charts(g, out_dir: Path) -> None:
    plt.rcParams.update({"figure.autolayout": True})

    # 1. Node types (with legend)
    stats = graph_stats(g)
    nodes = [(k, v) for k, v in stats.items() if k != "EDGES"]
    nodes.sort(key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(9, 5))
    bar_chart(ax, nodes, "Knowledge graph — nodes by type", "#4C72B0")
    fig.savefig(out_dir / "node-types.png", dpi=150)
    plt.close(fig)

    # 2. Edge kinds (with legend of edge semantics)
    edge_counts = collections.Counter(e.kind for e in g.edges)
    edges = sorted(edge_counts.items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bar_chart(ax, edges, "Knowledge graph — edges by kind", "#55A868")
    fig.savefig(out_dir / "edge-types.png", dpi=150)
    plt.close(fig)

    # 3. Obligations per actor
    actor_obs = collections.Counter(e.dst for e in g.edges if e.kind == "IMPOSES_ON")
    items = sorted(actor_obs.items(), key=lambda kv: kv[1])
    labels = [g.nodes[nid].title if nid in g.nodes else nid for nid, _ in items]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.barh(range(len(items)), [v for _, v in items], color="#C44E52")
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_title("Compliance burden — obligations imposed per actor")
    for i, (_, v) in enumerate(items):
        ax.text(v, i, f" {v}", va="center", fontsize=9)
    fig.savefig(out_dir / "obligations-by-actor.png", dpi=150)
    plt.close(fig)

    # 4. Article-level reference network (spring layout, weighted edges, legend)
    import networkx as nx

    article_ids = {n.id for n in g.nodes.values() if n.type in ("Article", "Annex")}
    sub = nx.DiGraph()
    for e in g.edges:
        if e.src in article_ids and e.dst in article_ids and e.kind == "REFERENCES":
            w = sub[u][v]["weight"] + 1 if sub.has_edge(u := e.src, v := e.dst) else 1
            sub.add_edge(e.src, e.dst, weight=w)
    fig, ax = plt.subplots(figsize=(14, 11))
    if len(sub) > 0:
        pos = nx.spring_layout(sub, k=0.35, seed=42, weight="weight")
        node_colours = ["#937860" if nid.startswith("annex") else "#4C72B0" for nid in sub.nodes]
        weights = [sub[u][v]["weight"] for u, v in sub.edges]
        max_w = max(weights)
        widths = [0.3 + 2.5 * (w / max_w) for w in weights]
        nx.draw_networkx_nodes(sub, pos, ax=ax, node_size=90, node_color=node_colours, alpha=0.85)
        nx.draw_networkx_edges(sub, pos, ax=ax, alpha=0.18, arrows=False, width=widths)
        # label key hubs only
        degrees = dict(sub.degree())
        hubs = sorted(degrees, key=degrees.get, reverse=True)[:14]
        nx.draw_networkx_labels(sub, pos, labels={h: h.replace("article-", "Art ").replace("annex-", "Annex ") for h in hubs}, ax=ax, font_size=8)
        # legend: node types + edge weight scale
        handles = type_legend(types=["Article", "Annex"])
        handles += [
            Line2D([0], [0], color="#4C72B0", lw=0.5, label="1 citation"),
            Line2D([0], [0], color="#4C72B0", lw=1.5, label="~5 citations"),
            Line2D([0], [0], color="#4C72B0", lw=2.8, label=f"{max_w} citations (max)"),
        ]
        ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.9)
        ax.set_title(f"Article ↔ Annex reference network ({len(sub)} nodes, {sub.number_of_edges()} REFERENCES edges)\nEdge width = citation count")
    ax.axis("off")
    fig.savefig(out_dir / "article-graph.png", dpi=150)
    plt.close(fig)

    # 5. Definitions → actors network (with legend)
    defs = {n.id for n in g.nodes.values() if n.type == "Definition"}
    actors = {n.id for n in g.nodes.values() if n.type == "Actor"}
    sub2 = nx.DiGraph()
    for e in g.edges:
        if e.kind == "DEFINES" and e.src in g.nodes and e.dst in defs:
            sub2.add_edge(e.src, e.dst)
        if e.kind == "IS_ROLE_OF" and e.src in defs and e.dst in actors:
            sub2.add_edge(e.src, e.dst)
    fig, ax = plt.subplots(figsize=(12, 9))
    if len(sub2) > 0:
        pos = nx.spring_layout(sub2, k=0.4, seed=42)
        colours = ["#C44E52" if n in actors else "#55A868" for n in sub2.nodes]
        nx.draw_networkx_nodes(sub2, pos, ax=ax, node_size=70, node_color=colours, alpha=0.85)
        nx.draw_networkx_edges(sub2, pos, ax=ax, alpha=0.15, arrows=False)
        handles = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#55A868", markersize=9, label="Definition (Art 3)"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#C44E52", markersize=9, label="Actor (regulated role)"),
        ]
        ax.legend(handles=handles, loc="upper right", fontsize=9, framealpha=0.9)
        ax.set_title(f"Article 3 definitions → actors ({len(sub2)} nodes)")
    ax.axis("off")
    fig.savefig(out_dir / "definitions-network.png", dpi=150)
    plt.close(fig)

    # 6. Interaction heatmap with dendrogram grouping (article + clause level)
    heatmap_chart(g, out_dir, level="article")
    heatmap_chart(g, out_dir, level="clause")


def heatmap_chart(g, out_dir: Path, level: str = "article") -> None:
    """Interaction heatmap: unit × unit REFERENCES matrix, grouped by
    hierarchical clustering with dendrograms on both axes.

    Dendrograms show the cluster hierarchy (which units cite alike) alongside
    the collated matrix — block structure emerges from the clustering order.
    """
    import numpy as np
    from scipy.cluster.hierarchy import dendrogram, linkage
    from scipy.spatial.distance import pdist

    if level == "article":
        unit_ids = sorted(n.id for n in g.nodes.values() if n.type in ("Article", "Annex"))
        title = "Article ↔ Annex citation interactions"
        fname = "heatmap-articles.png"
    else:
        # Clause-level: paragraphs + points (top N by interaction count)
        unit_ids = sorted(
            n.id for n in g.nodes.values() if n.type in ("Paragraph", "Point", "SubPoint")
        )
        title = "Clause-level citation interactions (paragraphs/points)"
        fname = "heatmap-clauses.png"

    index = {nid: i for i, nid in enumerate(unit_ids)}
    n = len(unit_ids)
    if n < 5:
        return

    mat = np.zeros((n, n))
    for e in g.edges:
        if e.kind != "REFERENCES":
            continue
        if e.src in index and e.dst in index:
            mat[index[e.src], index[e.dst]] += 1

    # Clause-level matrix is huge — keep only units with >=1 interaction
    if level != "article":
        active = np.where(mat.sum(axis=1) + mat.sum(axis=0) > 0)[0]
        mat = mat[np.ix_(active, active)]
        unit_ids = [unit_ids[i] for i in active]
        n = len(unit_ids)
        if n < 5:
            print("  heatmap-clauses: not enough interactions, skipped")
            return

    # Hierarchical clustering on the symmetric interaction profile
    # (rows of the matrix = who each unit cites/is cited by).
    sym = mat + mat.T
    np.fill_diagonal(sym, sym.diagonal())  # keep self-citations
    Z = linkage(sym, method="average", metric="euclidean")

    fig = plt.figure(figsize=(18, 16))
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 5], height_ratios=[1, 5], wspace=0.01, hspace=0.01)

    # Dendrograms: top (columns) and left (rows)
    ax_dend_top = fig.add_subplot(gs[0, 1])
    ax_dend_left = fig.add_subplot(gs[1, 0])
    ax_heat = fig.add_subplot(gs[1, 1])

    def short(nid: str) -> str:
        return nid.replace("article-", "Art ").replace("annex-", "Annex ")

    # Column dendrogram
    dendrogram(Z, ax=ax_dend_top, orientation="top", no_labels=True, color_threshold=0.7 * Z[:, 2].max())
    ax_dend_top.set_xticks([])
    ax_dend_top.set_yticks([])
    for spine in ax_dend_top.spines.values():
        spine.set_visible(False)

    # Row dendrogram
    dendrogram(Z, ax=ax_dend_left, orientation="left", no_labels=True, color_threshold=0.7 * Z[:, 2].max())
    ax_dend_left.set_xticks([])
    ax_dend_left.set_yticks([])
    for spine in ax_dend_left.spines.values():
        spine.set_visible(False)

    # Heatmap in the dendrogram's leaf order
    leaves = dendrogram(Z, no_plot=True)["leaves"]
    mat_ordered = mat[np.ix_(leaves, leaves)]
    ordered_ids = [unit_ids[i] for i in leaves]

    im = ax_heat.imshow(np.log1p(mat_ordered), cmap="magma", aspect="auto", interpolation="nearest")

    step = max(1, n // 60)
    ticks = list(range(0, n, step))
    ax_heat.set_xticks(ticks)
    ax_heat.set_yticks(ticks)
    ax_heat.set_xticklabels([short(ordered_ids[i]) for i in ticks], rotation=90, fontsize=6)
    ax_heat.set_yticklabels([short(ordered_ids[i]) for i in ticks], fontsize=6)
    ax_heat.set_xlabel("Cited unit")
    ax_heat.set_ylabel("Citing unit")
    ax_heat.set_title(f"{title} ({n}×{n}, log-scaled, dendrogram-grouped)")

    # Colourbar
    cbar = fig.colorbar(im, ax=ax_heat, label="log(1 + citation count)", shrink=0.6, pad=0.02)

    # Legend: colourbar meaning + dendrogram colour coding
    handles = [
        Line2D([0], [0], color="#4C72B0", lw=2, label="dendrogram: cluster merge distance"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#000000", markersize=10, label="dark cell = many citations"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#fcfdbf", markersize=10, label="light cell = few/none", markeredgecolor="#ccc"),
    ]
    ax_dend_left.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.9, title="Legend")

    fig.savefig(out_dir / fname, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  heatmap ({level}): {n}×{n}, dendrogram-grouped")


LEGEND_HTML = """
<div style="position:fixed; top:12px; left:12px; z-index:9999;
     background:rgba(255,255,255,0.92); border:1px solid #ccc; border-radius:6px;
     padding:10px 14px; font-family:sans-serif; font-size:13px; color:#333;
     box-shadow:0 1px 4px rgba(0,0,0,0.15);">
  <div style="font-weight:600; margin-bottom:6px;">{title}</div>
  {items}
</div>
"""


def _legend_items(pairs: list[tuple[str, str]], shape: str = "square") -> str:
    """HTML for legend rows: (label, colour)."""
    if shape == "square":
        swatch = 'display:inline-block; width:12px; height:12px; margin-right:7px; border-radius:2px; background:{c};'
    else:  # line
        swatch = 'display:inline-block; width:22px; height:0; margin-right:7px; border-top:3px solid {c}; vertical-align:middle;'
    return "".join(
        f'<div style="margin:3px 0;"><span style="{swatch.format(c=c)}"></span>{label}</div>'
        for label, c in pairs
    )


def interactive_graphs(g, out_dir: Path) -> None:
    from pyvis.network import Network

    def build(net: Network, node_ids: set[str], title: str) -> None:
        for node in g.nodes.values():
            if node.id in node_ids:
                net.add_node(
                    node.id,
                    label=node.title[:40] or node.id,
                    color=TYPE_COLOURS.get(node.type, "#999"),
                    title=f"{node.type}: {node.title}",
                )
        for e in g.edges:
            if e.src in node_ids and e.dst in node_ids:
                net.add_edge(e.src, e.dst, title=e.kind)

    def write_with_legend(net: Network, path: Path, title: str, node_types: list[str], show_edge_scale: bool = False) -> None:
        net.write_html(str(path))
        html = path.read_text(encoding="utf-8")
        items = _legend_items([(t, TYPE_COLOURS.get(t, "#999")) for t in node_types])
        if show_edge_scale:
            items += _legend_items([("edge width = citation count", "#4C72B0")], shape="line")
        legend = LEGEND_HTML.format(title=title, items=items)
        # Inject before </body>
        html = html.replace("</body>", legend + "\n</body>")
        path.write_text(html, encoding="utf-8")

    # Full graph (may be heavy but pyvis handles a few thousand nodes)
    net = Network(height="800px", width="100%", bgcolor="#ffffff", font_color="#333", notebook=False)
    net.force_atlas_2based(gravity=-40)
    build(net, set(g.nodes.keys()), "EU AI Act knowledge graph — colour by node type")
    full_types = [t for t in TYPE_COLOURS if any(n.type == t for n in g.nodes.values())]
    write_with_legend(net, out_dir / "graph-interactive.html", "EU AI Act knowledge graph — colour by node type", full_types)

    # Article-level subgraph
    net2 = Network(height="800px", width="100%", bgcolor="#ffffff", font_color="#333", notebook=False)
    net2.force_atlas_2based(gravity=-40)
    article_ids = {n.id for n in g.nodes.values() if n.type in ("Article", "Annex")}
    build(net2, article_ids, "EU AI Act — article-level reference network")
    write_with_legend(net2, out_dir / "article-graph.html", "EU AI Act — article-level reference network", ["Article", "Annex"], show_edge_scale=True)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", default="data/eu-ai-act", type=Path)
    parser.add_argument("--out", default="viz", type=Path)
    parser.add_argument(
        "--granularity",
        default="all",
        choices=["all", "article", "clause"],
        help="Granularity for t-SNE/heatmap: article-level, clause-level (paragraphs/points), or all",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    g = build_graph(args.corpus_dir)
    print(f"Graph: {len(g.nodes)} nodes, {len(g.edges)} edges")

    static_charts(g, args.out)
    print("Wrote static charts to {}/".format(args.out))

    interactive_graphs(g, args.out)
    print("Wrote interactive graphs to {}/".format(args.out))

    levels = {"all": ["article", "clause"], "article": ["article"], "clause": ["clause"]}[args.granularity]
    for level in levels:
        heatmap_chart(g, args.out, level=level)
    print("Wrote heatmaps to {}/".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
