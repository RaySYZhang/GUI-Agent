"""Reserved image utilities.

The official BaseAgent already provides image-to-base64 encoding. This module is
kept intentionally small so the final submission remains lightweight.
"""

from __future__ import annotations

from typing import Tuple

from PIL import Image


def resize_if_needed(image: Image.Image, max_side: int = 1600) -> Image.Image:
    """Return a resized copy only if the image is unusually large."""
    w, h = image.size
    longest = max(w, h)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    new_size: Tuple[int, int] = (max(1, int(w * scale)), max(1, int(h * scale)))
    return image.resize(new_size)
