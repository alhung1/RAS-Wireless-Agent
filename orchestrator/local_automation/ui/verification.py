"""Verification pipeline -- execute a VerificationSpec, return structured
VerificationEvidence.

Product-agnostic: accepts a generic VerificationSpec and tries each
verification method in priority order (OCR -> template -> pixel_diff).
"""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.screen_utils import capture_window
from orchestrator.local_automation.steps.step_result import (
    VerificationEvidence,
    VerificationSpec,
)
from orchestrator.local_automation.ui.detection import (
    ocr_available,
    read_ocr_from_image,
    pixel_diff,
    template_match_score,
)

logger = get_logger("ui.verification")


_LV_DIGIT_MAP = str.maketrans({
    "O": "0", "o": "0",
    "A": "4",
    "F": "6", "f": "6",
    "I": "1", "l": "1",
    "S": "5", "s": "5",
    "B": "8", "b": "8",
    "Z": "2", "z": "2",
    "T": "7",
    ")": "",  "(": "", ".": "", ",": "",
    " ": "", "'": "", '"': "", "\\": "",
    "/": "", "|": "", "!": "", "?": "",
})

_LV_AMBIGUOUS = {"a": ["9", "4"], "Q": ["0", "9"], "q": ["0", "9"],
                  "G": ["6", "9"], "g": ["9", "6"]}


def _normalize_digits(text: str, expected: str = "") -> str:
    """Normalize LabVIEW font OCR misreads for digit-only fields.

    Handles ambiguous characters (Q could be 0 or 9, a could be 9 or 4)
    by trying all interpretations and picking the one matching *expected*.
    Falls back to the first interpretation if no match.
    """
    base = text.translate(_LV_DIGIT_MAP)

    ambig_positions = []
    for i, ch in enumerate(base):
        if ch in _LV_AMBIGUOUS:
            ambig_positions.append((i, ch))

    if not ambig_positions:
        return base

    if not expected:
        result = list(base)
        for i, ch in ambig_positions:
            result[i] = _LV_AMBIGUOUS[ch][0]
        return "".join(result)

    expected_clean = expected.strip().replace(" ", "")

    def _try(result, pos_idx):
        if pos_idx >= len(ambig_positions):
            candidate = "".join(result)
            return candidate if expected_clean in candidate or candidate == expected_clean else None
        i, ch = ambig_positions[pos_idx]
        for replacement in _LV_AMBIGUOUS[ch]:
            result[i] = replacement
            hit = _try(result, pos_idx + 1)
            if hit:
                return hit
        result[i] = _LV_AMBIGUOUS[ch][0]
        return None

    result = list(base)
    hit = _try(result, 0)
    if hit:
        return hit

    for i, ch in ambig_positions:
        result[i] = _LV_AMBIGUOUS[ch][0]
    return "".join(result)


def _run_ocr_with_spec(
    img: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    spec: VerificationSpec,
) -> str:
    """Run OCR on a region using the spec's LabVIEW-optimized settings.

    Pipeline: crop -> scale -> grayscale -> threshold -> invert -> border -> OCR.
    """
    import cv2

    try:
        import pytesseract
    except ImportError:
        return ""

    x2 = min(x + w, img.shape[1])
    y2 = min(y + h, img.shape[0])
    x1, y1 = max(x, 0), max(y, 0)
    region = img[y1:y2, x1:x2]
    if region.size == 0:
        return ""

    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

    sf = spec.ocr_scale_factor
    if sf > 1:
        gray = cv2.resize(gray, None, fx=sf, fy=sf, interpolation=cv2.INTER_CUBIC)

    if spec.ocr_invert:
        _, bw = cv2.threshold(gray, spec.ocr_threshold, 255, cv2.THRESH_BINARY_INV)
    else:
        _, bw = cv2.threshold(gray, spec.ocr_threshold, 255, cv2.THRESH_BINARY)

    bordered = cv2.copyMakeBorder(bw, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=0)

    config_parts = [f"--psm {spec.ocr_psm}"]
    if spec.ocr_char_whitelist:
        config_parts.append(f"-c tessedit_char_whitelist={spec.ocr_char_whitelist}")
    config_str = " ".join(config_parts)

    try:
        text = pytesseract.image_to_string(bordered, config=config_str).strip()
        return text
    except Exception as exc:
        logger.warning("OCR with spec failed: %s", exc)
        return ""


