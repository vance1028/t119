from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional, Tuple

from .models import WatermarkPayload


ZWSP = "\u200B"
ZWNJ = "\u200C"
ZWJ = "\u200D"
ZWNBSP = "\uFEFF"
INVIS_SEP = "\u2063"

_ENCODING_CHARS = [ZWSP, ZWNJ, ZWJ, INVIS_SEP]
_MAGIC_BEGIN = "\u2060"
_MAGIC_END = "\u2061"
_HEADER_MAGIC = "AWM1"


def _str_to_base64(s: str) -> str:
    raw = s.encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _base64_to_str(b64: str) -> Optional[str]:
    try:
        return base64.b64decode(b64.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def _char_to_zwc(c: str) -> str:
    ord_val = ord(c)
    if ord_val < 128:
        bits = f"{ord_val:08b}"
    else:
        bits = f"{ord_val:016b}"
    out = []
    for i in range(0, len(bits), 2):
        pair = bits[i:i + 2]
        idx = int(pair, 2)
        out.append(_ENCODING_CHARS[idx])
    prefix_len = 4 if ord_val < 128 else 8
    return _ENCODING_CHARS[0] * (prefix_len - len(out)) + "".join(out)


def _zwc_to_char(zwc: str) -> Optional[str]:
    if len(zwc) == 4:
        bits_total = 8
    elif len(zwc) == 8:
        bits_total = 16
    else:
        return None
    bits = []
    for z in zwc:
        if z not in _ENCODING_CHARS:
            return None
        v = _ENCODING_CHARS.index(z)
        bits.append(f"{v:02b}")
    bit_str = "".join(bits)
    if len(bit_str) != bits_total:
        return None
    try:
        return chr(int(bit_str, 2))
    except Exception:
        return None


def _encode_payload(payload_str: str) -> str:
    wrapped = _HEADER_MAGIC + payload_str
    b64 = _str_to_base64(wrapped)
    zwc_parts = []
    for c in b64:
        zwc_parts.append(_char_to_zwc(c))
    encoded = "".join(zwc_parts)
    return _MAGIC_BEGIN + encoded + _MAGIC_END


def _decode_payload(zwc: str) -> Optional[str]:
    if not (zwc.startswith(_MAGIC_BEGIN) and zwc.endswith(_MAGIC_END)):
        return None
    inner = zwc[len(_MAGIC_BEGIN):-len(_MAGIC_END)]
    if not inner:
        return None
    chars = []
    i = 0
    while i < len(inner):
        piece = inner[i:i + 4]
        if len(piece) < 4:
            return None
        if inner[i] not in _ENCODING_CHARS:
            return None
        decoded_char = _zwc_to_char(piece)
        if decoded_char is not None:
            chars.append(decoded_char)
            i += 4
            continue
        piece = inner[i:i + 8]
        if len(piece) < 8:
            return None
        decoded_char = _zwc_to_char(piece)
        if decoded_char is None:
            return None
        chars.append(decoded_char)
        i += 8
    b64_str = "".join(chars)
    wrapped = _base64_to_str(b64_str)
    if not wrapped or not wrapped.startswith(_HEADER_MAGIC):
        return None
    return wrapped[len(_HEADER_MAGIC):]


def _split_text_body_and_zwc(text: str) -> Tuple[str, Optional[str]]:
    if _MAGIC_BEGIN in text and _MAGIC_END in text:
        idx_b = text.rfind(_MAGIC_BEGIN)
        idx_e = text.rfind(_MAGIC_END)
        if idx_e > idx_b:
            body = text[:idx_b]
            zwc = text[idx_b:idx_e + len(_MAGIC_END)]
            tail = text[idx_e + len(_MAGIC_END):]
            return body + tail, zwc
    return text, None


def embed_watermark(text_path: str | Path, payload: WatermarkPayload) -> tuple[bool, Optional[Path]]:
    p = Path(text_path)
    final_path: Optional[Path] = None
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            original = f.read()

        body, existing_zwc = _split_text_body_and_zwc(original)
        payload_str = payload.to_payload_string()
        new_zwc = _encode_payload(payload_str)

        if not body.endswith("\n"):
            body = body + "\n"
        new_text = body + new_zwc

        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
        final_path = p.resolve()
        return True, final_path
    except Exception:
        return False, final_path


def extract_watermark(text_path: str | Path) -> Optional[WatermarkPayload]:
    try:
        p = Path(text_path)
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        _, zwc = _split_text_body_and_zwc(text)
        if not zwc:
            return None
        payload_str = _decode_payload(zwc)
        if not payload_str:
            return None
        return WatermarkPayload.from_payload_string(payload_str)
    except Exception:
        return None


def watermark_present(text_path: str | Path) -> bool:
    return extract_watermark(text_path) is not None
