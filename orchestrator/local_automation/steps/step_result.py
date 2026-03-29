"""Typed result objects for step execution and verification.

Every step produces a StepResult.  Critical steps must also produce
VerificationEvidence proving the UI action succeeded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class VerificationSpec:
    """Declares *how* a step's success should be verified.

    At least one verification method must be specified.  The engine
    tries them in priority order: OCR -> template -> pixel_diff.

    OCR configuration fields control preprocessing and Tesseract
    settings for LabVIEW's custom UI controls.
    """
    # --- Primary verification methods ---
    ocr_region: tuple[int, int, int, int] | None = None
    expected_text: str = ""
    template_name: str = ""
    template_threshold: float = 0.70
    title_hint: str = ""
    pixel_diff_region: tuple[int, int, int, int] | None = None
    min_diff_pct: float = 1.0

    # --- OCR configuration ---
    ocr_psm: int = 7
    ocr_char_whitelist: str = ""
    ocr_scale_factor: int = 5
    ocr_threshold: int = 100
    ocr_invert: bool = True
    ocr_normalize_digits: bool = False

    def has_any_method(self) -> bool:
        return bool(
            self.ocr_region
            or self.template_name
            or self.title_hint
            or self.pixel_diff_region
        )


@dataclass
class VerificationEvidence:
    """Concrete proof that a step's action succeeded or failed.

    Produced by the verification pipeline after executing a step.
    Stored as JSON in the per-step artifact folder.
    """
    method: str  # "ocr", "template", "pixel_diff", "title_check", "none"
    expected: str = ""
    actual: str = ""
    match: bool = False
    confidence: float = 0.0
    screenshot_path: str = ""
    region: tuple[int, int, int, int] | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "method": self.method,
            "expected": self.expected,
            "actual": self.actual,
            "match": self.match,
            "confidence": self.confidence,
        }
        if self.screenshot_path:
            d["screenshot_path"] = self.screenshot_path
        if self.region:
            d["region"] = list(self.region)
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class StepResult:
    """Full result of executing a single automation step.

    Returned by BaseStep.execute() and enriched by the engine with
    verification evidence and recovery info.

    For multi-control steps (e.g. s05_freq_channel with 5 fields),
    *field_evidences* holds per-field verification while
    *verification_evidence* holds the combined/overall result.
    """
    ok: bool
    step_name: str
    attempts: int = 1
    verified: bool = False
    elapsed_sec: float = 0.0
    error: str = ""
    details: dict = field(default_factory=dict)
    artifact_paths: list[str] = field(default_factory=list)
    verification_evidence: Optional[VerificationEvidence] = None
    field_evidences: dict[str, VerificationEvidence] = field(default_factory=dict)
    recovery_actions: list[str] = field(default_factory=list)

    def all_fields_verified(self) -> bool:
        """True if every entry in field_evidences matched."""
        if not self.field_evidences:
            return self.verified
        return all(ev.match for ev in self.field_evidences.values())

    def failed_fields(self) -> list[str]:
        """Return names of fields whose verification failed."""
        return [k for k, ev in self.field_evidences.items() if not ev.match]

    def to_dict(self) -> dict:
        d: dict = {
            "ok": self.ok,
            "step_name": self.step_name,
            "attempts": self.attempts,
            "verified": self.verified,
            "elapsed_sec": round(self.elapsed_sec, 3),
        }
        if self.error:
            d["error"] = self.error
        if self.details:
            d["details"] = self.details
        if self.artifact_paths:
            d["artifact_paths"] = self.artifact_paths
        if self.verification_evidence:
            d["verification_evidence"] = self.verification_evidence.to_dict()
        if self.field_evidences:
            d["field_evidences"] = {
                k: ev.to_dict() for k, ev in self.field_evidences.items()
            }
        if self.recovery_actions:
            d["recovery_actions"] = self.recovery_actions
        return d
