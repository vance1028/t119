from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .models import AIContentMark, WatermarkPayload
from . import explicit as ex
from . import lsb_stego as lsb
from . import zwc_stego as zwc


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".json", ".xml",
    ".yaml", ".yml", ".ini", ".cfg", ".conf", ".py", ".js", ".ts", ".html",
    ".htm", ".css", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go",
    ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".bash",
    ".zsh", ".bat", ".ps1", ".toml", ".tex",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}


def detect_file_type(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    elif suffix in TEXT_EXTENSIONS:
        return "text"
    elif suffix in AUDIO_EXTENSIONS:
        return "audio"
    elif suffix in VIDEO_EXTENSIONS:
        return "video"
    else:
        return "unknown"


class FileProcessor(ABC):
    file_type: str = "unknown"

    @abstractmethod
    def read_explicit(self, path: str | Path) -> Optional[AIContentMark]: ...

    @abstractmethod
    def write_explicit(self, path: str | Path, mark: AIContentMark) -> bool: ...

    @abstractmethod
    def extract_implicit(self, path: str | Path) -> Optional[WatermarkPayload]: ...

    @abstractmethod
    def embed_implicit(self, path: str | Path, payload: WatermarkPayload) -> Tuple[bool, Optional[Path]]: ...


class ImageProcessor(FileProcessor):
    file_type = "image"

    def read_explicit(self, path):
        return ex.read_image_explicit(path)

    def write_explicit(self, path, mark):
        return ex.write_image_explicit(path, mark)

    def extract_implicit(self, path):
        return lsb.extract_watermark(path)

    def embed_implicit(self, path, payload):
        return lsb.embed_watermark(path, payload)


class TextProcessor(FileProcessor):
    file_type = "text"

    def read_explicit(self, path):
        return ex.read_text_explicit(path)

    def write_explicit(self, path, mark):
        return ex.write_text_explicit(path, mark)

    def extract_implicit(self, path):
        return zwc.extract_watermark(path)

    def embed_implicit(self, path, payload):
        return zwc.embed_watermark(path, payload)


class PlaceholderProcessor(FileProcessor):
    def __init__(self, file_type: str):
        self.file_type = file_type

    def read_explicit(self, path):
        return None

    def write_explicit(self, path, mark):
        return False

    def extract_implicit(self, path):
        return None

    def embed_implicit(self, path, payload):
        return False, None


_processor_cache: dict[str, FileProcessor] = {}


def get_processor(file_type: str) -> FileProcessor:
    if file_type in _processor_cache:
        return _processor_cache[file_type]
    if file_type == "image":
        p = ImageProcessor()
    elif file_type == "text":
        p = TextProcessor()
    else:
        p = PlaceholderProcessor(file_type)
    _processor_cache[file_type] = p
    return p


def scan_directory(root: str | Path, exclude_sidecar: bool = True) -> list[tuple[Path, str]]:
    root = Path(root)
    results = []
    if not root.exists():
        return results
    sidecar_suffix = ex.SIDECAR_SUFFIX
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if exclude_sidecar and p.name.endswith(sidecar_suffix):
            continue
        if p.name.startswith("."):
            continue
        ft = detect_file_type(p)
        results.append((p, ft))
    results.sort(key=lambda x: str(x[0]))
    return results
