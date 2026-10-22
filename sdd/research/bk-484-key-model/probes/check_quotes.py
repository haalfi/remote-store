"""Check every quote in research-backend-path-authorities.md § 3 against its sources.

For each § 3 subsection, the script takes every double-quoted passage in the
body and the URLs in that subsection's "Sources:" list. It fetches each source
once, reduces it to text (HTML tags dropped, PDFs through ``pdftotext``), and
reports a quote as found when every fragment of it, split at ``…``, occurs in
one source after normalisation: whitespace collapsed, typographic quotes and
dashes folded, Markdown backticks dropped, case kept.

Run from the repo root::

    hatch run python sdd/research/bk-484-key-model/probes/check_quotes.py --cache tmp/quote-cache

It prints one line per quote and a total, and exits 1 if any quote is missing.
Fetched pages go to ``--cache`` (outside the repo's tracked tree) and are
reused on a rerun.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import subprocess
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DOC = Path("sdd/research/research-backend-path-authorities.md")
UA = "Mozilla/5.0 (research quote check; remote-store)"


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag in ("br", "p", "li", "tr", "div", "h1", "h2", "h3", "h4", "pre", "td", "th"):
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


FOLD = str.maketrans(
    {
        # Every quote mark folds to one: a quote nested in a quote is written
        # with the other mark, and translate() maps each character only once.
        "\N{LEFT SINGLE QUOTATION MARK}": "'",
        "\N{RIGHT SINGLE QUOTATION MARK}": "'",
        "\N{LEFT DOUBLE QUOTATION MARK}": "'",
        "\N{RIGHT DOUBLE QUOTATION MARK}": "'",
        '"': "'",
        "\N{EN DASH}": "-",
        "\N{EM DASH}": "-",
        "\N{NO-BREAK SPACE}": " ",
        "\N{NARROW NO-BREAK SPACE}": " ",
        "\N{THIN SPACE}": " ",
        "`": "",
        "*": "",
        "\N{WORD JOINER}": "",
        "\N{ZERO WIDTH SPACE}": "",
        "\N{ZERO WIDTH NO-BREAK SPACE}": "",
    }
)


def norm(text: str) -> str:
    text = html.unescape(text).translate(FOLD)
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str, cache: Path) -> str:
    path = cache / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".txt")
    if path.exists():
        return norm(path.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 -- fixed https sources
        raw = resp.read()
        ctype = resp.headers.get("Content-Type") or ""
    if url.endswith(".pdf") or "pdf" in ctype:
        pdf = path.with_suffix(".pdf")
        pdf.write_bytes(raw)
        text = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout
    elif "html" in ctype or raw.lstrip()[:1] == b"<":
        parser = _Text()
        parser.feed(raw.decode("utf-8", "replace"))
        text = "".join(parser.parts)
    else:
        text = raw.decode("utf-8", "replace")
    text = norm(text)
    path.write_text(text, encoding="utf-8")
    return text


def quotes_in(text: str) -> list[str]:
    """The double-quoted passages of at least 12 characters in ``text``.

    A quote mark inside a code span is a literal character: such spans are
    hidden while quote marks are paired, then put back inside the quotes.
    """
    flat = re.sub(r"\s+", " ", text)
    spans: list[str] = []

    def hide(m: re.Match[str]) -> str:
        if '"' not in m.group(0):
            return m.group(0)
        spans.append(m.group(0))
        return f"\x00{len(spans) - 1}\x00"

    flat = re.sub(r"`[^`]*`", hide, flat)
    return [
        re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], q)
        for q in re.findall(r'"([^"]*)"', flat)
        if len(q) >= 12
    ]


def sections(doc: str) -> list[tuple[str, list[str], list[str]]]:
    """(heading, quotes, urls) for each ### 3.x subsection."""
    out = []
    for block in re.split(r"(?m)^### ", doc)[1:]:
        heading, _, body = block.partition("\n")
        if not heading.startswith("3."):
            continue
        body = body.split("\n---", 1)[0]
        text, _, sources = body.partition("\nSources:")
        urls = re.findall(r"<(https?://[^>]+)>", sources)
        out.append((heading.strip(), quotes_in(text), urls))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the authorities doc's quotes against their sources")
    parser.add_argument("--cache", required=True)
    parser.add_argument("-v", "--verbose", action="store_true", help="also print each quote found")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    doc = DOC.read_text(encoding="utf-8")
    total = missing = 0
    for heading, quotes, urls in sections(doc):
        texts = {}
        for url in urls:
            try:
                texts[url] = fetch(url, cache)
            except Exception as exc:  # noqa: BLE001 -- an unreachable source is reported, not fatal
                print(f"  FETCH-FAIL {url}: {type(exc).__name__}: {str(exc)[:120]}")
        for q in quotes:
            total += 1
            frags = [norm(f) for f in re.split(r"\s*…\s*", q) if norm(f)]
            hit = next((u for u, t in texts.items() if all(f in t for f in frags)), None)
            if hit is None:
                missing += 1
                print(f"MISSING [{heading[:40]}] {q[:110]}")
            elif args.verbose:
                print(f"ok      [{heading[:40]}] {q[:70]}  <- {hit[:70]}")
    print(f"\n{total - missing} of {total} quotes found in their section's sources")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
