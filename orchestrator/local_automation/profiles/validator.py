"""Profile validation (dry-run mode).

Validates profile schemas and semantic rules without touching the GUI.
Used by preflight and by the standalone validate_profiles.py script.
"""
from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from orchestrator.local_automation.profiles.schema import (
    ProductProfileData,
    TestProfile,
)
from orchestrator.local_automation.products.base import ProductBase


def validate_test_profile(
    raw_data: dict,
) -> tuple[bool, list[str]]:
    """Validate raw YAML data against the TestProfile schema.

    Returns (valid, list_of_error_messages).
    """
    errors: list[str] = []
    try:
        TestProfile(**raw_data)
    except ValidationError as exc:
        for err in exc.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
    return len(errors) == 0, errors


def validate_product_profile(
    raw_data: dict,
) -> tuple[bool, list[str]]:
    """Validate raw YAML data against the ProductProfileData schema."""
    errors: list[str] = []
    try:
        ProductProfileData(**raw_data)
    except ValidationError as exc:
        for err in exc.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
    return len(errors) == 0, errors


def validate_compatibility(
    profile: TestProfile,
    product: ProductBase,
) -> tuple[bool, list[str]]:
    """Check semantic compatibility between a test profile and product.

    Validates:
      - band is supported
      - mode is valid for band
      - channels are valid for their respective bands
    """
    errors: list[str] = []

    if profile.band not in product.supported_bands():
        errors.append(
            f"Band {profile.band!r} not supported by {product.name} "
            f"(supported: {product.supported_bands()})"
        )
        return False, errors

    valid_modes = product.valid_modes(profile.band)
    if profile.mode not in valid_modes:
        errors.append(
            f"Mode {profile.mode!r} not valid for {profile.band} on {product.name} "
            f"(valid: {valid_modes})"
        )

    channel_checks = [
        ("2.4G", profile.rf_channel_2g),
        ("5G", profile.rf_channel_5g),
        ("6G", profile.rf_channel_6g),
    ]
    for band, channel in channel_checks:
        if channel == "0":
            continue
        valid_ch = product.valid_channels(band)
        if channel not in valid_ch:
            errors.append(
                f"Channel {channel!r} not valid for {band} on {product.name}"
            )

    return len(errors) == 0, errors
