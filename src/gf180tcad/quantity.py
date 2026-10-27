# SPDX-License-Identifier: Apache-2.0
"""Read one named quantity from a committed file: the single reader module of the repo.

A :class:`Selector` names where a value sits inside a file, from a closed set of four kinds
(:data:`SELECTOR_KINDS`):

- ``json``: a key path, a list of keys (strings) and list indices (integers);
- ``csv``: ``columns``, a list of column names, plus exactly one row rule: ``rows: "all"``
  (every row), ``where: {column: value}`` (the one row whose column equals the value exactly)
  or ``index: i`` (the row at index i, from 0). The file may hold ``#`` comment lines before
  its header, as :func:`gf180tcad.io.write_csv` writes, and may be gzip-compressed (``.gz``);
- ``npz``: the name of one array member of a numpy ``.npz`` archive;
- ``toml``: a key path of table and key names.

:func:`read` returns the value: a scalar, a numpy array (one ``csv`` column over all rows, an
``npz`` member), a tuple (several ``csv`` columns) or the JSON or TOML value itself.
:func:`canonical_sha256` hashes an array by its canonical JSON text (:func:`canonical_json`:
compact, sorted keys, ``repr`` floats), so a manifest records a large array by its hash and a
test re-reads and re-hashes it.

A :class:`Quantity` is one manifest entry: either read from a file (``source`` and
``selector``) or derived by a named formula from other entries (``derived`` and ``inputs``),
with its ``unit``, its ``role`` (:data:`ROLES`), a ``scale`` factor (required for the roles
``geometry`` and ``axis``; 1 means to scale), a ``label`` naming it in an exaggeration
statement, and either ``value`` (a scalar) or ``value_sha256`` (an array).

The module imports only the standard library and numpy (tested), so the render manifest
(:mod:`gf180tcad.render.manifest`) and the explainer pages can share it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

SELECTOR_KINDS = ("csv", "json", "npz", "toml")
ROLES = ("axis", "display", "geometry", "value")
SCALED_ROLES = ("axis", "geometry")
_ROW_RULES = ("index", "rows", "where")


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


@dataclass(frozen=True)
class Selector:
    """Where a value sits in a file: ``kind`` (one of :data:`SELECTOR_KINDS`) and its ``spec``."""

    kind: str
    spec: Any

    @classmethod
    def from_dict(cls, d: Mapping) -> Selector:
        """The selector of the one-key mapping ``{kind: spec}``; ValueError if it is not one."""
        if not isinstance(d, Mapping) or len(d) != 1:
            raise ValueError(f"a selector is a one-key mapping {{kind: spec}}, got {d!r}")
        ((kind, spec),) = d.items()
        if kind not in SELECTOR_KINDS:
            raise ValueError(f"selector kind {kind!r} is not one of {SELECTOR_KINDS}")
        check = {"json": _check_json, "toml": _check_toml, "npz": _check_npz, "csv": _check_csv}
        check[kind](spec)
        return cls(kind, spec)

    def to_dict(self) -> dict:
        """The ``{kind: spec}`` mapping :meth:`from_dict` reads."""
        return {self.kind: self.spec}


def _check_path(kind: str, spec, ints: bool) -> None:
    if not isinstance(spec, list) or not spec:
        raise ValueError(f"a {kind} selector is a non-empty key path list, got {spec!r}")
    for k in spec:
        if not (isinstance(k, str) and k) and not (ints and _is_int(k)):
            raise ValueError(f"{kind} key path element {k!r} is not a key name or a list index")


def _check_json(spec) -> None:
    _check_path("json", spec, ints=True)


def _check_toml(spec) -> None:
    _check_path("toml", spec, ints=False)


def _check_npz(spec) -> None:
    if not isinstance(spec, str) or not spec:
        raise ValueError(f"an npz selector is a member name, got {spec!r}")


def _check_csv(spec) -> None:
    if not isinstance(spec, Mapping):
        raise ValueError(f"a csv selector is a mapping, got {spec!r}")  # noqa: TRY004 (a schema error)
    cols = spec.get("columns")
    if not isinstance(cols, list) or not cols or not all(isinstance(c, str) and c for c in cols):
        raise ValueError(f"a csv selector needs a non-empty list of column names, got {cols!r}")
    rules = [k for k in spec if k != "columns"]
    if len(rules) != 1 or rules[0] not in _ROW_RULES:
        raise ValueError(f"a csv selector needs exactly one row rule of {_ROW_RULES}, got {rules}")
    rule, arg = rules[0], spec[rules[0]]
    if rule == "rows" and arg != "all":
        raise ValueError(f'csv rows must be "all", got {arg!r}')
    if rule == "index" and not (_is_int(arg) and arg >= 0):
        raise ValueError(f"csv index must be an integer >= 0, got {arg!r}")
    if rule == "where" and not (
        isinstance(arg, Mapping)
        and len(arg) == 1
        and all(isinstance(k, str) and _is_number(v) for k, v in arg.items())
    ):
        raise ValueError(f"csv where must be one {{column: number}}, got {arg!r}")


def _walk(obj, path: Sequence, where: Path):
    for k in path:
        try:
            obj = obj[k]
        except (KeyError, IndexError, TypeError):
            raise KeyError(f"{where}: no key {k!r} on the path {list(path)!r}") from None
    return obj


def read_text(path: Path) -> str:
    """The UTF-8 text of ``path``, gunzipped when its name ends in ``.gz``."""
    data = Path(path).read_bytes()
    if Path(path).suffix == ".gz":
        data = gzip.decompress(data)
    return data.decode("utf-8")


def read_csv_columns(path: Path) -> dict[str, np.ndarray]:
    """Every column of a CSV file as float64 arrays, skipping ``#`` lines before the header."""
    lines = [ln for ln in read_text(path).splitlines() if ln and not ln.startswith("#")]
    if not lines:
        raise ValueError(f"{path}: no CSV header")
    names = lines[0].split(",")
    rows = [ln.split(",") for ln in lines[1:]]
    if any(len(r) != len(names) for r in rows):
        raise ValueError(f"{path}: ragged CSV row")
    return {n: np.array([float(r[i]) for r in rows], dtype=np.float64) for i, n in enumerate(names)}


