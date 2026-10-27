# SPDX-License-Identifier: Apache-2.0
"""The explainer pages' machinery (``docs/explained/``): numbers, idealised formulas, the one
device model and the figures.

Imported only by ``docs/conf.py``, :mod:`gf180tcad.docgen` and the tests, never by a module of
a hashed generator closure (tested), so nothing here changes a committed result's provenance.
"""


def substitutions() -> dict[str, str]:
    """Every MyST substitution of the explainer pages: the numbers
    (:func:`gf180tcad.explain.numbers.substitutions`) and the figures' scale statements
    (:func:`gf180tcad.explain.figures.substitutions`). ValueError on a key defined twice."""
    from gf180tcad.explain import figures, numbers

    a, b = numbers.substitutions(), figures.substitutions()
    if both := sorted(set(a) & set(b)):
        raise ValueError(f"substitution keys defined twice: {both}")
    return {**a, **b}
