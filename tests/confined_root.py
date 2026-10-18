# SPDX-License-Identifier: Apache-2.0
"""A fake confined-container filesystem root for the in-sandbox code paths (test helper)."""

from pathlib import Path


def make_confined_root(root: Path, *, cgroup: str = "/") -> Path:
    """A filesystem root that looks like a tools/sandbox-run container."""
    (root / "proc" / "self").mkdir(parents=True)
    (root / "proc" / "self" / "cgroup").write_text(f"0::{cgroup}\n")
    cg = root / "sys" / "fs" / "cgroup" / cgroup.strip("/")
    cg.mkdir(parents=True, exist_ok=True)
    (cg / "memory.max").write_text("4294967296\n")
    (cg / "pids.max").write_text("256\n")
    net = root / "sys" / "class" / "net"
    (net / "lo").mkdir(parents=True)
    (net / "bonding_masters").write_text("\n")  # a plain file, not an interface (real kernels)
    (root / ".dockerenv").write_text("")
    return root
