# SPDX-License-Identifier: Apache-2.0
"""The render manifest ``<render>.render.json``: every number a render uses, with its source.

The file is written by :func:`gf180tcad.io.write_json` (sorted keys, ``repr`` floats). Its
top-level keys (:data:`REQUIRED`, :data:`OPTIONAL`):

- ``format``: :data:`FORMAT`;
- ``render``: the render's name, and optionally ``device`` and ``params``;
- ``inputs``: every source file a quantity reads, repo-relative, mapped to its sha256;
- ``quantities``: name to entry, each a :class:`gf180tcad.quantity.Quantity`;
- ``exaggeration``: the statements drawn into the image and written on its docs page. Each
  entry whose scale is not 1 has its :func:`exaggeration_text` here;
- ``outputs``, ``scene``, ``frames``, ``generator``, ``image`` and ``cycles``: the rendered
  files, the scene description, the animation frames, the generator hash, the render image
  and the Cycles settings, written by the render generator.

:meth:`Manifest.verify` re-reads every entry from its source, re-evaluates every derived entry
through :func:`gf180tcad.derive.evaluate` from the values of its inputs, checks every input
file's sha256 and every exaggeration statement, and returns the problems found.
:class:`Builder` writes a manifest by reading the same sources, so a scene builder never types a
number.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from gf180tcad import derive, io
from gf180tcad.quantity import Quantity, Selector, file_sha256

FORMAT = 1
REQUIRED = ("exaggeration", "format", "inputs", "quantities", "render")
OPTIONAL = ("cycles", "device", "frames", "generator", "image", "outputs", "params", "scene")


def exaggeration_text(label: str, scale: float) -> str:
    """The exaggeration statement of an entry drawn at ``scale`` times its size, for example
    ``"oxide thickness ×40, not to scale"``."""
    return f"{label} ×{scale:g}, not to scale"


def _derived_order(quantities: Mapping[str, Quantity]) -> list[str]:
    """The derived entries in an order where each comes after its derived inputs."""
    done: list[str] = []
    state: dict[str, str] = {}

    def visit(name: str, path: tuple[str, ...]) -> None:
        if state.get(name) == "done":
            return
        if state.get(name) == "visiting":
            raise ValueError(f"{name}: derived inputs form a cycle {' -> '.join((*path, name))}")
        state[name] = "visiting"
        for i in quantities[name].inputs:
            if quantities[i].derived is not None:
                visit(i, (*path, name))
        state[name] = "done"
        done.append(name)

    for name in sorted(quantities):
        if quantities[name].derived is not None:
            visit(name, ())
    return done


@dataclass
class Manifest:
    """One render manifest (see the module docstring)."""

    render: str
    quantities: dict[str, Quantity]
    inputs: dict[str, str]
    exaggeration: list[str]
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Mapping) -> Manifest:
        """The manifest of the mapping ``d``; ValueError on any schema error."""
        if unknown := sorted(set(d) - set(REQUIRED) - set(OPTIONAL)):
            raise ValueError(f"unknown key {unknown} in a render manifest")
        if missing := sorted(set(REQUIRED) - set(d)):
            raise ValueError(f"a render manifest needs {missing}")
        if d["format"] != FORMAT:
            raise ValueError(f"format {d['format']!r} is not {FORMAT}")
        if not isinstance(d["render"], str) or not d["render"]:
            raise ValueError(f"render must be a name, got {d['render']!r}")
        inputs = d["inputs"]
        if not isinstance(inputs, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) and len(v) == 64 for k, v in inputs.items()
        ):
            raise ValueError("inputs maps each repo-relative path to its sha256")
        ex = d["exaggeration"]
        if not isinstance(ex, list) or not all(isinstance(s, str) and s for s in ex):
            raise ValueError("exaggeration is a list of statements")
        if not isinstance(d["quantities"], Mapping):
            raise ValueError("quantities maps each name to its entry")  # noqa: TRY004
        qs = {n: Quantity.from_dict(n, q) for n, q in sorted(d["quantities"].items())}
        for name, q in qs.items():
            if q.derived is None:
                continue
            if q.derived not in derive.FORMULAS:
                raise ValueError(f"{name}: no formula {q.derived!r} in gf180tcad.derive")
            want = len(derive.FORMULAS[q.derived].inputs)
            if len(q.inputs) != want:
                raise ValueError(f"{name}: {q.derived} takes {want} inputs, got {len(q.inputs)}")
            for i in q.inputs:
                if i not in qs:
                    raise ValueError(f"{name}: input {i!r} is not a quantity of this manifest")
        _derived_order(qs)
        extra = {k: d[k] for k in OPTIONAL if k in d}
        return cls(d["render"], qs, dict(inputs), list(ex), extra)

    def to_dict(self) -> dict:
        """The mapping :meth:`from_dict` reads."""
        return {
            **self.extra,
            "format": FORMAT,
            "render": self.render,
            "inputs": dict(self.inputs),
            "quantities": {n: q.to_dict() for n, q in self.quantities.items()},
            "exaggeration": list(self.exaggeration),
        }

    @classmethod
    def load(cls, path: Path) -> Manifest:
        """Read and check the manifest file ``path``."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def dump(self, path: Path) -> None:
        """Write the manifest to ``path`` with :func:`gf180tcad.io.write_json`."""
        io.write_json(path, self.to_dict())

    def required_exaggeration(self) -> list[str]:
        """The statement of every entry whose scale is not 1, in name order."""
        return [
            exaggeration_text(q.label, q.scale)
            for q in self.quantities.values()
            if q.scale is not None and q.scale != 1
        ]

    def values(self, root: Path) -> tuple[dict, list[str]]:
        """Every entry's value as computed now under ``root``: read entries from their sources,
        derived entries from those values; and the problems met on the way."""
        got: dict = {}
        problems: list[str] = []
        for name, q in self.quantities.items():
            if q.derived is not None:
                continue
            path = Path(root) / q.source
            if not path.is_file():
                problems.append(f"{name}: source missing: {q.source}")
                continue
            try:
                got[name] = q.read(root)
            except (KeyError, IndexError, ValueError) as e:
                problems.append(f"{name}: {e}")
        for name in _derived_order(self.quantities):
            q = self.quantities[name]
            if not all(i in got for i in q.inputs):
                problems.append(f"{name}: an input could not be read")
                continue
            try:
                got[name] = derive.evaluate(q.derived, [got[i] for i in q.inputs])
            except (ValueError, ArithmeticError) as e:
                problems.append(f"{name}: {q.derived} failed: {e}")
        return got, problems

    def verify(self, root: Path) -> list[str]:
        """The problems of this manifest against the files under ``root`` (empty when it holds):
        a changed input file, a source not listed in ``inputs``, a missing source, a value that
        differs, a derived value that differs on re-evaluation, a missing exaggeration statement."""
        problems: list[str] = []
        for rel, sha in sorted(self.inputs.items()):
            path = Path(root) / rel
            if not path.is_file():
                problems.append(f"input {rel}: missing")
            elif file_sha256(path) != sha:
                problems.append(f"input {rel}: sha256 changed")
        for name, q in self.quantities.items():
            if q.source is not None and q.source not in self.inputs:
                problems.append(f"{name}: source not listed in inputs: {q.source}")
        got, found = self.values(root)
        problems += found
        for name, q in self.quantities.items():
            if name not in got:
                continue
            if why := q.mismatch(got[name]):
                kind = "derived " if q.derived is not None and why.startswith("value ") else ""
                problems.append(f"{name}: {kind}{why}")
        for name, q in self.quantities.items():
            if q.scale is not None and q.scale != 1:
                text = exaggeration_text(q.label, q.scale)
                if text not in self.exaggeration:
                    problems.append(f"{name}: no exaggeration string {text!r}")
        return problems


