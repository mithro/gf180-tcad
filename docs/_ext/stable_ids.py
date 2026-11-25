# SPDX-License-Identifier: Apache-2.0
"""Identify each figure and table by its label instead of a running number.

Sphinx numbers figures and tables in one sequence, so adding a figure renumbers every one after
it, and a number quoted in an issue or a pull request comment goes stale. This extension shows
each item's own label instead, less the prefix that only repeats its kind: the table labelled
``tab-poe-pairs`` is captioned "Table poe-pairs: ..." and ``{numref}`` prints "Table
poe-pairs". The identifier changes only when somebody renames the label, and then every
``{numref}`` to the old label fails the ``-W`` build.

How it works:

* Sphinx assigns its numbers in its own ``env-get-updated`` handler (priority 500) and keeps
  them in ``env.toc_fignumbers[docname][kind][id] = (n,)``. :func:`replace_numbers` runs after
  it (priority 900) and replaces each tuple with ``(identifier,)``; the HTML writer and
  ``{numref}`` join the tuple into ``numfig_format`` ("Table %s"), so they print the identifier.
* Sphinx rewrites every page whose numbers differ from the ones it kept from the last build.
  :func:`replace_numbers` saves the real numbers in ``env.stable_ids_numbers``, and
  :func:`restore_numbers` (priority 100, before Sphinx's handler) puts them back, so a rebuild
  with no change writes no page.
* :class:`CaptionColonTranslator` adds a colon after the identifier in a caption only
  ("Table poe-pairs: The two pair sets"); a ``{numref}`` has none ("Table poe-pairs lists").
* A numbered item with no label (Sphinx gave it an id such as ``id3``) and two labels that
  give the same identifier are Sphinx warnings, so ``sphinx-build -W`` fails.

theme_figures (docs/_ext/theme_figures.py) merges each light/dark twin pair into one figure on
``doctree-read``, before any number is assigned, so a pair has the light twin's label and one
identifier, and the dark twin is never numbered.

Adapted from evampire's docs/_ext/stable_ids.py (Apache-2.0).
"""

import copy
import re

from sphinx.util import logging
from sphinx.writers.html5 import HTML5Translator

logger = logging.getLogger(__name__)

#: Label prefixes that only repeat the kind of item, which the caption already states.
KIND_PREFIXES = {
    "figure": ("fig-",),
    "table": ("tab-", "tbl-"),
    "code-block": ("lst-",),
}

# An id that docutils made up for an item without a label, such as "id3".
_GENERATED_ID = re.compile(r"id\d+")


def stable_id(kind: str, label: str) -> str:
    """The identifier readers see for the item of this kind and label. This function alone
    decides it, so a different scheme needs changes only here."""
    for prefix in KIND_PREFIXES.get(kind, ()):
        if label.startswith(prefix):
            return label[len(prefix) :]
    return label


def _labels(env) -> dict[tuple[str, str], str]:
    """{(docname, element id): label}: the label as written (MyST ``:name:``, rST ``.. _x:``),
    lowercased by docutils. The element id is the label made id-safe (an underscore becomes a
    hyphen), so the label, which a reader can search the source for, is shown instead."""
    labels = env.domains.standard_domain.labels
    return {(docname, labelid): name for name, (docname, labelid, _) in labels.items()}


def restore_numbers(app, env) -> list[str]:
    """Put back the numbers Sphinx assigned in the previous build, so that its comparison with
    the numbers it assigns now sees numbers on both sides."""
    numbers = getattr(env, "stable_ids_numbers", None)
    if numbers is not None:
        env.toc_fignumbers = numbers
    return []


def replace_numbers(app, env) -> list[str]:
    """Swap every number Sphinx assigned for the item's identifier; warn for an item with no
    label and for two labels with one identifier."""
    env.stable_ids_numbers = copy.deepcopy(env.toc_fignumbers)
    labels = _labels(env)
    seen: dict[tuple[str, str], tuple[str, str]] = {}
    for docname in sorted(env.toc_fignumbers):
        for kind, numbers in env.toc_fignumbers[docname].items():
            for element_id in sorted(numbers):
                label = labels.get((docname, element_id))
                if label is None and _GENERATED_ID.fullmatch(element_id):
                    logger.warning(
                        "a numbered %s has no label, so it has no identifier to show; give it "
                        "a :name: (element id %s)",
                        kind,
                        element_id,
                        location=docname,
                        type="stable_ids",
                    )
                    continue
                label = label or element_id
                identifier = stable_id(kind, label)
                first = seen.setdefault((kind, identifier), (docname, label))
                if first != (docname, label):
                    logger.warning(
                        "%s '%s' has the same identifier '%s' as '%s' in %s; rename one of "
                        "the labels",
                        kind,
                        label,
                        identifier,
                        first[1],
                        first[0],
                        location=docname,
                        type="stable_ids",
                    )
                numbers[element_id] = (identifier,)
    return []


class CaptionColonTranslator(HTML5Translator):
    """Write "Table poe-pairs: " at the start of a caption; {numref} text keeps no colon."""

    def add_fignumber(self, node) -> None:
        start = len(self.body)
        super().add_fignumber(node)
        # Sphinx appends three strings: the opening <span>, the identifier followed by a space,
        # and the closing </span>.
        added = self.body[start:]
        if len(added) == 3 and added[1].endswith(" "):
            self.body[start + 1] = added[1][:-1] + ": "
        elif added:
            logger.warning(
                "the caption number has an unexpected form, so no colon was added; update "
                "CaptionColonTranslator for this Sphinx version",
                location=node,
                type="stable_ids",
            )


def setup(app):
    # Sphinx assigns the numbers in its own handler for this event at the default priority,
    # 500; a higher number runs later.
    app.connect("env-get-updated", restore_numbers, priority=100)
    app.connect("env-get-updated", replace_numbers, priority=900)
    for builder in ("html", "dirhtml", "singlehtml"):
        app.set_translator(builder, CaptionColonTranslator)
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