def execute_verification(
    hwnd: int,
    spec: VerificationSpec,
    before_img: Optional[np.ndarray] = None,
    artifacts_dir: str = "",
) -> VerificationEvidence:
    """Execute a VerificationSpec and return structured evidence.

    Tries methods in priority order:
      1. OCR (if ocr_region is set and OCR is available)
      2. Template match (if template_name is set)
      3. Title hint (if title_hint is set)
      4. Pixel diff (if pixel_diff_region is set and before_img provided)
      5. Returns method="none" if no method could be executed

    The *first matching method* populates the evidence.  If OCR finds
    a match, template/pixel_diff are skipped.
    """
    if not spec.has_any_method():
        return VerificationEvidence(method="none", match=True,
                                    detail="No verification spec defined")

    try:
        after_img = capture_window(hwnd)
    except Exception as exc:
        return VerificationEvidence(
            method="capture_failed", match=False,
            detail=f"Could not capture window: {exc}",
        )

    screenshot_path = ""
    if artifacts_dir:
        try:
            os.makedirs(artifacts_dir, exist_ok=True)
            import cv2
            path = os.path.join(artifacts_dir, "verify_screenshot.png")
            cv2.imwrite(path, after_img)
            screenshot_path = path
        except Exception:
            pass

    # Method 1: OCR (uses spec's LabVIEW-optimized configuration)
    # For numeric fields with normalize_digits, tries multiple thresholds
    # since LabVIEW's font produces different misreads at different levels.
    if spec.ocr_region and ocr_available():
        x, y, w, h = spec.ocr_region
        expected = spec.expected_text.strip()
        expected_nospace = expected.replace(" ", "")

        thresholds = [spec.ocr_threshold]
        if spec.ocr_normalize_digits:
            thresholds = [40, 60, 80, spec.ocr_threshold]
            thresholds = sorted(set(thresholds))

        best_text = ""
        best_match = False
        for thresh in thresholds:
            trial_spec = VerificationSpec(
                ocr_region=spec.ocr_region,
                expected_text=spec.expected_text,
                ocr_psm=spec.ocr_psm,
                ocr_char_whitelist=spec.ocr_char_whitelist,
                ocr_scale_factor=spec.ocr_scale_factor,
                ocr_threshold=thresh,
                ocr_invert=spec.ocr_invert,
                ocr_normalize_digits=spec.ocr_normalize_digits,
            )
            raw = _run_ocr_with_spec(after_img, x, y, w, h, trial_spec)
            clean = raw.strip()
            if spec.ocr_normalize_digits:
                clean = _normalize_digits(clean, expected=expected)
            nospace = clean.replace(" ", "")
            match = (expected_nospace.lower() in nospace.lower()
                     or nospace.lower() == expected_nospace.lower())
            if not best_text or match:
                best_text = raw
                best_match = match
            if match:
                break

        return VerificationEvidence(
            method="ocr",
            expected=expected,
            actual=best_text,
            match=best_match,
            confidence=1.0 if best_match else 0.0,
            screenshot_path=screenshot_path,
            region=spec.ocr_region,
            detail=f"psm={spec.ocr_psm} thresholds={thresholds} "
                   f"norm_dig={spec.ocr_normalize_digits}",
        )

    # Method 2: Template match
    if spec.template_name:
        score = template_match_score(after_img, spec.template_name)
        match = score >= spec.template_threshold
        return VerificationEvidence(
            method="template",
            expected=spec.template_name,
            actual=f"score={score:.3f}",
            match=match,
            confidence=score,
            screenshot_path=screenshot_path,
        )

    # Method 3: Title hint
    if spec.title_hint:
        import ctypes
        user32 = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        match = spec.title_hint.lower() in title.lower()
        return VerificationEvidence(
            method="title_check",
            expected=spec.title_hint,
            actual=title,
            match=match,
            confidence=1.0 if match else 0.0,
            screenshot_path=screenshot_path,
        )

    # Method 4: Pixel diff (requires before_img)
    if spec.pixel_diff_region and before_img is not None:
        x, y, w, h = spec.pixel_diff_region
        diff_pct, _ = pixel_diff(before_img, after_img, x, y, w, h)
        if diff_pct >= spec.min_diff_pct:
            return VerificationEvidence(
                method="pixel_diff",
                expected=spec.expected_text or f">={spec.min_diff_pct}% change",
                actual=f"{diff_pct:.1f}% diff",
                match=True,
                confidence=diff_pct / 100.0,
                screenshot_path=screenshot_path,
                region=spec.pixel_diff_region,
                detail=f"Region changed by {diff_pct:.1f}%",
            )
        if diff_pct == 0.0:
            return VerificationEvidence(
                method="pixel_diff_inconclusive",
                expected=spec.expected_text or f">={spec.min_diff_pct}% change",
                actual="0.0% diff",
                match=True,
                confidence=0.0,
                screenshot_path=screenshot_path,
                region=spec.pixel_diff_region,
                detail="No pixel change detected; field may already contain "
                       "expected value. Action performed but value unverifiable "
                       "without OCR.",
            )
        return VerificationEvidence(
            method="pixel_diff",
            expected=spec.expected_text or f">={spec.min_diff_pct}% change",
            actual=f"{diff_pct:.1f}% diff",
            match=False,
            confidence=diff_pct / 100.0,
            screenshot_path=screenshot_path,
            region=spec.pixel_diff_region,
            detail=f"Region only {diff_pct:.1f}% changed "
                   f"(need >={spec.min_diff_pct}%)",
        )

    # Method 5: OCR region specified but OCR not available, pixel_diff fallback
    if spec.ocr_region and not ocr_available() and before_img is not None:
        x, y, w, h = spec.ocr_region
        diff_pct, _ = pixel_diff(before_img, after_img, x, y, w, h)
        if diff_pct >= spec.min_diff_pct:
            return VerificationEvidence(
                method="pixel_diff",
                expected=spec.expected_text or f">={spec.min_diff_pct}% change",
                actual=f"{diff_pct:.1f}% diff (OCR unavailable)",
                match=True,
                confidence=diff_pct / 100.0,
                screenshot_path=screenshot_path,
                region=spec.ocr_region,
                detail="OCR unavailable; pixel_diff confirmed change",
            )
        return VerificationEvidence(
            method="pixel_diff_inconclusive",
            expected=spec.expected_text or "value verification",
            actual=f"{diff_pct:.1f}% diff (OCR unavailable)",
            match=True,
            confidence=0.0,
            screenshot_path=screenshot_path,
            region=spec.ocr_region,
            detail="OCR unavailable; pixel_diff shows no change. "
                   "Action performed but value unverifiable without OCR. "
                   "Inspect screenshots for manual confirmation.",
        )

    return VerificationEvidence(
        method="none", match=False,
        detail="No verification method could be executed "
               "(OCR unavailable, no template, no before_img for pixel_diff)",
    )


