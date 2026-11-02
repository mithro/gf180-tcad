# SPDX-License-Identifier: Apache-2.0
"""Keep a number and its unit on one line in the built pages (issue #119).

``gf180tcad.explain.numbers.format_value`` already joins the values it prints with a
non-breaking space. This extension does the same for the values typed by hand in a page and
for those the generated result pages print: in each text node outside code and math, the
space between a digit and a unit becomes U+00A0, and the "/" inside a compound unit such as
fF/µm² is followed by U+2060 (word joiner), so the browser has no place to break.
"""

import re

from docutils import nodes
from sphinx.transforms import SphinxTransform

NBSP = "\u00a0"
WORD_JOINER = "\u2060"
# Units that follow a number, longest alternatives first. A letter after the unit means the
# match is part of a longer word, so the space stays.
_UNIT = r"(?:%|[kmµnp]?V|eV|K|[fpnµm]?F|[µnpm]?A|[kM]?Ω|nm|µm|um|cm|mm|ps|ns|µs|ms|Hz)"
_VALUE_UNIT = re.compile(rf"(?<=[\d)]) (?={_UNIT}(?![\w]))")
_SLASH = re.compile(r"(?<![\w])([fpnµmkM]?[FVA])/(?=[µcnmu])")
_SKIP = (
    nodes.literal,
    nodes.literal_block,
    nodes.math,
    nodes.math_block,
    nodes.raw,
    nodes.FixedTextElement,
)


def join_units(text: str) -> str:
    """``text`` with the value-unit spaces made non-breaking and word joiners after unit slashes."""
    text = _VALUE_UNIT.sub(NBSP, text)
    return _SLASH.sub(lambda m: m.group(1) + "/" + WORD_JOINER, text)


class JoinUnits(SphinxTransform):
    """Runs while the page is read, before the title collector copies the titles, so the
    table of contents, the sidebar and the page titles carry the joined text too."""

    default_priority = 100

    def apply(self, **kwargs):
        join_doctree(None, self.document, self.env.docname)


def join_doctree(app, doctree, docname):
    for node in list(doctree.findall(nodes.Text)):
        if node.parent is None or isinstance(node.parent, _SKIP):
            continue
        new = join_units(node.astext())
        if new != node.astext():
            node.parent.replace(node, nodes.Text(new))


def setup(app):
    app.add_transform(JoinUnits)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "2"}