def _read_csv(spec: Mapping, path: Path):
    cols = read_csv_columns(path)
    for c in spec["columns"]:
        if c not in cols:
            raise KeyError(f"{path}: no column {c!r} (has {list(cols)})")
    picked = [cols[c] for c in spec["columns"]]
    if "rows" in spec:
        return picked[0] if len(picked) == 1 else tuple(picked)
    if "index" in spec:
        i = spec["index"]
        n = len(picked[0])
        if i >= n:
            raise IndexError(f"{path}: row index {i} out of range ({n} rows)")
        row = tuple(float(a[i]) for a in picked)
    else:
        ((col, want),) = spec["where"].items()
        if col not in cols:
            raise KeyError(f"{path}: no column {col!r} (has {list(cols)})")
        hits = np.flatnonzero(cols[col] == want)
        if len(hits) != 1:
            what = "no row" if not len(hits) else f"{len(hits)} rows"
            raise ValueError(f"{path}: {what} with {col} == {want!r}; a where rule needs one")
        row = tuple(float(a[hits[0]]) for a in picked)
    return row[0] if len(row) == 1 else row


def read(selector: Selector, path: Path):
    """The value ``selector`` names in the file ``path`` (see the module docstring)."""
    path = Path(path)
    if selector.kind == "json":
        return _walk(json.loads(read_text(path)), selector.spec, path)
    if selector.kind == "toml":
        return _walk(tomllib.loads(read_text(path)), selector.spec, path)
    if selector.kind == "npz":
        with np.load(path, allow_pickle=False) as z:
            if selector.spec not in z.files:
                raise KeyError(f"{path}: no member {selector.spec!r} (has {sorted(z.files)})")
            return z[selector.spec]
    return _read_csv(selector.spec, path)


def _plain(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, tuple | list):
        return [_plain(x) for x in obj]
    if isinstance(obj, Mapping):
        return {str(k): _plain(v) for k, v in obj.items()}
    return obj


