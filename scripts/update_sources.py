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

Usage:
    uv run python scripts/update_sources.py [--output-dir data/eu-ai-act] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
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


def html_to_markdown(html: str) -> str:
    """Convert XHTML to markdown via html2text."""
    import html2text

    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_images = True
    h.ignore_links = False
    h.mark_code = False
    return h.handle(html)


def extract_divs(html: str, prefix: str, unit_prefix: str) -> list[tuple[str, str]]:
    """Extract <div class='eli-subdivision' id='{prefix}_N'>...</div> blocks.

    Returns [(unit_id, html_fragment)]. Uses balanced-div scanning because
    nested divs make naive regex splitting unreliable. Unit IDs use
    {unit_prefix}-N (e.g. article-5, recital-42).
    """
    units: list[tuple[str, str]] = []
    for m in re.finditer(rf'<div class="eli-subdivision" id="{prefix}_(\d+)">', html):
        start = m.start()
        depth = 0
        pos = start
        for tag in re.finditer(r"<div\b|</div>", html[start:]):
            if tag.group(0) == "<div":
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    pos = start + tag.end()
                    break
        units.append((f"{unit_prefix}-{m.group(1)}", html[start:pos]))
    return units


def extract_annexes(html: str) -> list[tuple[str, str]]:
    """Extract annex sections delimited by <hr class='separator-annex'/>."""
    marker = '<hr class="separator-annex"/>'
    title_re = re.compile(r'<p class="title-annex-1"[^>]*>\s*ANNEX\s+([IVX]+)\s*</p>')
    units: list[tuple[str, str]] = []

    positions = [m.start() for m in re.finditer(re.escape(marker), html)]
    # Annex content runs from its separator to the next separator (or doc end).
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(html)
        chunk = html[pos:end]
        tm = title_re.search(chunk)
        if not tm:
            continue
        # Drop the leading separator so files start with the annex title.
        chunk = chunk.replace(marker, "", 1)
        units.append((f"annex-{tm.group(1).lower()}", chunk))
    return units


def strip_amendment_markers(md: str) -> str:
    """Remove CELLAR amendment markers (▼M1, ▼B, ▼C1 ...) and modref remnants."""
    # modref links render as: [▼M1](url "32026R1744: INSERTED") or bare ▼M1
    md = re.sub(r"\[▼[A-Z0-9]+\]\([^)]*\s*\"[^\"]*\"\)", "", md)
    md = re.sub(r"\[▼[A-Z0-9]+\]\([^)]*\)", "", md)
    md = re.sub(r"▼[A-Z0-9]+", "", md)
    # leftover quoted titles like "32026R1744: INSERTED")
    md = re.sub(r"\"[0-9R/]+:\s*(INSERTED|REPLACED|AMENDED|DELETED)[^\"]*\"\)?", "", md)
    return md


def fragment_to_markdown(fragment: str) -> str:
    md = html_to_markdown(fragment)
    md = strip_amendment_markers(md)
    # collapse the "1\. \n\n" paragraph-number artifacts from CELLAR tables
    md = re.sub(r"^(\d+\\\.)\s*$", r"**\1**", md, flags=re.MULTILINE)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def frontmatter(unit_id: str, kind: str, celex: str, retrieved: str, extra: dict[str, str] | None = None) -> str:
    lines = [
        "---",
        f"id: {unit_id}",
        f"type: {kind}",
        f"celex: {celex}",
        f"source_url: {CELLAR}/{celex}",
        f"retrieved: {retrieved}",
        f'attribution: "{ATTRIBUTION}"',
    ]
    for k, v in (extra or {}).items():
        lines.append(f"{k}: {v}")
    lines += ["---", ""]
    return "\n".join(lines)


def write_units(units: list[tuple[str, str]], out_dir: Path, kind: str, celex: str, retrieved: str) -> int:
    kind_dir = out_dir / f"{kind}s" if kind != "annex" else out_dir / "annexes"
    kind_dir.mkdir(parents=True, exist_ok=True)
    for unit_id, fragment in units:
        md = fragment_to_markdown(fragment)
        path = kind_dir / f"{unit_id}.md"
        path.write_text(frontmatter(unit_id, kind, celex, retrieved) + md + "\n", encoding="utf-8")
    return len(units)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="data/eu-ai-act", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse but do not write")
    args = parser.parse_args()

    retrieved = dt.date.today().isoformat()

    # 1. Consolidated text -> articles + annexes (current law incl. Omnibus)
    consolidated = None
    for celex in CONSOLIDATED_CANDIDATES:
        print(f"Trying consolidated {celex} ...")
        try:
            consolidated = fetch_xhtml(celex)
            print(f"  OK ({len(consolidated):,} bytes)")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  failed: {exc}")
    if consolidated is None:
        print("ERROR: no consolidated version available", file=sys.stderr)
        return 1

    # 2. Original OJ -> recitals (consolidated renderings omit them)
    print(f"Fetching original OJ {ORIGINAL_CELEX} for recitals ...")
    original = fetch_xhtml(ORIGINAL_CELEX)

    articles = extract_divs(consolidated, "art", "article")
    annexes = extract_annexes(consolidated)
    recitals = extract_divs(original, "rct", "recital")
    print(f"Parsed: articles={len(articles)} annexes={len(annexes)} recitals={len(recitals)}")

    if not articles or not recitals:
        print("ERROR: parsing failed — CELLAR layout may have changed.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("Dry run: not writing files.")
        return 0

    out = args.output_dir
    n = 0
    n += write_units(articles, out, "article", CONSOLIDATED_CELEX, retrieved)
    n += write_units(annexes, out, "annex", CONSOLIDATED_CELEX, retrieved)
    n += write_units(recitals, out, "recital", ORIGINAL_CELEX, retrieved)
    print(f"Wrote {n} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