def save_evidence(
    evidence: VerificationEvidence,
    artifacts_dir: str,
    step_name: str,
) -> str:
    """Save verification evidence as JSON.  Returns absolute file path."""
    artifacts_dir = os.path.abspath(artifacts_dir)
    os.makedirs(artifacts_dir, exist_ok=True)
    path = os.path.join(artifacts_dir, f"verify_{step_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence.to_dict(), f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Polling helpers (condition-based waits, not blind sleeps)
# ---------------------------------------------------------------------------

import time


def poll_until(
    condition_fn,
    timeout: float = 10.0,
    interval: float = 0.5,
    desc: str = "condition",
) -> bool:
    """Poll until condition_fn() returns truthy, or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    logger.warning("Poll timeout after %.1fs waiting for %s", timeout, desc,
                   extra={"action": "poll", "step": desc})
    return False


def poll_for_window(
    wm,
    title_hint: str,
    timeout: float = 10.0,
    interval: float = 0.5,
) -> int | None:
    """Poll until a window matching *title_hint* appears.

    *wm* is a WindowManager instance.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = wm.find_vi_window(title_hint, timeout=0.3)
        if hwnd:
            return hwnd
        time.sleep(interval)
    return None


def poll_window_gone(
    hwnd: int,
    timeout: float = 10.0,
    interval: float = 0.5,
) -> bool:
    """Poll until *hwnd* is no longer visible."""
    import ctypes
    user32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not user32.IsWindowVisible(hwnd):
            return True
        time.sleep(interval)
    return False
