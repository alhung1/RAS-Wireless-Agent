"""Strict pre-execution validation.

run_preflight() checks every precondition that can be verified before
any GUI interaction.  If any required check fails the engine refuses
to start, providing clear error messages for each failure.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import RunConfig, StepContext
    from orchestrator.local_automation.products.base import ProductBase


@dataclass
class PreflightCheck:
    """Result of a single preflight check."""
    name: str
    passed: bool
    required: bool = True
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "required": self.required,
            "message": self.message,
        }


@dataclass
class PreflightResult:
    """Aggregated result of all preflight checks."""
    passed: bool = True
    checks: list[PreflightCheck] = field(default_factory=list)

    def add(self, check: PreflightCheck) -> None:
        self.checks.append(check)
        if check.required and not check.passed:
            self.passed = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "failed_required": [
                c.to_dict() for c in self.checks
                if c.required and not c.passed
            ],
        }

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        failed_req = [c for c in self.checks if c.required and not c.passed]
        lines = [f"Preflight: {passed}/{total} checks passed"]
        for c in failed_req:
            lines.append(f"  FAIL [required]: {c.name} -- {c.message}")
        for c in self.checks:
            if not c.required and not c.passed:
                lines.append(f"  WARN [optional]: {c.name} -- {c.message}")
        return "\n".join(lines)


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def run_preflight(
    config: "RunConfig",
    product: "ProductBase",
    ctx: "StepContext",
) -> PreflightResult:
    """Execute all preflight checks.  Returns PreflightResult."""
    result = PreflightResult()

    # 1. Product existence
    result.add(PreflightCheck(
        name="product_loaded",
        passed=product is not None,
        message=f"Product adapter: {product.name}" if product else "No product adapter",
    ))

    # 2. Band supported by product
    if product:
        band_ok = config.band in product.supported_bands()
        result.add(PreflightCheck(
            name="band_supported",
            passed=band_ok,
            message=(f"Band {config.band!r} supported"
                     if band_ok
                     else f"Band {config.band!r} not in {product.supported_bands()}"),
        ))

    # 3. Mode valid for band
    if product and config.band in product.supported_bands():
        valid_modes = product.valid_modes(config.band)
        mode_ok = config.mode in valid_modes
        result.add(PreflightCheck(
            name="mode_valid",
            passed=mode_ok,
            message=(f"Mode {config.mode!r} valid for {config.band}"
                     if mode_ok
                     else f"Mode {config.mode!r} not in {valid_modes}"),
        ))

    # 4. Channel valid for band
    if product and config.band in product.supported_bands():
        channel_field = {
            "2.4G": config.rf_channel_2g,
            "5G": config.rf_channel_5g,
            "6G": config.rf_channel_6g,
        }.get(config.band, "0")
        if channel_field != "0":
            valid_ch = product.valid_channels(config.band)
            ch_ok = channel_field in valid_ch
            result.add(PreflightCheck(
                name="channel_valid",
                passed=ch_ok,
                message=(f"Channel {channel_field!r} valid for {config.band}"
                         if ch_ok
                         else f"Channel {channel_field!r} not in {valid_ch}"),
            ))

    # 5. Required fields non-empty
    required_fields = [
        ("ap_name", config.ap_name),
        ("client_name", config.client_name),
        ("band", config.band),
        ("mode", config.mode),
        ("design_stage", config.design_stage),
        ("region", config.region),
    ]
    for fname, fval in required_fields:
        result.add(PreflightCheck(
            name=f"field_{fname}",
            passed=bool(fval and fval.strip()),
            message=f"{fname}={fval!r}" if fval else f"{fname} is empty",
        ))

    # 6. Template assets exist
    required_templates = [
        "orange_arrow.png",
        "green_ok_button.png",
        "done_button.png",
    ]
    for tpl in required_templates:
        tpl_path = TEMPLATES_DIR / tpl
        result.add(PreflightCheck(
            name=f"template_{tpl}",
            passed=tpl_path.is_file(),
            required=False,
            message=(f"Found {tpl_path}" if tpl_path.is_file()
                     else f"Missing {tpl_path}"),
        ))

    # 7. AP / Client folder paths exist
    if product:
        ap_folder = product.ap_folder()
        client_folder = product.client_folder()
        result.add(PreflightCheck(
            name="ap_folder_exists",
            passed=os.path.isdir(ap_folder),
            required=not ctx.dry_run,
            message=f"AP folder: {ap_folder}",
        ))
        result.add(PreflightCheck(
            name="client_folder_exists",
            passed=os.path.isdir(client_folder),
            required=not ctx.dry_run,
            message=f"Client folder: {client_folder}",
        ))

    # 8. LabVIEW exe exists (unless dry-run)
    result.add(PreflightCheck(
        name="exe_exists",
        passed=os.path.isfile(config.exe_path),
        required=not ctx.dry_run,
        message=f"EXE: {config.exe_path}",
    ))

    # 9. OCR availability (optional -- warning only)
    result.add(PreflightCheck(
        name="ocr_available",
        passed=ctx.ocr_available,
        required=False,
        message=("pytesseract available"
                 if ctx.ocr_available
                 else "pytesseract unavailable -- OCR verification disabled, "
                      "pixel-diff fallback will be used"),
    ))

    # 10. Artifacts directory writable
    try:
        os.makedirs(ctx.artifacts_dir, exist_ok=True)
        test_file = os.path.join(ctx.artifacts_dir, ".preflight_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        result.add(PreflightCheck(
            name="artifacts_writable",
            passed=True,
            message=f"Artifacts dir: {ctx.artifacts_dir}",
        ))
    except Exception as exc:
        result.add(PreflightCheck(
            name="artifacts_writable",
            passed=False,
            message=f"Cannot write to {ctx.artifacts_dir}: {exc}",
        ))

    return result
