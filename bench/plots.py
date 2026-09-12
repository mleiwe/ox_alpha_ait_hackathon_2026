"""Benchmark performance charts — static PNGs for REPORT.md + the demo.

Reads the JSON results written by `bench/run.py --out` and renders:

  1. bench/viz/bench-mrr.png          — MRR@k by strategy (grouped bars, per-category)
  2. bench/viz/bench-recall.png       — recall@k by strategy
  3. bench/viz/bench-chain.png        — chain recall on multi-hop (where H3 lives)
  4. bench/viz/bench-latency.png      — latency budget (<1s/query line)
  5. bench/viz/bench-reasoning.png    — reasoning tier: hop coverage / distractor
                                        resistance / trace validity per primitive
  6. bench/viz/bench-curves.png       — recall@k curves over k ∈ {3, 5, 10}

Style matches the existing viz (magma palette, clean spines).

Usage:
    uv run bench/run.py --all --gold bench/gold/ --out bench/results_retrieval.json
    uv run bench/run.py --all --gold bench/gold/reasoning/ --mode reasoning --out bench/results_reasoning.json
    uv run bench/plots.py --retrieval bench/results_retrieval.json --reasoning bench/results_reasoning.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BENCH_DIR = Path(__file__).parent
VIZ_DIR = BENCH_DIR / "viz"

# magma-derived palette, consistent with the existing heatmap/legend viz
PALETTE = ["#1b1053", "#4f127b", "#822681", "#b73779", "#e75263", "#fc8961", "#fec287"]
BUDGET_S = 1.0  # plan: latency budget <1s/query


def _style(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


def _short(name: str) -> str:
    """4-graphrag -> 4 GraphRAG ; 4u-graphrag-uniform -> 4u GraphRAG(unif)"""
    labels = {
        "0-substring": "0 substring",
        "1-bm25": "1 BM25",
        "2-tfidf": "2 TF-IDF",
        "4-graphrag": "4 GraphRAG",
        "4u-graphrag-uniform": "4u GraphRAG(unif)",
    }
    return labels.get(name, name)


def plot_mrr(retrieval: list[dict], out: Path) -> None:
    """MRR@k by strategy, broken down by category (grouped bars)."""
    cats = sorted({c for r in retrieval for c in r["per_category"]})
    strategies = [r["strategy"] for r in retrieval]
    x = np.arange(len(cats))
    width = 0.8 / len(strategies)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, r in enumerate(retrieval):
        vals = [r["per_category"].get(c, {}).get("mrr", 0.0) for c in cats]
        bars = ax.bar(x + i * width, vals, width, label=_short(r["strategy"]), color=PALETTE[i % len(PALETTE)])
        ax.bar_label(bars, fmt="%.2f", fontsize=7, padding=2)
    ax.set_xticks(x + width * (len(strategies) - 1) / 2)
    ax.set_xticklabels(cats)
    ax.set_ylabel(f"MRR@{retrieval[0]['k']}")
    ax.set_title("Retrieval quality by strategy and category (higher is better)")
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 1.0)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_recall(retrieval: list[dict], out: Path) -> None:
    """Recall@k by strategy (grouped bars)."""
    cats = sorted({c for r in retrieval for c in r["per_category"]})
    strategies = [r["strategy"] for r in retrieval]
    x = np.arange(len(cats))
    width = 0.8 / len(strategies)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, r in enumerate(retrieval):
        vals = [r["per_category"].get(c, {}).get("recall", 0.0) for c in cats]
        bars = ax.bar(x + i * width, vals, width, label=_short(r["strategy"]), color=PALETTE[i % len(PALETTE)])
        ax.bar_label(bars, fmt="%.2f", fontsize=7, padding=2)
    ax.set_xticks(x + width * (len(strategies) - 1) / 2)
    ax.set_xticklabels(cats)
    ax.set_ylabel(f"recall@{retrieval[0]['k']}")
    ax.set_title("Recall by strategy and category (higher is better)")
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 1.0)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_chain(retrieval: list[dict], out: Path) -> None:
    """Chain recall on multi-hop — where H3 lives."""
    strategies = [r["strategy"] for r in retrieval]
    vals = [r["per_category"].get("multi-hop", {}).get("chain_recall", 0.0) for r in retrieval]

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    bars = ax.bar([_short(s) for s in strategies], vals, color=PALETTE[: len(strategies)])
    ax.bar_label(bars, fmt="%.2f", fontsize=9, padding=2)
    ax.set_ylabel("chain recall (multi-hop)")
    ax.set_title("H3: does the strategy deliver the whole chain?\n(fraction of multi-hop items with ALL expected units retrieved)")
    ax.set_ylim(0, 1.0)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_latency(retrieval: list[dict], out: Path) -> None:
    """Latency budget: mean + p95 per strategy vs the <1s budget."""
    strategies = [r["strategy"] for r in retrieval]
    mean = [r["latency_mean_s"] * 1000 for r in retrieval]
    p95 = [r["latency_p95_s"] * 1000 for r in retrieval]
    x = np.arange(len(strategies))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    b1 = ax.bar(x - width / 2, mean, width, label="mean", color=PALETTE[2])
    b2 = ax.bar(x + width / 2, p95, width, label="p95", color=PALETTE[4])
    ax.bar_label(b1, fmt="%.0fms", fontsize=8, padding=2)
    ax.bar_label(b2, fmt="%.0fms", fontsize=8, padding=2)
    ax.axhline(BUDGET_S * 1000, color="#b73779", linestyle="--", linewidth=1.2)
    ax.text(len(strategies) - 0.5, BUDGET_S * 1000 + 8, "budget <1s/query", color="#b73779", fontsize=8, ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([_short(s) for s in strategies])
    ax.set_ylabel("latency (ms)")
    ax.set_title("Query latency vs IDE-agent budget (lower is better)")
    ax.legend(frameon=False, fontsize=9)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_reasoning(reasoning: list[dict], out: Path) -> None:
    """Reasoning tier: hop coverage / distractor resistance / trace validity per primitive."""
    signals = ["hop_coverage", "distractor_resistance", "trace_validity"]
    signal_labels = ["hop coverage", "distractor resistance", "trace validity"]
    primitives = sorted({c for r in reasoning for c in r["per_category"]})
    strategies = [r["strategy"] for r in reasoning]

    fig, axes = plt.subplots(1, len(reasoning), figsize=(7 * len(reasoning), 5.5), sharey=True, squeeze=False)
    for j, r in enumerate(reasoning):
        ax = axes[0][j]
        x = np.arange(len(primitives))
        width = 0.8 / len(signals)
        for i, sig in enumerate(signals):
            vals = [r["per_category"].get(p, {}).get(sig, 0.0) for p in primitives]
            ax.bar(x + i * width, vals, width, label=signal_labels[i], color=PALETTE[i * 2 % len(PALETTE)])
        ax.set_xticks(x + width)
        ax.set_xticklabels([p.replace("-", "\n") for p in primitives], fontsize=7)
        ax.set_title(_short(r["strategy"]), fontsize=11)
        ax.set_ylim(0, 1.0)
        _style(ax)
    axes[0][0].set_ylabel("signal (0-1)")
    axes[0][0].legend(frameon=False, fontsize=9, loc="upper right")
    fig.suptitle("Reasoning tier per composition primitive (H5: does the strategy walk the chain?)", fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_curves(curves: dict[str, list[dict]], out: Path) -> None:
    """Recall@k curves over k ∈ {3, 5, 10} — reported, never tuned."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ks = sorted({k for runs in curves.values() for r in runs for k in [r["k"]]})
    for i, (strategy, runs) in enumerate(sorted(curves.items())):
        runs_sorted = sorted(runs, key=lambda r: r["k"])
        ax.plot([r["k"] for r in runs_sorted], [r["recall_at_k"] for r in runs_sorted], marker="o", label=_short(strategy), color=PALETTE[i % len(PALETTE)])
    ax.set_xticks([3, 5, 10])
    ax.set_xlabel("k")
    ax.set_ylabel("recall@k")
    ax.set_title("Recall@k curves (same k across strategies — never tuned)")
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 1.0)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def contact_sheet(charts: list[Path], out: Path, width: int = 900) -> None:
    """Stitch charts into one PNG (harness-friendly single-image review)."""
    from PIL import Image

    imgs = [Image.open(p) for p in charts if p.exists()]
    if not imgs:
        return
    scaled = []
    for im in imgs:
        h = int(im.height * width / im.width)
        scaled.append(im.resize((width, h)))
    per_row = 3
    rows = [scaled[i:i + per_row] for i in range(0, len(scaled), per_row)]
    row_h = [max(im.height for im in r) for r in rows]
    total_w = width * per_row + 10 * (per_row + 1)
    total_h = sum(row_h) + 20 * (len(rows) + 1)
    sheet = Image.new("RGB", (total_w, total_h), "white")
    y = 20
    for r, rh in zip(rows, row_h):
        x = 10
        for im in r:
            sheet.paste(im, (x, y))
            x += width + 10
        y += rh + 20
    sheet.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval", type=Path, help="retrieval results JSON from bench/run.py --out")
    parser.add_argument("--reasoning", type=Path, help="reasoning results JSON from bench/run.py --out")
    parser.add_argument("--curves", type=Path, help="curves JSON: {strategy: [results at k=3,5,10]}")
    parser.add_argument("--out-dir", type=Path, default=VIZ_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    if args.retrieval:
        retrieval = json.loads(args.retrieval.read_text())
        plot_mrr(retrieval, args.out_dir / "bench-mrr.png")
        written.append("bench-mrr.png")
        plot_recall(retrieval, args.out_dir / "bench-recall.png")
        written.append("bench-recall.png")
        plot_chain(retrieval, args.out_dir / "bench-chain.png")
        written.append("bench-chain.png")
        plot_latency(retrieval, args.out_dir / "bench-latency.png")
        written.append("bench-latency.png")

    if args.reasoning:
        reasoning = json.loads(args.reasoning.read_text())
        plot_reasoning(reasoning, args.out_dir / "bench-reasoning.png")
        written.append("bench-reasoning.png")

    if args.curves:
        curves = json.loads(args.curves.read_text())
        plot_curves(curves, args.out_dir / "bench-curves.png")
        written.append("bench-curves.png")

    # single-image contact sheet of everything written (harness-friendly review)
    if written:
        sheet = args.out_dir / "bench-contact-sheet.png"
        contact_sheet([args.out_dir / w for w in written], sheet)
        written.append(sheet.name)

    print(f"wrote {len(written)} charts -> {args.out_dir}:")
    for w in written:
        print(f"  {args.out_dir / w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
