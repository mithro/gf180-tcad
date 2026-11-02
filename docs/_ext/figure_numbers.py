# SPDX-License-Identifier: Apache-2.0
"""Number only named figures, from 1 on each page.

A page names the light twin of a figure (``:name:``) and refers to it with ``{numref}``. Sphinx
numbers every captioned figure that has an id, and MyST gives unnamed figures one, so the dark
twin would take a number of its own and the reader would see every other number. Sphinx also
counts across the whole site when the toctree is not numbered. Once Sphinx has assigned its
numbers, this extension drops the unnamed figures from them and renumbers the rest of each page
from 1. (The ids stay: the HTML writer requires one on every figure when numfig is on.)
"""

from docutils import nodes


def unnamed_figure_ids(doctree) -> set[str]:
    """The ids of the figures of ``doctree`` that have no ``:name:``."""
    return {i for fig in doctree.findall(nodes.figure) if not fig["names"] for i in fig["ids"]}


def renumber_per_page(app, env):
    """Drop unnamed figures from ``env.toc_fignumbers`` and renumber the rest from 1 per page
    and type, keeping their order; return the pages whose numbers changed (Sphinx writes them
    again)."""
    changed = []
    for docname, types in env.toc_fignumbers.items():
        skip = unnamed_figure_ids(env.get_doctree(docname))
        new = {}
        for figtype, ids in types.items():
            kept = sorted((i for i in ids if i not in skip), key=ids.get)
            new[figtype] = {fid: (n,) for n, fid in enumerate(kept, start=1)}
        if new != types:
            env.toc_fignumbers[docname] = new
            changed.append(docname)
    return changed


def setup(app):
    # After Sphinx's own numbering (its toctree collector listens at the default priority).
    app.connect("env-get-updated", renumber_per_page, priority=900)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