class Builder:
    """Write a :class:`Manifest` by reading committed files under ``root``: each
    :meth:`source` call reads its value and records the file's sha256, each :meth:`derived`
    call evaluates its formula."""

    def __init__(self, root: Path, render: str, **extra):
        self.root = Path(root)
        self.render = render
        self.extra = extra
        self.quantities: dict[str, Quantity] = {}
        self.inputs: dict[str, str] = {}
        self._values: dict = {}

    def _add(self, q: Quantity, value) -> object:
        if q.name in self.quantities:
            raise ValueError(f"{q.name}: already in the manifest")
        q.record(value)
        Quantity.from_dict(q.name, q.to_dict())  # the schema checks
        self.quantities[q.name] = q
        self._values[q.name] = value
        return value

    def source(
        self,
        name: str,
        source: str,
        selector: Mapping,
        unit: str | list[str],
        role: str = "value",
        scale: float | None = None,
        label: str | None = None,
    ):
        """Read entry ``name`` from the repo-relative ``source``; returns its value."""
        q = Quantity(name, unit, role, scale, label, source, Selector.from_dict(selector))
        value = q.read(self.root)
        self.inputs[source] = file_sha256(self.root / source)
        return self._add(q, value)

    def derived(
        self,
        name: str,
        formula: str,
        inputs: Sequence[str],
        unit: str | list[str],
        role: str = "value",
        scale: float | None = None,
        label: str | None = None,
    ):
        """Derive entry ``name`` by ``formula`` from the entries ``inputs``; returns its value."""
        missing = [i for i in inputs if i not in self._values]
        if missing:
            raise ValueError(f"{name}: inputs {missing} are not in the manifest yet")
        value = derive.evaluate(formula, [self._values[i] for i in inputs])
        q = Quantity(name, unit, role, scale, label, derived=formula, inputs=tuple(inputs))
        return self._add(q, value)

    def build(self, statements: Sequence[str] = ()) -> Manifest:
        """The manifest: the exaggeration statements of the scaled entries, then
        ``statements`` (others, such as a log-scaled axis)."""
        m = Manifest(self.render, dict(sorted(self.quantities.items())), dict(self.inputs), [])
        m.exaggeration = [*m.required_exaggeration(), *statements]
        m.extra = dict(self.extra)
        return Manifest.from_dict(m.to_dict())
