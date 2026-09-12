"""Canonical graph model for the EU AI Act corpus.

Parses `data/eu-ai-act/` markdown (with YAML frontmatter and heading-based
legal hierarchy) into nodes and edges. Backend-agnostic: NetworkX, LLMwiki,
and Neo4j adapters all consume this.

Node hierarchy (from markdown headings):
    # Article 6 — Title          -> Article node
    ## 1                         -> Paragraph node (article-6.1)
    ### (a)                      -> Point node (article-6.1.a)
    #### (i)                     -> Sub-point node (article-6.1.a.i)

Article 3 definitions ('term' means ...) become Definition nodes linked to
Actor nodes for the five regulated roles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# --- frontmatter parsing (no external YAML dep needed for our simple schema) ---

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
DEFINITION_RE = re.compile(r"‘([^’]{2,60})’\s+means\s+([^;]+);")
ARTICLE_REF_RE = re.compile(r"Article\s+(\d{1,3})([a-z])?(?:\((\d+)\))?")
ANNEX_REF_RE = re.compile(r"Annex\s+([IVX]{1,4})\b")
SHALL_RE = re.compile(r"([^.]*\bshall\b[^.]*\.)", re.DOTALL)

# Article 3 defines ~70 terms; these map to Actor nodes.
ACTOR_TERMS = {
    "provider": "actor-provider",
    "deployer": "actor-deployer",
    "importer": "actor-importer",
    "distributor": "actor-distributor",
    "product manufacturer": "actor-product-manufacturer",
    "authorised representative": "actor-authorised-representative",
}

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse simple `key: value` frontmatter. Returns (meta, body)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"')
    return meta, text[m.end():]


@dataclass
class Node:
    id: str
    type: str
    title: str = ""
    content: str = ""
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    kind: str
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> Node:
        if node.id not in self.nodes:
            self.nodes[node.id] = node
        return self.nodes[node.id]

    def add_edge(self, src: str, dst: str, kind: str, **attrs: str) -> None:
        if src == dst:
            return
        self.edges.append(Edge(src=src, dst=dst, kind=kind, attrs=attrs))


def _norm_annex(num: str) -> str:
    return f"annex-{num.lower()}"


def _norm_article(num: str, letter: str | None) -> str:
    return f"article-{num}{letter or ''}".lower()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load_units(corpus_dir: Path) -> list[tuple[dict[str, str], str, Path]]:
    """Load all corpus markdown files. Returns [(meta, body, path)]."""
    units = []
    for sub in ("articles", "recitals", "annexes", "guidance", "amendments"):
        d = corpus_dir / sub
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            units.append((meta, body, path))
    return units


def split_headings(body: str) -> list[tuple[int, str, str]]:
    """Split body into (level, heading, text) sections. Text runs until next heading."""
    sections: list[tuple[int, str, str]] = []
    current: tuple[int, str, list[str]] | None = None
    for line in body.splitlines():
        m = HEADING_RE.match(line)
        if m:
            if current:
                sections.append((current[0], current[1], "\n".join(current[2]).strip()))
            current = (len(m.group(1)), m.group(2).strip(), [])
        elif current:
            current[2].append(line)
    if current:
        sections.append((current[0], current[1], "\n".join(current[2]).strip()))
    return sections


def build_graph(corpus_dir: Path) -> Graph:
    """Build the canonical graph from the corpus."""
    g = Graph()
    units = load_units(corpus_dir)

    # Pass 1: unit nodes + hierarchical sub-unit nodes from headings
    for meta, body, path in units:
        uid = meta.get("id") or path.stem
        # Normalize unit type: article->Article, recital->Recital, annex->Annex
        raw_type = meta.get("type", path.parent.name.rstrip("s"))
        utype = {"article": "Article", "recital": "Recital", "annex": "Annex"}.get(raw_type, raw_type.capitalize())
        sections = split_headings(body)
        title = sections[0][1] if sections else uid
        g.add_node(Node(id=uid, type=utype, title=title, content=body.strip(), attrs=dict(meta)))

        if uid.startswith("article-") or uid.startswith("annex-"):
            # Track hierarchy: (level, id) stack for containment edges
            stack: list[tuple[int, str]] = [(1, uid)]
            for level, heading, text in sections[1:]:
                # Determine sub-unit id: article-6.1 / article-6.1.a / article-6.1.a.i
                h = heading.strip()
                parent_id = stack[-1][1] if stack else uid
                if level == 2:
                    sub_id = f"{uid}.{_slug(h)}"
                elif level == 3:
                    sub_id = f"{parent_id}.{_slug(h)}"
                else:
                    sub_id = f"{parent_id}.{_slug(h)}"
                sub_type = {2: "Paragraph", 3: "Point"}.get(level, "SubPoint")
                g.add_node(Node(id=sub_id, type=sub_type, title=h, content=text))
                g.add_edge(parent_id, sub_id, "HAS_SUBUNIT")
                # maintain stack: pop entries with level >= current
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, sub_id))

    # Pass 2: definitions (Article 3) and actors
    for meta, body, path in units:
        uid = meta.get("id")
        if uid != "article-3":
            continue
        for term, definition in DEFINITION_RE.findall(body):
            term_clean = term.strip().lower()
            def_id = f"def-{_slug(term_clean)}"
            g.add_node(Node(id=def_id, type="Definition", title=term_clean, content=definition.strip()))
            g.add_edge(uid, def_id, "DEFINES")
            if term_clean in ACTOR_TERMS:
                actor_id = ACTOR_TERMS[term_clean]
                g.add_node(Node(id=actor_id, type="Actor", title=term_clean))
                g.add_edge(def_id, actor_id, "IS_ROLE_OF")

    # Pass 3: sub-unit edges (definition usage, clause-level cross-references),
    # obligations, risk tiers. Direct references only.
    for meta, body, path in units:
        uid = meta.get("id")
        if not uid:
            continue

        # Collect sub-units for this unit (article-6.1, article-6.1.a, ...)
        sub_units = [n for n in g.nodes.values() if n.id.startswith(uid + ".")]
        # Map sub-unit -> its root article/annex id
        def root_of(sub_id: str) -> str:
            return uid

        for sub in sub_units:
            text = sub.content or ""

            # 3a. Definition usage: clause/sub-clause uses a term defined in
            # Article 3. Terms appear quoted ('AI system') or unquoted in
            # running text — match as a word-boundary phrase.
            defs_text = next((n.content for n in g.nodes.values() if n.id == "article-3"), "")
            for term, _definition in DEFINITION_RE.findall(defs_text):
                term_clean = term.strip().lower()
                pattern = re.compile(r"['\u2018\u2019\"]?" + re.escape(term_clean) + r"['\u2018\u2019\"]?", re.IGNORECASE)
                if pattern.search(text):
                    def_id = f"def-{_slug(term_clean)}"
                    if def_id in g.nodes:
                        g.add_edge(sub.id, def_id, "USES_DEFINITION")

            # 3b. Clause-level cross-references (direct only): "Article X(n)",
            # "point (a) of Article X", "paragraph n of this Article", "Annex X".
            for num, letter, _para in ARTICLE_REF_RE.findall(text):
                ref_id = _norm_article(num, letter)
                if ref_id != uid and ref_id in g.nodes:
                    g.add_edge(sub.id, ref_id, "REFERENCES")

            for num in ANNEX_REF_RE.findall(text):
                ref_id = _norm_annex(num)
                if ref_id in g.nodes:
                    g.add_edge(sub.id, ref_id, "REFERENCES")

        # Unit-level references (article -> article/annex) — keep for rollup
        body = "\n".join(n.content for n in sub_units) if sub_units else ""
        full_text = body or (g.nodes[uid].content if uid in g.nodes else "")

        # Article references
        for num, letter, _para in ARTICLE_REF_RE.findall(full_text):
            ref_id = _norm_article(num, letter)
            if ref_id != uid and ref_id in g.nodes:
                g.add_edge(uid, ref_id, "REFERENCES")

        # Annex references
        for num in ANNEX_REF_RE.findall(full_text):
            ref_id = _norm_annex(num)
            if ref_id != uid and ref_id in g.nodes:
                g.add_edge(uid, ref_id, "REFERENCES")

        # Obligations: sentences with "shall" in articles
        if uid.startswith("article-"):
            for i, sent in enumerate(SHALL_RE.findall(full_text)):
                sent_clean = " ".join(sent.split())
                sent_clean = re.sub(r"^#{1,6}\s+", "", sent_clean)  # strip heading markers
                if len(sent_clean) < 20:
                    continue
                ob_id = f"obligation-{uid}-{i}"
                actor = next((a for t, a in ACTOR_TERMS.items() if t in sent_clean.lower()), "")
                g.add_node(Node(id=ob_id, type="Obligation", title=sent_clean[:80], content=sent_clean))
                g.add_edge(uid, ob_id, "HAS_OBLIGATION")
                if actor:
                    g.add_edge(ob_id, actor, "IMPOSES_ON")

        # Risk tiers
        low = (g.nodes[uid].content if uid in g.nodes else "").lower()
        if uid == "article-5" or "prohibited" in low[:200]:
            g.add_node(Node(id="risk-unacceptable", type="RiskTier", title="unacceptable risk"))
            g.add_edge(uid, "risk-unacceptable", "CLASSIFIES_AS")
        if "high-risk" in low:
            g.add_node(Node(id="risk-high", type="RiskTier", title="high risk"))
            g.add_edge(uid, "risk-high", "CLASSIFIES_AS")

    # Pass 4: recital links — INTERPRETS (explicit article citations) and
    # USES_DEFINITION (recitals use Art 3 terms heavily, e.g. recital 19
    # defines the scope of 'publicly accessible space').
    defs_text = next((n.content for n in g.nodes.values() if n.id == "article-3"), "")
    defined_terms = [t.strip().lower() for t, _d in DEFINITION_RE.findall(defs_text)]
    for meta, body, path in units:
        uid = meta.get("id")
        if not uid or not uid.startswith("recital-"):
            continue
        for num, letter, _para in ARTICLE_REF_RE.findall(body):
            ref_id = _norm_article(num, letter)
            if ref_id in g.nodes:
                g.add_edge(uid, ref_id, "INTERPRETS")
        for term in defined_terms:
            pattern = re.compile(r"['\u2018\u2019\"]?" + re.escape(term) + r"['\u2018\u2019\"]?", re.IGNORECASE)
            if pattern.search(body):
                def_id = f"def-{_slug(term)}"
                if def_id in g.nodes:
                    g.add_edge(uid, def_id, "USES_DEFINITION")

    apply_edge_weights(g)
    return g


# Edge strength scheme: base weight per kind, reflecting how strongly the
# edge implies semantic dependency. Direct citations are strongest.
EDGE_BASE_WEIGHTS: dict[str, float] = {
    "REFERENCES": 3.0,        # direct citation — strongest signal
    "USES_DEFINITION": 2.0,   # uses an Art 3 term — strong semantic dependency
    "IMPOSES_ON": 2.5,        # obligation binding an actor
    "INTERPRETS": 1.5,        # recital interpretation — persuasive, not binding
    "DEFINES": 2.0,           # article defines a term
    "IS_ROLE_OF": 2.0,        # definition maps to an actor role
    "CLASSIFIES_AS": 1.5,     # risk-tier classification
    "HAS_OBLIGATION": 1.5,    # article contains obligation
    "HAS_SUBUNIT": 1.0,       # structural containment — weakest
}


def apply_edge_weights(g: Graph) -> None:
    """Assign weights to all edges: base weight per kind, boosted by multiplicity.

    Repeated references (unit A cites unit B in several clauses) accumulate:
    weight = base + (count - 1). Stored on the edge attrs.
    """
    counts: dict[tuple[str, str, str], int] = {}
    for e in g.edges:
        counts[(e.src, e.dst, e.kind)] = counts.get((e.src, e.dst, e.kind), 0) + 1

    seen: set[tuple[str, str, str]] = set()
    weighted: list[Edge] = []
    for e in g.edges:
        key = (e.src, e.dst, e.kind)
        if key in seen:
            continue  # deduplicate repeated edges, keep one with accumulated weight
        seen.add(key)
        base = EDGE_BASE_WEIGHTS.get(e.kind, 1.0)
        e.attrs["weight"] = f"{base + (counts[key] - 1):.1f}"
        weighted.append(e)
    g.edges = weighted


def graph_stats(g: Graph) -> dict[str, int]:
    """Node counts by type + total edges."""
    by_type: dict[str, int] = {}
    for n in g.nodes.values():
        by_type[n.type] = by_type.get(n.type, 0) + 1
    by_type["EDGES"] = len(g.edges)
    return by_type
