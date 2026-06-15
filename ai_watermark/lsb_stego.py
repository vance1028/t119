from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional, Tuple

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

from .models import WatermarkPayload


HEADER_MAGIC = b"AWM1"
HEADER_SIZE = 4 + 4


def _check_pil():
    if not _PIL_AVAILABLE:
        raise ImportError("Pillow is required for image operations")


def _embed_bits_into_pixels(pixels: list[Tuple[int, ...]], bits: list[int]) -> list[Tuple[int, ...]]:
    new_pixels = []
    bit_idx = 0
    total_bits = len(bits)
    for pix in pixels:
        new_pix = list(pix)
        for channel in range(3):
            if bit_idx < total_bits:
                old_val = new_pix[channel]
                bit_val = bits[bit_idx]
                new_pix[channel] = (old_val & 0xFE) | bit_val
                bit_idx += 1
            else:
                break
        new_pixels.append(tuple(new_pix))
        if bit_idx >= total_bits and len(new_pixels) == len(pixels):
            break
    if len(new_pixels) < len(pixels):
        new_pixels.extend(pixels[len(new_pixels):])
    return new_pixels


def _extract_bits_from_pixels(pixels: list[Tuple[int, ...]], num_bits: int) -> Optional[list[int]]:
    bits = []
    bit_idx = 0
    for pix in pixels:
        for channel in range(3):
            if bit_idx < num_bits:
                bits.append(pix[channel] & 0x01)
                bit_idx += 1
            else:
                break
        if bit_idx >= num_bits:
            break
    if len(bits) < num_bits:
        return None
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        out.append(byte)
    return bytes(out)


def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 0x01)
    return bits


def _prepare_payload_data(payload_str: str) -> bytes:
    body = payload_str.encode("utf-8")
    length = len(body)
    return HEADER_MAGIC + struct.pack(">I", length) + body


def _parse_payload_data(raw: bytes) -> Optional[str]:
    if len(raw) < HEADER_SIZE:
        return None
    if raw[:4] != HEADER_MAGIC:
        return None
    length = struct.unpack(">I", raw[4:8])[0]
    if length <= 0 or length > len(raw) - HEADER_SIZE:
        return None
    body = raw[HEADER_SIZE:HEADER_SIZE + length]
    try:
        return body.decode("utf-8")
    except Exception:
        return None


def _capacity_available(img: "Image.Image") -> int:
    width, height = img.size
    total_pixels = width * height
    total_channels = total_pixels * 3
    total_bytes = total_channels // 8
    return max(0, total_bytes - HEADER_SIZE)


def _build_pnginfo(img: "Image.Image") -> "PngImagePlugin.PngInfo | None":
    try:
        from PIL import PngImagePlugin
        pnginfo = PngImagePlugin.PngInfo()
        for k, v in (img.info or {}).items():
            if isinstance(k, str) and isinstance(v, (str, bytes)):
                try:
                    if isinstance(v, bytes):
                        try:
                            v = v.decode("utf-8", errors="ignore")
                        except Exception:
                            continue
                    pnginfo.add_text(k, v)
                except Exception:
                    pass
        return pnginfo
    except Exception:
        return None


def embed_watermark(image_path: str | Path, payload: WatermarkPayload) -> tuple[bool, Optional[Path]]:
    _check_pil()
    final_path: Optional[Path] = None
    try:
        payload_str = payload.to_payload_string()
        data = _prepare_payload_data(payload_str)
        p = Path(image_path)
        suffix = p.suffix.lower()

        lossy_fmt = suffix in (".jpg", ".jpeg", ".webp")

        save_path = p
        if lossy_fmt:
            save_path = p.with_suffix(".png")

        with Image.open(image_path) as img:
            rgba = img.convert("RGBA")
            width, height = rgba.size
            pixels = list(rgba.getdata())

            capacity = _capacity_available(rgba)
            if len(data) > capacity:
                min_w = ((len(data) + HEADER_SIZE) * 8) // 3 + 1
                min_size = int(min_w ** 0.5) + 10
                new_size = max(width, min_size), max(height, min_size)
                rgba = rgba.resize(new_size, Image.Resampling.LANCZOS)
                width, height = rgba.size
                pixels = list(rgba.getdata())

            bits = _bytes_to_bits(data)
            new_pixels = _embed_bits_into_pixels(pixels, bits)

            new_img = Image.new("RGBA", (width, height))
            new_img.putdata(new_pixels)

            save_kwargs: dict = {}
            pnginfo = _build_pnginfo(img)
            if pnginfo:
                save_kwargs["pnginfo"] = pnginfo

            new_img.save(save_path, format="PNG", **save_kwargs)
            final_path = save_path.resolve()

            if lossy_fmt and save_path != p:
                try:
                    p.unlink()
                except Exception:
                    pass
        return True, final_path
    except Exception:
        return False, final_path


def extract_watermark(image_path: str | Path) -> Optional[WatermarkPayload]:
    _check_pil()
    try:
        with Image.open(image_path) as img:
            rgba = img.convert("RGBA")
            width, height = rgba.size
            pixels = list(rgba.getdata())

            header_bits_needed = HEADER_SIZE * 8
            header_bits = _extract_bits_from_pixels(pixels, header_bits_needed)
            if header_bits is None:
                return None
            header_bytes = _bits_to_bytes(header_bits)
            if len(header_bytes) < HEADER_SIZE:
                return None
            if header_bytes[:4] != HEADER_MAGIC:
                return None
            body_len = struct.unpack(">I", header_bytes[4:8])[0]
            if body_len <= 0:
                return None

            total_bits = (HEADER_SIZE + body_len) * 8
            all_bits = _extract_bits_from_pixels(pixels, total_bits)
            if all_bits is None:
                return None
            all_bytes = _bits_to_bytes(all_bits)
            payload_str = _parse_payload_data(all_bytes)
            if not payload_str:
                return None
            return WatermarkPayload.from_payload_string(payload_str)
    except Exception:
        return None


def watermark_present(image_path: str | Path) -> bool:
    return extract_watermark(image_path) is not None
