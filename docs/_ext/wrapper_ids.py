# SPDX-License-Identifier: Apache-2.0
"""Give each id in the built pages one element (issue #150).

The Furo theme wraps every table and every display equation in a ``container`` (classes
``table-wrapper`` and ``math-wrapper``) so that it can scroll at phone width. Its
post-transform ``WrapTableAndMathInAContainerTransform`` (priority 500) copies all attributes of
the wrapped node onto the wrapper. The ids go with them, and the wrapped node keeps its own. A
labelled equation or a named table then carries its id twice, which is invalid HTML.

:class:`DropWrapperIds` runs after it and removes from each wrapper the ids its wrapped node
carries. The wrapped node keeps them: Sphinx's math writer reads an equation's number from the
equation's own first id, and a link to the equation or table lands on the element itself.
"""

from docutils import nodes
from sphinx.transforms.post_transforms import SphinxPostTransform

#: The wrapper classes Furo gives its containers.
WRAPPER_CLASSES = ("table-wrapper", "math-wrapper")


class DropWrapperIds(SphinxPostTransform):
    """Remove from each Furo wrapper the ids its wrapped table or equation also carries."""

    formats = ("html",)
    default_priority = 501  # after Furo's wrapping transform (500)

    def run(self, **kwargs) -> None:
        for wrapper in list(self.document.findall(nodes.container)):
            if not set(wrapper["classes"]) & set(WRAPPER_CLASSES) or not wrapper["ids"]:
                continue
            inner = {i for c in wrapper.children if isinstance(c, nodes.Element) for i in c["ids"]}
            wrapper["ids"] = [i for i in wrapper["ids"] if i not in inner]


def setup(app):
    app.add_post_transform(DropWrapperIds)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
