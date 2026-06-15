from __future__ import annotations

import json
import hmac
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any


SCHEMA_VERSION = "1.0"
WATERMARK_MAGIC = "AWM1"


@dataclass
class AIContentMark:
    is_ai_generated: bool = True
    ai_tool: str = "unknown"
    generated_at: str = ""
    content_fingerprint: str = ""
    mark_id: str = ""
    schema_version: str = SCHEMA_VERSION
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()
        if not self.mark_id:
            self.mark_id = hashlib.sha256(
                f"{self.ai_tool}|{self.generated_at}|{self.content_fingerprint}".encode()
            ).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIContentMark":
        known = {
            k: data[k] for k in data
            if k in {"is_ai_generated", "ai_tool", "generated_at",
                     "content_fingerprint", "mark_id", "schema_version"}
        }
        extra = {k: v for k, v in data.items() if k not in known}
        obj = cls(**known)
        obj.extra = extra
        return obj

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "AIContentMark":
        return cls.from_dict(json.loads(s))

    def fingerprint_for_hmac(self) -> bytes:
        parts = [
            WATERMARK_MAGIC,
            "1" if self.is_ai_generated else "0",
            self.ai_tool,
            self.generated_at,
            self.content_fingerprint,
            self.mark_id,
            self.schema_version,
        ]
        return "|".join(parts).encode("utf-8")


@dataclass
class WatermarkPayload:
    mark: AIContentMark
    hmac_digest: str = ""

    def compute_hmac(self, secret_key: bytes) -> str:
        msg = self.mark.fingerprint_for_hmac()
        return hmac.new(secret_key, msg, hashlib.sha256).hexdigest()

    def sign(self, secret_key: bytes) -> "WatermarkPayload":
        self.hmac_digest = self.compute_hmac(secret_key)
        return self

    def verify_hmac(self, secret_key: bytes) -> bool:
        if not self.hmac_digest:
            return False
        expected = self.compute_hmac(secret_key)
        return hmac.compare_digest(expected, self.hmac_digest)

    def to_payload_string(self) -> str:
        data = {
            "m": self.mark.to_dict(),
            "h": self.hmac_digest,
            "v": WATERMARK_MAGIC,
        }
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_payload_string(cls, s: str) -> Optional["WatermarkPayload"]:
        try:
            data = json.loads(s)
            if data.get("v") != WATERMARK_MAGIC:
                return None
            mark = AIContentMark.from_dict(data["m"])
            obj = cls(mark=mark, hmac_digest=data.get("h", ""))
            return obj
        except Exception:
            return None


class ComplianceStatus:
    COMPLIANT = "compliant"
    MISSING_BOTH = "missing_both"
    MISSING_EXPLICIT = "missing_explicit"
    MISSING_IMPLICIT = "missing_implicit"
    MISMATCH = "mismatch"
    HMAC_INVALID = "hmac_invalid"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class FileResult:
    path: str
    file_type: str
    status: str = ComplianceStatus.SKIPPED
    explicit_mark: Optional[AIContentMark] = None
    implicit_payload: Optional[WatermarkPayload] = None
    messages: list[str] = field(default_factory=list)
    current_fingerprint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "file_type": self.file_type,
            "status": self.status,
            "explicit_mark": self.explicit_mark.to_dict() if self.explicit_mark else None,
            "implicit_mark": self.implicit_payload.mark.to_dict() if self.implicit_payload else None,
            "hmac_valid": self.implicit_payload is not None,
            "messages": self.messages,
            "current_fingerprint": self.current_fingerprint,
        }


@dataclass
class ReportSummary:
    total: int = 0
    compliant: int = 0
    missing_both: int = 0
    missing_explicit: int = 0
    missing_implicit: int = 0
    mismatch: int = 0
    hmac_invalid: int = 0
    fingerprint_mismatch: int = 0
    error: int = 0
    skipped: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
