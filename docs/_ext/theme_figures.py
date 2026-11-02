# SPDX-License-Identifier: Apache-2.0
"""Merge each light/dark pair of figures into one figure.

A page draws a figure twice, once per theme: a ``{figure}`` with ``:figclass: only-light``
followed by its twin with ``:figclass: only-dark`` and the same caption. With ``numfig`` on,
Sphinx numbers both, so a ``{numref}`` would name the one a dark-theme reader never sees. On
``doctree-read``, before the numbers are assigned, :func:`merge_twins` moves the dark image into
the light figure, gives each image its theme class and drops the dark figure. The figure keeps
the light one's name, so it is numbered once and shows its caption in either theme.

Sphinx counts figures across the whole site when the toctree is not numbered. Once it has
assigned its numbers, :func:`renumber_per_page` numbers each page's figures from 1, keeping their
order, so the first figure on every page is Figure 1.

A pair that cannot be merged (no twin directly after the light one, other captions, or more than
one image in a twin) is a Sphinx warning, so ``sphinx-build -W`` fails rather than numbering the
twins apart.
"""

from docutils import nodes
from sphinx.util import logging

logger = logging.getLogger(__name__)

LIGHT, DARK = "only-light", "only-dark"


def _caption(fig: nodes.figure) -> str | None:
    caps = [c.astext() for c in fig.findall(nodes.caption)]
    return caps[0] if len(caps) == 1 else None


def merge_twins(doctree: nodes.Node, warn=None) -> int:
    """Merge every ``only-light`` figure that is directly followed by an ``only-dark`` figure
    with the same caption; return how many pairs were merged. ``warn(node, message)`` is called
    for each twin that cannot be merged."""
    warn = warn or (lambda node, msg: None)
    merged, paired = 0, set()
    for light in list(doctree.findall(nodes.figure)):
        if LIGHT not in light["classes"] or light.parent is None:
            continue
        dark = light.next_node(nodes.Element, siblings=True, descend=False, ascend=False)
        if not isinstance(dark, nodes.figure) or DARK not in dark["classes"]:
            warn(light, "an only-light figure with no only-dark twin directly after it")
            continue
        paired.add(id(dark))
        if _caption(light) is None or _caption(light) != _caption(dark):
            warn(
                light,
                "the only-light and only-dark twins have other captions; give both "
                "the same caption",
            )
            continue
        light_images = list(light.findall(nodes.image))
        dark_images = list(dark.findall(nodes.image))
        if len(light_images) != 1 or len(dark_images) != 1:
            warn(
                light,
                f"a twin pair needs one image in each figure, not "
                f"{len(light_images)} and {len(dark_images)}",
            )
            continue
        light_image, dark_image = light_images[0], dark_images[0]
        light_image["classes"].append(LIGHT)
        dark_image["classes"].append(DARK)
        dark_image.parent.remove(dark_image)
        light_image.parent.insert(light_image.parent.index(light_image) + 1, dark_image)
        light["classes"].remove(LIGHT)
        dark.parent.remove(dark)
        merged += 1
    for dark in list(doctree.findall(nodes.figure)):
        if DARK in dark["classes"] and id(dark) not in paired:
            warn(dark, "an only-dark figure with no only-light twin directly before it")
    return merged


def _on_doctree_read(app, doctree):
    merge_twins(doctree, warn=lambda node, msg: logger.warning(msg, location=node))


def renumber_per_page(app, env) -> list[str]:
    """Number each page's figures (and tables and code blocks) from 1 per type, in the order
    Sphinx gave them; return the pages whose numbers changed, so Sphinx writes them again."""
    changed = []
    for docname, types in env.toc_fignumbers.items():
        new = {
            figtype: {fid: (n,) for n, fid in enumerate(sorted(ids, key=ids.get), start=1)}
            for figtype, ids in types.items()
        }
        if new != types:
            env.toc_fignumbers[docname] = new
            changed.append(docname)
    return changed


def setup(app):
    app.connect("doctree-read", _on_doctree_read)
    # After Sphinx's own numbering: its toctree collector listens at the default priority, 500.
    app.connect("env-get-updated", renumber_per_page, priority=900)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
