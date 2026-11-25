# SPDX-License-Identifier: Apache-2.0
"""Check the built HTML for problems that Sphinx does not report.

Once an HTML build has written every page (``build-finished``), :func:`site_problems` reads the
whole output folder and each problem becomes a Sphinx warning, so ``sphinx-build -W`` (CI's docs
job, Read the Docs with ``fail_on_warning``, the offline build of tests/offline_build.py) fails:

* A numbered figure, table or code block that no link on the site points to: a number nobody
  uses. Refer to it with ``{numref}``, or drop its caption so it is not numbered.
* A caption identified by a running number ("Table 12") instead of its label ("Table
  poe-pairs"), which stable_ids (docs/_ext/stable_ids.py) shows; and "Figure 3" or "Table 12"
  typed in a page's text, which names no item, since no item has a number. Another document's
  table, as in "Table 2-1 of the user manual", is allowed.
* A figure or content table with no caption: it has no number, so the text cannot cite it.
* An image without alternative text. docutils fills a missing ``:alt:`` with the image's path,
  so an ``alt`` that is empty, equals the ``src`` or names an image file counts as missing.
* A docutils error box (``system-message``), an unresolved reference (``problematic``) or a
  ``{contents}`` directive, which Furo draws as a red box from CSS alone.

A light/dark figure pair is one figure by the time the pages are written: theme_figures
(docs/_ext/theme_figures.py) merges the dark twin into the light one before numbering, so the
pair has one identifier, and the light twin's ``:name:`` is the target a ``{numref}`` links to.

It needs the whole site, because a figure on one page may be cited only from another. Run by
hand on a build folder: ``uv run --locked python docs/_ext/html_checks.py docs/_build``.
Adapted from evampire's check_html.py (Apache-2.0).
"""

from __future__ import annotations

import html.parser
import posixpath
import re
import sys
import urllib.parse
from pathlib import Path

# Markup that appears in a page only when something is wrong.
MARKERS = {
    'class="contents':
        "a {contents} directive, which Furo shows as a red error box; remove it (Furo lists "
        "the page contents in the right-hand sidebar)",
    'class="system-message"': "a docutils error or warning box is shown in the page",
    'class="problematic"': "a reference or role could not be resolved",
}  # fmt: skip

IMAGE_SUFFIXES = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp")

#: A caption's identifier that is a running number, such as "Figure 3: " or "Table 1.2 ".
NUMBERED_CAPTION = re.compile(r"\S+\s+\d+(?:\.\d+)*:?")

#: "Figure 3" or "Table 12" in a page's text, not followed by "of" (another document's item).
NUMBER_REF = re.compile(
    r"\b((?:Fig(?:ure)?s?\.?|Tables?|Tab\.)\s+\d+(?:[-.]\d+)*)\b(?![-.]?\d)(?!\s+of\b)"
)

# Elements whose text is not prose a reader is pointed by: links (a {numref} is one), code.
_NOT_PROSE = ("a", "code", "pre", "script", "style")


