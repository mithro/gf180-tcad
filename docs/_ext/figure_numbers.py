# SPDX-License-Identifier: Apache-2.0
"""Number the figures of each page from 1, counting a light and dark twin pair as one figure.

Sphinx's ``numfig`` counts every captioned figure across the whole site, and it counts the
``only-light`` and ``only-dark`` twins of a figure separately, though a reader sees one of the
two. A reader of a page would then see figure numbers that skip. After Sphinx assigns its
numbers, :func:`renumber` replaces them: per page, from 1, in page order, with an ``only-dark``
figure that follows an ``only-light`` one taking the same number. ``{numref}`` reads the same
table, so a reference prints the number the reader sees.
"""

from docutils import nodes


def page_numbers(figures: list[tuple[str, list[str]]]) -> dict[str, int]:
    """Figure id to number, for one page's figures given in page order as (id, classes)."""
    out: dict[str, int] = {}
    n = 0
    previous_light = False
    for fig_id, classes in figures:
        if "only-dark" in classes and previous_light:
            out[fig_id] = n
            previous_light = False
            continue
        n += 1
        out[fig_id] = n
        previous_light = "only-light" in classes
    return out


def renumber(app, env):
    changed = []
    for docname, types in env.toc_fignumbers.items():
        if "figure" not in types:
            continue
        doctree = env.get_doctree(docname)
        figures = [
            (f["ids"][0], list(f["classes"])) for f in doctree.findall(nodes.figure) if f["ids"]
        ]
        numbered = [(i, c) for i, c in figures if i in types["figure"]]
        new = {i: (n,) for i, n in page_numbers(numbered).items()}
        if new != types["figure"]:
            types["figure"] = new
            changed.append(docname)
    return changed


def setup(app):
    # After sphinx's own TocTreeCollector (priority 500) has assigned the site-wide numbers.
    app.connect("env-get-updated", renumber, priority=900)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
