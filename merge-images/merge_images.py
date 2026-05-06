#!/usr/bin/env python3
import os
import re
from pathlib import Path
from PIL import Image

NUM_RE = re.compile(r"(\d+)")


def numeric_key(p: Path):
    m = NUM_RE.search(p.stem)
    return int(m.group(1)) if m else float("inf")


def merge_vertical(folder: Path):
    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder}")

    exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
    images = [p for p in folder.iterdir() if p.suffix.lower() in exts]
    images.sort(key=numeric_key)

    if not images:
        raise ValueError("No images found.")

    opened = [Image.open(p) for p in images]
    widths = [im.width for im in opened]
    heights = [im.height for im in opened]

    total_height = sum(heights)
    max_width = max(widths)

    merged = Image.new("RGB", (max_width, total_height), color=(255, 255, 255))
    y = 0
    for im in opened:
        if im.mode != "RGB":
            im = im.convert("RGB")
        merged.paste(im, (0, y))
        y += im.height

    out_path = folder.parent / f"{folder.name}.jpg"
    merged.save(out_path, quality=95)
    return out_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: merge_images.py /path/to/folder")
        sys.exit(1)
    out = merge_vertical(Path(sys.argv[1]))
    print(f"Saved: {out}")