def canonical_json(value) -> str:
    """The canonical JSON text of ``value``: arrays and tuples as lists, sorted keys, no spaces,
    ``repr`` floats (so -0.0 and 0.0 differ), NaN and infinities refused (ValueError)."""
    return json.dumps(
        _plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def canonical_sha256(value) -> str:
    """The sha256 (hex) of :func:`canonical_json` of ``value``, UTF-8 encoded."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def is_array(value) -> bool:
    """True unless ``value`` is a scalar (a number, a string, a boolean or None): a manifest
    records an array by :func:`canonical_sha256` and a scalar by its value."""
    if isinstance(value, np.ndarray):
        return value.ndim > 0
    return not isinstance(value, str | int | float | bool | np.generic | type(None))


def file_sha256(path: Path) -> str:
    """The sha256 (hex) of the bytes of ``path``."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class Quantity:
    """One manifest entry (see the module docstring). Build it with :meth:`from_dict`, which
    checks the schema; :meth:`to_dict` writes it back."""

    name: str
    unit: str | list[str]
    role: str = "value"
    scale: float | None = None
    label: str | None = None
    source: str | None = None
    selector: Selector | None = None
    derived: str | None = None
    inputs: tuple[str, ...] = ()
    value: Any = None
    value_sha256: str | None = None

    _KEYS = frozenset(
        {"unit", "role", "scale", "label", "source", "selector", "derived", "inputs"}
        | {"value", "value_sha256"}
    )

    @classmethod
    def from_dict(cls, name: str, d: Mapping) -> Quantity:
        """The entry ``name`` of a manifest's ``quantities``; ValueError naming ``name`` on any
        schema error."""

        def fail(msg: str):
            raise ValueError(f"{name}: {msg}")

        if not isinstance(d, Mapping):
            fail(f"an entry is a mapping, got {d!r}")
        if unknown := sorted(set(d) - cls._KEYS):
            fail(f"unknown key {unknown}")
        unit = d.get("unit")
        if not (
            isinstance(unit, str)
            or (isinstance(unit, list) and all(isinstance(u, str) for u in unit))
        ):
            fail(f"unit must be a string or a list of strings, got {unit!r}")
        role = d.get("role", "value")
        if role not in ROLES:
            fail(f"role {role!r} is not one of {ROLES}")
        scale = d.get("scale")
        if scale is not None and not (_is_number(scale) and scale > 0):
            fail(f"scale must be a number > 0, got {scale!r}")
        if role in SCALED_ROLES and scale is None:
            fail(f"role {role!r} needs a scale (1 when to scale)")
        label = d.get("label")
        if label is not None and not (isinstance(label, str) and label):
            fail(f"label must be a non-empty string, got {label!r}")
        if scale is not None and scale != 1 and label is None:
            fail(f"scale {float(scale)!r} needs a label for its exaggeration statement")
        sourced = "source" in d or "selector" in d
        derived = "derived" in d or "inputs" in d
        if sourced == derived:
            fail("an entry has either source and selector, or derived and inputs")
        selector = None
        if sourced:
            if not (isinstance(d.get("source"), str) and d["source"]) or "selector" not in d:
                fail("a read entry needs a source path and a selector")
            try:
                selector = Selector.from_dict(d["selector"])
            except ValueError as e:
                fail(str(e))
        inputs: tuple[str, ...] = ()
        if derived:
            if not isinstance(d.get("derived"), str) or not isinstance(d.get("inputs"), list):
                fail("a derived entry needs a formula name and a list of input names")
            inputs = tuple(d["inputs"])
            if not inputs or not all(isinstance(i, str) for i in inputs):
                fail(f"inputs must be a non-empty list of names, got {d['inputs']!r}")
        if ("value" in d) == ("value_sha256" in d):
            fail("exactly one of value and value_sha256")
        if "value" in d and is_array(d["value"]):
            fail("value holds a scalar; an array is recorded by value_sha256")
        sha = d.get("value_sha256")
        if sha is not None and not (isinstance(sha, str) and len(sha) == 64):
            fail(f"value_sha256 must be 64 hex digits, got {sha!r}")
        return cls(
            name=name,
            unit=unit,
            role=role,
            scale=None if scale is None else float(scale),
            label=label,
            source=d.get("source"),
            selector=selector,
            derived=d.get("derived"),
            inputs=inputs,
            value=d.get("value"),
            value_sha256=sha,
        )

    def to_dict(self) -> dict:
        """The mapping :meth:`from_dict` reads (absent fields left out)."""
        d: dict = {"unit": self.unit, "role": self.role}
        if self.scale is not None:
            d["scale"] = self.scale
        if self.label is not None:
            d["label"] = self.label
        if self.source is not None:
            d["source"] = self.source
            d["selector"] = self.selector.to_dict()
        if self.derived is not None:
            d["derived"] = self.derived
            d["inputs"] = list(self.inputs)
        if self.value_sha256 is not None:
            d["value_sha256"] = self.value_sha256
        else:
            d["value"] = self.value
        return d

    def record(self, value) -> None:
        """Store ``value``: a scalar in :attr:`value`, an array by :func:`canonical_sha256`."""
        if is_array(value):
            self.value, self.value_sha256 = None, canonical_sha256(value)
        else:
            self.value, self.value_sha256 = _plain(value), None

    def mismatch(self, value) -> str | None:
        """None when ``value`` is the recorded one, else why not (exact: ``repr`` for floats)."""
        if self.value_sha256 is not None:
            if not is_array(value):
                return f"recorded an array, got the scalar {value!r}"
            got = canonical_sha256(value)
            if got != self.value_sha256:
                return f"value_sha256 {got} != recorded {self.value_sha256}"
            return None
        if is_array(value):
            return "recorded a scalar, got an array"
        got = _plain(value)
        if type(got) is not type(self.value) or repr(got) != repr(self.value):
            return f"value {got!r} != recorded {self.value!r}"
        return None

    def read(self, root: Path):
        """The value of a read entry from its source under ``root``."""
        if self.selector is None:
            raise ValueError(f"{self.name}: a derived entry has no source to read")
        return read(self.selector, Path(root) / self.source)
