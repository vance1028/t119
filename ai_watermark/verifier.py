from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .models import (
    AIContentMark, WatermarkPayload, FileResult, ComplianceStatus,
    ReportSummary,
)
from .processors import get_processor
from .fingerprint import compute_fingerprint


@dataclass
class VerifyConfig:
    secret_key: bytes
    progress_cb: Optional[Callable[[int, int, Path], None]] = None


@dataclass
class VerifyResult:
    file_results: list[FileResult] = field(default_factory=list)

    def summary(self) -> ReportSummary:
        s = ReportSummary()
        for r in self.file_results:
            s.total += 1
            status = r.status
            if status == ComplianceStatus.COMPLIANT:
                s.compliant += 1
            elif status == ComplianceStatus.MISSING_BOTH:
                s.missing_both += 1
            elif status == ComplianceStatus.MISSING_EXPLICIT:
                s.missing_explicit += 1
            elif status == ComplianceStatus.MISSING_IMPLICIT:
                s.missing_implicit += 1
            elif status == ComplianceStatus.MISMATCH:
                s.mismatch += 1
            elif status == ComplianceStatus.HMAC_INVALID:
                s.hmac_invalid += 1
            elif status == ComplianceStatus.FINGERPRINT_MISMATCH:
                s.fingerprint_mismatch += 1
            elif status == ComplianceStatus.ERROR:
                s.error += 1
            elif status == ComplianceStatus.SKIPPED:
                s.skipped += 1
        return s

    def grouped(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {
            "compliant": [], "missing_both": [], "missing_explicit": [],
            "missing_implicit": [], "mismatch": [], "hmac_invalid": [],
            "fingerprint_mismatch": [], "error": [], "skipped": [],
        }
        for r in self.file_results:
            key = r.status
            if key in groups:
                groups[key].append(r.path)
        return groups

    def has_issues(self) -> bool:
        s = self.summary()
        issues = (
            s.missing_both + s.missing_explicit + s.missing_implicit
            + s.mismatch + s.hmac_invalid + s.fingerprint_mismatch + s.error
        )
        return issues > 0


def _marks_consistent(m1: AIContentMark, m2: AIContentMark) -> bool:
    return (
        m1.is_ai_generated == m2.is_ai_generated
        and m1.ai_tool == m2.ai_tool
        and m1.mark_id == m2.mark_id
        and m1.content_fingerprint == m2.content_fingerprint
        and m1.schema_version == m2.schema_version
    )


def verify_file(
    path: str | Path,
    file_type: str,
    config: VerifyConfig,
) -> FileResult:
    p = Path(path)
    result = FileResult(path=str(p), file_type=file_type)
    if file_type not in ("image", "text"):
        result.status = ComplianceStatus.SKIPPED
        result.messages.append(f"unsupported_file_type:{file_type}")
        return result
    processor = get_processor(file_type)
    try:
        current_fp = compute_fingerprint(p, file_type)
        result.current_fingerprint = current_fp
        explicit = processor.read_explicit(p)
        implicit = processor.extract_implicit(p)

        result.explicit_mark = explicit
        result.implicit_payload = implicit

        explicit_missing = explicit is None
        implicit_missing = implicit is None

        if explicit_missing and implicit_missing:
            result.status = ComplianceStatus.MISSING_BOTH
            result.messages.append("no_explicit_no_implicit")
            return result
        if explicit_missing and not implicit_missing:
            result.status = ComplianceStatus.MISSING_EXPLICIT
            result.messages.append("missing_explicit_mark")
            return result
        if implicit_missing and not explicit_missing:
            result.status = ComplianceStatus.MISSING_IMPLICIT
            result.messages.append("missing_implicit_watermark")
            return result

        assert implicit is not None and explicit is not None
        if not implicit.verify_hmac(config.secret_key):
            result.status = ComplianceStatus.HMAC_INVALID
            result.messages.append("hmac_verification_failed")
            return result

        if not _marks_consistent(explicit, implicit.mark):
            result.status = ComplianceStatus.MISMATCH
            result.messages.append("explicit_implicit_mismatch")
            return result

        if explicit.content_fingerprint != current_fp:
            result.status = ComplianceStatus.FINGERPRINT_MISMATCH
            result.messages.append("fingerprint_changed_content_modified")
            return result

        result.status = ComplianceStatus.COMPLIANT
        result.messages.append("fully_compliant")
        return result

    except Exception as e:
        result.status = ComplianceStatus.ERROR
        result.messages.append(f"exception:{type(e).__name__}:{e}")
        return result


def verify_directory(
    root: str | Path,
    config: VerifyConfig,
    files: Optional[list[tuple[Path, str]]] = None,
) -> VerifyResult:
    from .processors import scan_directory
    if files is None:
        files = scan_directory(root)
    result = VerifyResult()
    total = len(files)
    for idx, (p, ft) in enumerate(files, start=1):
        if config.progress_cb:
            config.progress_cb(idx, total, p)
        fr = verify_file(p, ft, config)
        result.file_results.append(fr)
    return result
