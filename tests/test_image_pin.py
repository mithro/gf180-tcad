# SPDX-License-Identifier: Apache-2.0
"""docker/IMAGE pins our ghcr image by manifest digest; docker/base/IMAGE_ID is its config digest."""

import re
from pathlib import Path

DOCKER = Path(__file__).resolve().parents[1] / "docker"


def test_image_pinned_by_digest():
    text = (DOCKER / "IMAGE").read_text(encoding="utf-8")
    assert re.fullmatch(r"ghcr\.io/mithro/gf180-tcad-base@sha256:[0-9a-f]{64}\n", text)


def test_image_id_is_a_digest():
    text = (DOCKER / "base" / "IMAGE_ID").read_text(encoding="utf-8")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}\n", text)
