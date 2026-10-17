# gf180-tcad

Open-source TCAD for the GlobalFoundries GF180MCU process, validated against the
PDK's own SPICE models.

## What and why

This project builds a scriptable TCAD flow (structures from gdsfactory layouts,
simulated with [DEVSIM](https://devsim.net/) and cross-checked with Charon) for
GF180MCU transistors, and measures, quantitatively, reproducibly and in public,
how closely it agrees with the PDK SPICE models.

The SPICE models are the golden reference; the TCAD is the suspect. Mismatches
are documented with their probable cause rather than hidden. Only once the TCAD
has earned confidence will it be used to extend or create SPICE models.

## Status

Phase 0 (foundations and SPICE reference dataset) is in progress. Nothing here
is a result yet.

## Documentation

https://gf180-tcad.readthedocs.io (to be created)

## Development

```
uv sync
uv run pytest -m "not sandbox"
uv run ruff check
uv run ruff format --check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution rules.

## Licence

Apache-2.0, see [LICENSE](LICENSE).
