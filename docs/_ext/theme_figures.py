# SPDX-License-Identifier: Apache-2.0
"""Merge each light/dark pair of figures into one figure.

A page draws a figure twice, once per theme: a ``{figure}`` with ``:figclass: only-light``
followed by its twin with ``:figclass: only-dark`` and the same caption. With ``numfig`` on,
Sphinx numbers both, so a ``{numref}`` would name the one a dark-theme reader never sees. On
``doctree-read``, before the numbers are assigned, :func:`merge_twins` moves the dark image into
the light figure, gives each image its theme class and drops the dark figure. The figure keeps
the light one's name, so it is numbered once and shows its caption in either theme.
"""

from docutils import nodes

LIGHT, DARK = "only-light", "only-dark"


def _caption(fig: nodes.figure) -> str | None:
    caps = [c.astext() for c in fig.findall(nodes.caption)]
    return caps[0] if len(caps) == 1 else None


def merge_twins(doctree: nodes.Node) -> int:
    """Merge every ``only-light`` figure that is directly followed by an ``only-dark`` figure
    with the same caption; return how many pairs were merged."""
    merged = 0
    for light in list(doctree.findall(nodes.figure)):
        if LIGHT not in light["classes"] or light.parent is None:
            continue
        dark = light.next_node(nodes.Element, siblings=True, descend=False, ascend=False)
        if not isinstance(dark, nodes.figure) or DARK not in dark["classes"]:
            continue
        if _caption(light) is None or _caption(light) != _caption(dark):
            continue
        light_images = list(light.findall(nodes.image))
        dark_images = list(dark.findall(nodes.image))
        if len(light_images) != 1 or len(dark_images) != 1:
            continue
        light_image, dark_image = light_images[0], dark_images[0]
        light_image["classes"].append(LIGHT)
        dark_image["classes"].append(DARK)
        dark_image.parent.remove(dark_image)
        light_image.parent.insert(light_image.parent.index(light_image) + 1, dark_image)
        light["classes"].remove(LIGHT)
        dark.parent.remove(dark)
        merged += 1
    return merged


def _on_doctree_read(app, doctree):
    merge_twins(doctree)


def setup(app):
    app.connect("doctree-read", _on_doctree_read)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