class PageParser(html.parser.HTMLParser):
    """The links, numbered figures and tables, and images without alt text of one page.

    ``links`` holds every link target except the "link to this" anchors beside headings and
    captions. ``numbered`` holds, for each numbered figure, table or code block, its caption
    number and every ``id`` inside it, because a label can land on the figure, on the table or
    on an element within it. ``missing_alt`` lists the images without alternative text.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.numbered: list[tuple[str, set[str]]] = []
        self.missing_alt: list[str] = []
        self.uncaptioned: list[str] = []
        # The text of the page's main content (the element with role="main": Furo's <article>)
        # outside links and code, in which a hand-typed "Figure 3" is looked for. _main holds
        # the main element's tag and how many elements of that tag are open inside it.
        self.prose: list[str] = []
        self._main: list | None = None
        self._not_prose = 0
        # Open numbered-element candidates, each [kind, ids, caption number]; kind is "figure",
        # "table" (a docutils table: the content tables of a page), "code" or "other" (a table
        # Sphinx draws itself, such as the index). A <div> is pushed as a code block's wrapper,
        # other <div>s as None so the end tags pair up.
        self._open: list[list | None] = []
        self._caption: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "a" and "href" in attrs and "headerlink" not in classes:
            self.links.append(attrs["href"])
        if self._main is None and attrs.get("role") == "main":
            self._main = [tag, 0]
        if self._main is not None and tag == self._main[0]:
            self._main[1] += 1
        if tag in _NOT_PROSE:
            self._not_prose += 1
        elif tag in ("p", "li", "td", "th", "div", "figcaption", "caption", "dd", "dt", "br"):
            self.prose.append(" ")
        if tag == "figure":
            self._open.append(["figure", set(), None])
        elif tag == "table":
            self._open.append(["table" if "docutils" in classes else "other", set(), None])
        elif tag == "div":
            self._open.append(["code", set(), None] if "literal-block-wrapper" in classes else None)
        if "id" in attrs:
            for element in self._open:
                if element is not None:
                    element[1].add(attrs["id"])
        if tag == "span" and "caption-number" in classes:
            self._caption = ""
        if tag == "img":
            alt = (attrs.get("alt") or "").strip()
            src = attrs.get("src") or ""
            if (
                not alt
                or alt == src
                or alt.lower().endswith(IMAGE_SUFFIXES)
                or alt == posixpath.basename(src)
            ):
                self.missing_alt.append(f"image {src}")

    def handle_data(self, data):
        if self._caption is not None:
            self._caption += data
        elif self._main is not None and self._main[1] and not self._not_prose:
            self.prose.append(data)

    def handle_endtag(self, tag):
        if self._main is not None and tag == self._main[0] and self._main[1]:
            self._main[1] -= 1
        if tag in _NOT_PROSE and self._not_prose:
            self._not_prose -= 1
        if tag == "span" and self._caption is not None:
            for element in reversed(self._open):
                if element is not None:
                    element[2] = self._caption.strip()
                    break
            self._caption = None
        if tag in ("figure", "table", "div") and self._open:
            element = self._open.pop()
            if element is None:
                return
            kind, ids, number = element
            if number:
                self.numbered.append((number, ids))
            elif kind in ("figure", "table"):
                label = min(ids) if ids else "with no id"
                self.uncaptioned.append(f"a {kind} ({label})")


def html_pages(root: Path) -> list[Path]:
    """Every page of the build folder ``root``."""
    return sorted(p for p in root.rglob("*.html") if "_static" not in p.relative_to(root).parts)


def page_problems(name: str, text: str) -> list[str]:
    """The markers of :data:`MARKERS` found in one page."""
    return [
        f"{name}: {text.count(marker)} x '{marker}': {meaning}"
        for marker, meaning in MARKERS.items()
        if marker in text
    ]


def site_problems(pages: dict[str, str]) -> list[str]:
    """Every problem of a site given as {path relative to the build folder: HTML}."""
    parsed = {}
    for name, text in pages.items():
        parser = PageParser()
        parser.feed(text)
        parsed[name] = parser
    # Every (page, fragment) pair that some link on the site points to.
    targets = set()
    for name, parser in parsed.items():
        for href in parser.links:
            url = urllib.parse.urlsplit(href)
            if url.scheme or url.netloc or not url.fragment:
                continue
            path = url.path or posixpath.basename(name)
            path = posixpath.normpath(posixpath.join(posixpath.dirname(name), path))
            targets.add((path, url.fragment))
    problems = []
    for name, parser in parsed.items():
        problems += page_problems(name, pages[name])
        for number, ids in parser.numbered:
            if NUMBERED_CAPTION.fullmatch(number):
                problems.append(
                    f"{name}: '{number}' is identified by a running number, not its label; is "
                    "docs/_ext/stable_ids.py in the conf.py extensions?"
                )
            if not any((name, i) in targets for i in ids):
                problems.append(
                    f"{name}: '{number}' is numbered but no page refers to it; add a "
                    f"{{numref}} reference or remove its caption"
                )
        for m in NUMBER_REF.finditer(" ".join("".join(parser.prose).split())):
            problems.append(
                f"{name}: '{m.group(1)}' typed in the text: figures and tables are identified "
                "by their labels, not numbers, so cite the item with {numref}"
            )
        for item in parser.uncaptioned:
            problems.append(
                f"{name}: {item} has no caption, so it has no number to cite; give it a "
                f"caption and a :name: ({{table}} directive for a table)"
            )
        for item in parser.missing_alt:
            problems.append(f"{name}: {item} has no alt text; give the directive an :alt: option")
    return problems


def check_folder(root: Path) -> list[str]:
    """Every problem of the build folder ``root``."""
    return site_problems(
        {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in html_pages(root)}
    )


def _on_build_finished(app, exception):
    if exception is not None or app.builder.format != "html":
        return
    from sphinx.util import logging

    logger = logging.getLogger(__name__)
    for problem in check_folder(Path(app.outdir)):
        logger.warning(problem, type="html_checks")


def setup(app):
    app.connect("build-finished", _on_build_finished)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    if not html_pages(root):
        print(f"error: no HTML files found under {root}")
        return 2
    problems = check_folder(root)
    print("\n".join(problems))
    print(f"checked {len(html_pages(root))} pages, {len(problems)} problem(s) found")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
