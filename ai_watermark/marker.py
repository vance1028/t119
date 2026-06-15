from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .models import (
    AIContentMark, WatermarkPayload, FileResult, ComplianceStatus,
)
from .processors import get_processor
from .fingerprint import compute_fingerprint


@dataclass
class MarkConfig:
    secret_key: bytes
    ai_tool: str = "unknown"
    is_ai_generated: bool = True
    dry_run: bool = False
    overwrite: bool = False
    mark_id_counter: int = 0
    progress_cb: Optional[Callable[[int, int, Path], None]] = None


@dataclass
class MarkResult:
    file_results: list[FileResult] = field(default_factory=list)

    def summary_counts(self) -> dict[str, int]:
        counts = {
            "marked": 0, "already_marked": 0, "skipped": 0,
            "failed": 0, "dry_run": 0,
        }
        for r in self.file_results:
            msgs = set(r.messages)
            if "dry_run" in msgs:
                counts["dry_run"] += 1
            elif "already_marked" in msgs:
                counts["already_marked"] += 1
            elif r.status == ComplianceStatus.ERROR:
                counts["failed"] += 1
            elif r.status == ComplianceStatus.SKIPPED:
                counts["skipped"] += 1
            elif "marked_ok" in msgs:
                counts["marked"] += 1
        return counts


def _marks_equivalent(m1: Optional[AIContentMark], m2: Optional[AIContentMark]) -> bool:
    if m1 is None or m2 is None:
        return False
    return (
        m1.is_ai_generated == m2.is_ai_generated
        and m1.ai_tool == m2.ai_tool
        and m1.content_fingerprint == m2.content_fingerprint
        and m1.schema_version == m2.schema_version
    )


def mark_file(
    path: str | Path,
    file_type: str,
    config: MarkConfig,
) -> FileResult:
    p = Path(path)
    result = FileResult(path=str(p.resolve()), file_type=file_type)
    if file_type not in ("image", "text"):
        result.status = ComplianceStatus.SKIPPED
        result.messages.append(f"unsupported_file_type:{file_type}")
        return result
    processor = get_processor(file_type)
    try:
        current_fp = compute_fingerprint(p, file_type)
        result.current_fingerprint = current_fp
        existing_explicit = processor.read_explicit(p)
        existing_implicit = processor.extract_implicit(p)
        hmac_ok = False
        if existing_implicit:
            hmac_ok = existing_implicit.verify_hmac(config.secret_key)
        target_mark = AIContentMark(
            is_ai_generated=config.is_ai_generated,
            ai_tool=config.ai_tool,
            content_fingerprint=current_fp,
        )
        implicit_matches = (
            existing_implicit is not None
            and hmac_ok
            and _marks_equivalent(existing_implicit.mark, target_mark)
        )
        explicit_matches = _marks_equivalent(existing_explicit, target_mark)
        if not config.overwrite and implicit_matches and explicit_matches:
            result.status = ComplianceStatus.COMPLIANT
            result.explicit_mark = existing_explicit
            result.implicit_payload = existing_implicit
            result.messages.append("already_marked")
            return result

        if config.dry_run:
            result.status = ComplianceStatus.COMPLIANT
            result.explicit_mark = target_mark
            result.messages.append("dry_run")
            result.messages.append("would_mark")
            return result

        new_payload = WatermarkPayload(mark=target_mark).sign(config.secret_key)
        impl_ok, final_path = processor.embed_implicit(p, new_payload)
        if not impl_ok:
            result.status = ComplianceStatus.ERROR
            result.messages.append("implicit_embed_failed")
            return result

        write_target = final_path or p
        if final_path and str(final_path.resolve()) != str(p.resolve()):
            result.messages.append(
                f"path_renamed:{p.name}->{final_path.name}"
            )
            result.path = str(final_path.resolve())

        expl_ok = processor.write_explicit(write_target, target_mark)
        if not expl_ok:
            result.status = ComplianceStatus.ERROR
            result.messages.append("explicit_write_failed")
            return result
        result.explicit_mark = target_mark
        result.implicit_payload = new_payload
        result.status = ComplianceStatus.COMPLIANT
        result.messages.append("marked_ok")
        return result
    except Exception as e:
        result.status = ComplianceStatus.ERROR
        result.messages.append(f"exception:{type(e).__name__}:{e}")
        return result


def mark_directory(
    root: str | Path,
    config: MarkConfig,
    files: Optional[list[tuple[Path, str]]] = None,
) -> MarkResult:
    from .processors import scan_directory
    if files is None:
        files = scan_directory(root)
    result = MarkResult()
    total = len(files)
    for idx, (p, ft) in enumerate(files, start=1):
        if config.progress_cb:
            config.progress_cb(idx, total, p)
        fr = mark_file(p, ft, config)
        result.file_results.append(fr)
    return result
