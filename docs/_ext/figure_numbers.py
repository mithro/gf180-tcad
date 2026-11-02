# SPDX-License-Identifier: Apache-2.0
"""Number only named figures, from 1 on each page.

A page names the light twin of a figure (``:name:``) and refers to it with ``{numref}``. Sphinx
numbers every figure that has an id, and MyST gives unnamed figures one, so the dark twin would
take a number of its own and the reader would see every other number. Sphinx also counts across
the whole site when the toctree is not numbered. This extension removes the ids of unnamed
figures as each page is read, and renumbers the figures of each page from 1 once Sphinx has
assigned its numbers.
"""

from docutils import nodes


def drop_unnamed_figure_ids(app, doctree):
    for fig in doctree.findall(nodes.figure):
        if not fig["names"]:
            fig["ids"] = []


def renumber_per_page(app, env):
    """Renumber ``env.toc_fignumbers`` from 1 per page and type, keeping the order; return the
    pages whose numbers changed (Sphinx writes them again)."""
    changed = []
    for docname, types in env.toc_fignumbers.items():
        new = {
            figtype: {fid: (i,) for i, fid in enumerate(sorted(ids, key=ids.get), start=1)}
            for figtype, ids in types.items()
        }
        if new != types:
            env.toc_fignumbers[docname] = new
            changed.append(docname)
    return changed


def setup(app):
    app.connect("doctree-read", drop_unnamed_figure_ids)
    # After Sphinx's own numbering (its toctree collector listens at the default priority).
    app.connect("env-get-updated", renumber_per_page, priority=900)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
