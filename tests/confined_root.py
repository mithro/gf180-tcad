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
    (root / "work" / "src").mkdir(parents=True)
    (root / "work" / "out").mkdir(parents=True)
    (root / "proc" / "self" / "mountinfo").write_text(
        "986 900 0:60 / / ro,relatime - overlay overlay rw\n"
        "995 986 254:124 /home/u/repo /work/src ro,relatime - ext4 /dev/sda1 rw\n"
        "996 986 0:34 /tmp/x /work/out rw,nosuid,nodev - tmpfs tmpfs rw\n"
    )
    return root
