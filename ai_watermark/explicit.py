from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, PngImagePlugin
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

from .models import AIContentMark


EXPLICIT_KEY = "AI-Content-Mark"
SIDECAR_SUFFIX = ".aimark.json"


def _sidecar_path(path: str | Path) -> Path:
    p = Path(path)
    return p.parent / f"{p.name}{SIDECAR_SUFFIX}"


def _mark_from_metadata_dict(data: dict) -> Optional[AIContentMark]:
    raw = data.get(EXPLICIT_KEY) or data.get(EXPLICIT_KEY.lower())
    if not raw:
        return None
    if isinstance(raw, dict):
        return AIContentMark.from_dict(raw)
    try:
        return AIContentMark.from_json(raw)
    except Exception:
        return None


def read_image_explicit(path: str | Path) -> Optional[AIContentMark]:
    if not _PIL_AVAILABLE:
        return None
    try:
        with Image.open(path) as img:
            info = img.info or {}
            mark = _mark_from_metadata_dict(info)
            if mark:
                return mark
            exif = None
            try:
                exif_data = img.getexif()
                if exif_data:
                    exif = dict(exif_data.items())
            except Exception:
                exif = None
            if exif:
                for k, v in exif.items():
                    if isinstance(v, str) and (EXPLICIT_KEY in v or "AI-Content" in v):
                        try:
                            return AIContentMark.from_json(v)
                        except Exception:
                            pass
            return None
    except Exception:
        return None


def write_image_explicit(path: str | Path, mark: AIContentMark) -> bool:
    if not _PIL_AVAILABLE:
        return False
    try:
        mark_json = mark.to_json()
        p = Path(path)
        suffix = p.suffix.lower()
        with Image.open(path) as img:
            if suffix in (".png",):
                pnginfo = PngImagePlugin.PngInfo()
                for k, v in (img.info or {}).items():
                    if isinstance(v, (str, int, float, bytes)):
                        try:
                            pnginfo.add_text(str(k), str(v) if not isinstance(v, bytes) else v)
                        except Exception:
                            pass
                pnginfo.add_text(EXPLICIT_KEY, mark_json)
                img.save(p, format="PNG", pnginfo=pnginfo)
            elif suffix in (".jpg", ".jpeg"):
                exif = img.info.get("exif", b"")
                save_kwargs = {"format": "JPEG", "quality": "keep"}
                if exif:
                    save_kwargs["exif"] = exif
                new_info = dict(img.info or {})
                new_info[EXPLICIT_KEY] = mark_json
                save_kwargs["jpginfo"] = new_info
                from PIL import JpegImagePlugin
                JpegImagePlugin._getmp = lambda x: None
                img.save(p, **save_kwargs)
            else:
                new_info = dict(img.info or {})
                new_info[EXPLICIT_KEY] = mark_json
                img.save(p, **new_info)
        return True
    except Exception:
        return False


def read_sidecar_explicit(path: str | Path) -> Optional[AIContentMark]:
    sc = _sidecar_path(path)
    if not sc.is_file():
        return None
    try:
        with open(sc, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AIContentMark.from_dict(data)
    except Exception:
        return None


def write_sidecar_explicit(path: str | Path, mark: AIContentMark) -> bool:
    sc = _sidecar_path(path)
    try:
        with open(sc, "w", encoding="utf-8") as f:
            json.dump(mark.to_dict(), f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def read_text_explicit(path: str | Path) -> Optional[AIContentMark]:
    return read_sidecar_explicit(path)


def write_text_explicit(path: str | Path, mark: AIContentMark) -> bool:
    return write_sidecar_explicit(path, mark)


def sidecar_exists(path: str | Path) -> bool:
    return _sidecar_path(path).is_file()


def remove_sidecar(path: str | Path) -> bool:
    sc = _sidecar_path(path)
    if sc.is_file():
        try:
            os.remove(sc)
            return True
        except Exception:
            return False
    return False
