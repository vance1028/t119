from __future__ import annotations

import hashlib
import os
from pathlib import Path

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


CHUNK_SIZE = 65536


def compute_file_hash(path: str | Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _image_dhash_bits(img: "Image.Image", w: int = 9, h: int = 8) -> bytes:
    gray = img.convert("L")
    src_pixels = [p & 0xE0 for p in gray.getdata()]
    cleaned = Image.new("L", gray.size)
    cleaned.putdata(src_pixels)
    small = cleaned.resize((w, h), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    bits = bytearray()
    for row in range(h):
        row_start = row * w
        for col in range(w - 1):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            if abs(left - right) <= 2:
                bits.append(0)
            else:
                bits.append(1 if left > right else 0)
    return bytes(bits)


def compute_image_perceptual_fingerprint(path: str | Path) -> str:
    if not _PIL_AVAILABLE:
        return compute_file_hash(path)
    try:
        with Image.open(path) as img:
            bits = _image_dhash_bits(img)
            md5 = hashlib.md5(bits).hexdigest()
            sha = hashlib.sha256(bits).hexdigest()
            return md5 + sha[:16]
    except Exception:
        return compute_file_hash(path)


def _strip_zero_width_markers(text: str) -> str:
    from .zwc_stego import _split_text_body_and_zwc
    body, _ = _split_text_body_and_zwc(text)
    return body


def compute_text_fingerprint(path: str | Path) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        stripped = _strip_zero_width_markers(content)
        normalized = " ".join(stripped.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    except Exception:
        return compute_file_hash(path)


def compute_fingerprint(path: str | Path, file_type: str) -> str:
    path = Path(path)
    if file_type == "image":
        return compute_image_perceptual_fingerprint(path)
    elif file_type == "text":
        return compute_text_fingerprint(path)
    else:
        return compute_file_hash(path)
