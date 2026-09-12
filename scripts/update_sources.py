#!/usr/bin/env python3
"""Fetch the EU AI Act from the EU Publications Office (CELLAR) and convert to markdown.

Phase 1 of the compliance-agents data layer. Designed to run on a schedule
(GitHub Actions cron) and open a PR when the consolidated text changes.

Sources (validated 2026-09-12):
  - Consolidated text (incl. AI Omnibus, Reg (EU) 2026/1744):
      http://publications.europa.eu/resource/celex/02024R1689-20260727
    NOTE: consolidated renderings omit recitals.
  - Original OJ version (has recitals rct_1..rct_180):
      http://publications.europa.eu/resource/celex/32024R1689

CELLAR requires content negotiation:
  Accept: application/xhtml+xml
  Accept-Language: eng

Markdown structure: legal hierarchy is encoded as headings so sub-units are
addressable and navigable:
  # Article 6 — Title
  ## 1                (paragraph)
  ### (a)             (point)
  #### (i)            (sub-point)

Usage:
    uv run python scripts/update_sources.py [--output-dir data/eu-ai-act] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

CONSOLIDATED_CELEX = "02024R1689-20260727"  # in-force consolidated version (Omnibus applied)
ORIGINAL_CELEX = "32024R1689"
CELLAR = "http://publications.europa.eu/resource/celex"
ATTRIBUTION = "© European Union, http://eur-lex.europa.eu"
HEADERS = {
    "Accept": "application/xhtml+xml",
    "Accept-Language": "eng",
    "User-Agent": "Mozilla/5.0 (compatible; compliance-agents-data/0.1)",
}

# Candidate consolidated dates, newest first. The script tries each until one
# returns 200; update this list when the Commission publishes new consolidated
# versions (e.g. after the next amending regulation).
CONSOLIDATED_CANDIDATES = [
    "02024R1689-20260727",
    "02024R1689-20240712",
]


def fetch_xhtml(celex: str) -> str:
    """Fetch a CELEX document from CELLAR as XHTML."""
    import httpx

    url = f"{CELLAR}/{celex}"
    resp = httpx.get(url, headers=HEADERS, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


# --- tree parsing (stdlib html.parser; handles XHTML entities via convert_charrefs) ---

VOID_TAGS = {"br", "hr", "img", "meta", "link", "input", "col"}


class Element:
    __slots__ = ("tag", "attrs", "parent", "children")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None, parent: "Element | None" = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.parent = parent
        self.children: list[Element | str] = []


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        el = Element(tag, dict(attrs), self.cur)
        self.cur.children.append(el)
        if tag not in VOID_TAGS:
            self.cur = el

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        if data:
            self.cur.children.append(data)


def parse_html(html: str) -> Element:
    builder = TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def classes(el: Element) -> set[str]:
    return set(el.attrs.get("class", "").split())


def iter_elements(el: Element):
    for child in el.children:
        if isinstance(child, Element):
            yield child
            yield from iter_elements(child)


AMENDMENT_RE = re.compile(r"▼[A-Z0-9]+")


def text_of(el: Element) -> str:
    """Normalized text content, skipping modref amendment markers."""
    parts: list[str] = []

    def walk(node: Element) -> None:
        for child in node.children:
            if isinstance(child, str):
                parts.append(child)
            elif "modref" not in classes(child):
                walk(child)

    walk(el)
    return AMENDMENT_RE.sub("", " ".join("".join(parts).split())).strip()


def find_subdivisions(root: Element, prefix: str) -> list[tuple[str, Element]]:
    """Find <div class='eli-subdivision' id='{prefix}_N'> elements."""
    out: list[tuple[str, Element]] = []
    for el in iter_elements(root):
        if el.tag == "div" and "eli-subdivision" in classes(el):
            m = re.fullmatch(rf"{prefix}_(\d+)", el.attrs.get("id", ""))
            if m:
                out.append((m.group(1), el))
    return out


# --- norm rendering: legal hierarchy -> markdown headings ---

def render_points(container: Element, level: int) -> list[str]:
    """Render div.grid-container.grid-list: (a)/(i) markers + content."""
    lines: list[str] = []
    marker = ""
    for child in container.children:
        if not isinstance(child, Element):
            continue
        cls = classes(child)
        if "grid-list-column-1" in cls:
            marker = text_of(child).strip()
        elif "grid-list-column-2" in cls:
            if marker:
                lines += ["", f"{'#' * level} {marker}", ""]
            lines += render_content(child, level + 1)
            marker = ""
    return lines


def render_content(el: Element, level: int) -> list[str]:
    """Render mixed content: text nodes, paragraphs, nested point lists, norm divs."""
    lines: list[str] = []
    for child in el.children:
        if isinstance(child, str):
            t = " ".join(child.split())
            if t:
                lines += [AMENDMENT_RE.sub("", t), ""]
            continue
        cls = classes(child)
        if child.tag == "p":
            t = text_of(child)
            if t:
                lines += [t, ""]
        elif child.tag == "div" and "grid-container" in cls and "grid-list" in cls:
            lines += render_points(child, level)
        elif child.tag == "div" and "norm" in cls:
            lines += render_norm(child, level)
        elif child.tag == "table":
            t = text_of(child)
            if t:
                lines += [t, ""]
    return lines


def render_norm(el: Element, level: int) -> list[str]:
    """Render div.norm: optional span.no-parag number + content."""
    lines: list[str] = []
    num = ""
    for child in el.children:
        if isinstance(child, str):
            continue
        cls = classes(child)
        if child.tag == "span" and "no-parag" in cls:
            num = text_of(child).strip().rstrip(".")
        elif child.tag == "div" and "norm" in cls:
            if num:
                lines += ["", f"{'#' * level} {num}", ""]
                num = ""
            lines += render_content(child, level + 1)
        elif child.tag == "div" and "grid-container" in cls:
            lines += render_points(child, level + 1)
        elif child.tag == "p":
            t = text_of(child)
            if t:
                if num:
                    lines += ["", f"{'#' * level} {num}", ""]
                    num = ""
                lines += [t, ""]
    return lines


def article_markdown(el: Element, unit_id: str) -> str:
    title, subtitle = "", ""
    body: list[str] = []
    for child in el.children:
        if not isinstance(child, Element):
            continue
        cls = classes(child)
        if child.tag == "p" and "title-article-norm" in cls:
            title = text_of(child)
        elif child.tag == "div" and "eli-title" in cls:
            subtitle = text_of(child)
        elif child.tag == "div" and "norm" in cls:
            body += render_norm(child, 2)
        elif child.tag == "div" and "grid-container" in cls and "grid-list" in cls:
            # top-level point lists (e.g. Article 3 definitions)
            body += render_points(child, 2)
        elif child.tag == "p":
            t = text_of(child)
            if t:
                body += [t, ""]
    header = f"# {title or unit_id}"
    if subtitle:
        header += f" — {subtitle}"
    return "\n".join([header, ""] + body).strip() + "\n"


def recital_markdown(el: Element, unit_id: str) -> str:
    num = unit_id.rsplit("-", 1)[-1]
    text = re.sub(r"^\(\d+\)\s*", "", text_of(el))
    return f"# Recital {num}\n\n{text}\n"


def annex_markdown(elements: list[Element]) -> str:
    lines: list[str] = []
    for el in elements:
        cls = classes(el)
        if el.tag == "p" and "title-annex-1" in cls:
            lines += [f"# {text_of(el)}", ""]
        elif el.tag == "p" and "title-annex-2" in cls:
            lines += [f"**{text_of(el)}**", ""]
        elif el.tag == "p" and "title-gr-seq-level-1" in cls:
            lines += ["", f"## {text_of(el)}", ""]
        elif el.tag == "p" and "title-gr-seq-level-2" in cls:
            lines += ["", f"### {text_of(el)}", ""]
        elif el.tag == "div" and "norm" in cls:
            lines += render_norm(el, 3)
        elif el.tag == "div" and "grid-container" in cls:
            lines += render_points(el, 4)
        elif el.tag == "p":
            t = text_of(el)
            if t:
                lines += [t, ""]
        elif el.tag == "table":
            t = text_of(el)
            if t:
                lines += [t, ""]
    return "\n".join(lines).strip() + "\n"


def find_annex_groups(root: Element) -> list[tuple[str, list[Element]]]:
    """Group elements between p.title-annex-1 headings into annex sections."""
    groups: list[tuple[str, list[Element]]] = []
    current: tuple[str, list[Element]] | None = None
    for el in iter_elements(root):
        cls = classes(el)
        if el.tag == "p" and "title-annex-1" in cls:
            if current:
                groups.append(current)
            current = (text_of(el), [])
        elif current is not None:
            current[1].append(el)
    if current:
        groups.append(current)
    return groups


def frontmatter(unit_id: str, kind: str, celex: str, retrieved: str) -> str:
    return (
        "---\n"
        f"id: {unit_id}\n"
        f"type: {kind}\n"
        f"celex: {celex}\n"
        f"source_url: {CELLAR}/{celex}\n"
        f"retrieved: {retrieved}\n"
        f'attribution: "{ATTRIBUTION}"\n'
        "---\n\n"
    )


def write_corpus(articles: list[tuple[str, str]], annexes: list[tuple[str, str]],
                 recitals: list[tuple[str, str]], out_dir: Path, retrieved: str) -> int:
    count = 0
    for kind_dir, items in (
        ("articles", articles),
        ("annexes", annexes),
        ("recitals", recitals),
    ):
        d = out_dir / kind_dir
        d.mkdir(parents=True, exist_ok=True)
        for unit_id, md in items:
            celex = CONSOLIDATED_CELEX if kind_dir != "recitals" else ORIGINAL_CELEX
            kind = {"articles": "article", "annexes": "annex", "recitals": "recital"}[kind_dir]
            path = d / f"{unit_id}.md"
            path.write_text(frontmatter(unit_id, kind, celex, retrieved) + md, encoding="utf-8")
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="data/eu-ai-act", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse but do not write")
    args = parser.parse_args()

    retrieved = dt.date.today().isoformat()

    # 1. Consolidated text -> articles + annexes (current law incl. Omnibus)
    consolidated_html = None
    consolidated_celex = None
    for celex in CONSOLIDATED_CANDIDATES:
        print(f"Trying consolidated {celex} ...")
        try:
            consolidated_html = fetch_xhtml(celex)
            consolidated_celex = celex
            print(f"  OK ({len(consolidated_html):,} bytes)")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  failed: {exc}")
    if consolidated_html is None:
        print("ERROR: no consolidated version available", file=sys.stderr)
        return 1

    # 2. Original OJ -> recitals (consolidated renderings omit them)
    print(f"Fetching original OJ {ORIGINAL_CELEX} for recitals ...")
    original_html = fetch_xhtml(ORIGINAL_CELEX)

    cons_root = parse_html(consolidated_html)
    orig_root = parse_html(original_html)

    articles = [(f"article-{num}", article_markdown(el, f"article-{num}"))
                for num, el in find_subdivisions(cons_root, "art")]
    recitals = [(f"recital-{num}", recital_markdown(el, f"recital-{num}"))
                for num, el in find_subdivisions(orig_root, "rct")]
    annexes = [(name.lower().replace(" ", "-"), annex_markdown(els))
               for name, els in find_annex_groups(cons_root)]

    print(f"Parsed: articles={len(articles)} annexes={len(annexes)} recitals={len(recitals)}")

    if not articles or not recitals:
        print("ERROR: parsing failed — CELLAR layout may have changed.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("Dry run: not writing files.")
        return 0

    n = write_corpus(articles, annexes, recitals, args.output_dir, retrieved)
    print(f"Wrote {n} files to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
