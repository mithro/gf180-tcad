# SPDX-License-Identifier: Apache-2.0
"""Mark table cells that hold one number with the class ``num``.

docs/_static/narrow.css keeps such a cell on one line on a narrow screen, so a value like
7.271e-11 never breaks at its sign (spec §10.3: no number broken across lines at 400 px).
"""

import re

from docutils import nodes

# One number: an optional sign or comparison, digits with "." or ",", an optional exponent and %.
NUMBER = re.compile(r"^[−+\-–~≈≥≤<>]?\s?\d[\d.,]*(?:[eE][−+\-]?\d+)?\s?%?$")


def mark_number_cells(app, doctree, docname):
    for entry in doctree.findall(nodes.entry):
        if NUMBER.match(entry.astext().strip()):
            entry["classes"].append("num")


def setup(app):
    app.connect("doctree-resolved", mark_number_cells)
    app.add_css_file("narrow.css")
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
