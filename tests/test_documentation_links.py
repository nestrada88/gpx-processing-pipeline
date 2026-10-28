"""Offline integrity checks for local documentation links and anchors.

This is deliberately bounded: external HTTP links, rendered HTML links and
runtime CLI examples are not tested here. Markdown code is ignored.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LINK = re.compile(r"(?<!!)\[[^\]\n]*\]\((<[^>]+>|[^)\n]+)\)")
ATX = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(`+)(.*?)\1")


def _without_code(markdown: str) -> str:
    """Exclude fenced and inline-code text from link analysis."""
    kept: list[str] = []
    fence_marker: str | None = None
    for line in markdown.splitlines():
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence_marker is None:
                fence_marker = marker
            elif marker[0] == fence_marker[0] and len(marker) >= len(fence_marker):
                fence_marker = None
            continue
        if fence_marker is not None:
            continue
        kept.append(INLINE_CODE.sub("", line))
    return "\n".join(kept)


def _slug(text: str) -> str:
    """Approximate GitHub heading slugs for ordinary Markdown headings."""
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("`", "").strip().lower()
    text = "".join(
        ch for ch in text
        if ch in {" ", "-", "_"} or ch.isalnum()
        or unicodedata.category(ch).startswith("M")
    )
    return text.replace(" ", "-")


def _headings(markdown: str) -> set[str]:
    """Collect heading IDs, including GitHub-style duplicate suffixes."""
    slugs: set[str] = set()
    counts: Counter[str] = Counter()
    for line in _without_code(markdown).splitlines():
        m = ATX.match(line)
        if not m:
            continue
        slug = _slug(m.group(2))
        if not slug:
            continue
        number = counts[slug]
        counts[slug] += 1
        slugs.add(slug if not number else f"{slug}-{number}")
    return slugs


def test_local_markdown_links_and_anchors() -> None:
    """Every local Markdown link points to an existing file and heading."""
    docs = [ROOT / "README.md", *sorted(DOCS.rglob("*.md"))]
    errors: list[str] = []
    anchors: dict[Path, set[str]] = {}
    for source in docs:
        markdown = _without_code(source.read_text(encoding="utf-8"))
        for match in LINK.finditer(markdown):
            href = match.group(1).strip().strip("<>")
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc or href.startswith("//"):
                continue
            path = unquote(parsed.path)
            anchor = unquote(parsed.fragment)
            dest = (source.parent / path).resolve() if path else source.resolve()
            try:
                dest.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{source.relative_to(ROOT)}: link escapes repository: {href}")
                continue
            if not dest.is_file():
                errors.append(f"{source.relative_to(ROOT)}: missing file: {href}")
                continue
            if anchor and dest.suffix.lower() == ".md":
                if dest not in anchors:
                    anchors[dest] = _headings(dest.read_text(encoding="utf-8"))
                if anchor not in anchors[dest]:
                    errors.append(f"{source.relative_to(ROOT)}: missing heading: {href}")
    assert not errors, "\n" + "\n".join(errors)
