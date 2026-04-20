"""Profile and product loading.

Loads YAML profiles, resolves product adapters, and produces a typed
RunConfig ready for the step engine.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

from orchestrator.local_automation.engine.context import RunConfig
from orchestrator.local_automation.products.base import ProductBase
from orchestrator.local_automation.profiles.schema import (
    ProductProfileData,
    TestProfile,
    TestMatrix,
)


PRODUCT_ADAPTERS: dict[str, type[ProductBase]] = {}


def register_product(product_id: str, adapter_cls: type[ProductBase]) -> None:
    """Register a product adapter class by ID."""
    PRODUCT_ADAPTERS[product_id.upper()] = adapter_cls


def _register_builtin_products() -> None:
    """Auto-register all built-in product adapters."""
    if PRODUCT_ADAPTERS:
        return
    from orchestrator.local_automation.products.be200 import BE200Adapter
    register_product("INTEL_BE200", BE200Adapter)


def get_product_adapter(product_id: str) -> Optional[ProductBase]:
    """Look up and instantiate a product adapter by ID."""
    _register_builtin_products()
    cls = PRODUCT_ADAPTERS.get(product_id.upper())
    if cls is None:
        return None
    return cls()


def load_product_profile(yaml_path: str) -> ProductProfileData:
    """Load a product profile YAML into a typed model."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return ProductProfileData(**data)


def load_test_profile(yaml_path: str) -> TestProfile:
    """Load a test profile YAML into a typed model."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return TestProfile(**data)


def load_test_matrix(yaml_path: str) -> TestMatrix:
    """Load a test matrix YAML."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return TestMatrix(**data)


def resolve_run_config(
    test_profile: TestProfile,
    product_profile: Optional[ProductProfileData] = None,
    product: Optional[ProductBase] = None,
) -> RunConfig:
    """Merge test profile + product profile + product adapter defaults
    into a single typed RunConfig.

    Priority (highest to lowest):
      1. Values explicitly set in the test profile
      2. Values from the product profile YAML
      3. Default values from the product adapter
      4. RunConfig field defaults
    """
    cfg = RunConfig()

    # Layer 3: product adapter defaults for the band
    if product:
        band_defaults = product.default_config(test_profile.band)
        for k, v in band_defaults.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)

    # Layer 2: product profile data
    if product_profile:
        field_map = {
            "ap_name": product_profile.ap_name,
            "client_name": product_profile.client_name,
            "exe_path": product_profile.exe_path,
        }
        if product_profile.firmware_rev:
            field_map["firmware_rev"] = product_profile.firmware_rev
        for k, v in field_map.items():
            if v and hasattr(cfg, k):
                setattr(cfg, k, v)

    # Layer 1: test profile values (override everything)
    profile_fields = {
        "band": test_profile.band,
        "freq_range": test_profile.freq_range,
        "rf_channel_2g": test_profile.rf_channel_2g,
        "rf_channel_5g": test_profile.rf_channel_5g,
        "rf_channel_6g": test_profile.rf_channel_6g,
        "mode": test_profile.mode,
        "number_of_pairs": test_profile.number_of_pairs,
        "number_of_pairs_5g6g": test_profile.number_of_pairs_5g6g,
        "design_stage": test_profile.design_stage,
        "region": test_profile.region,
        "ip_dropdown_2g": test_profile.ip_dropdown_2g,
        "ip_dropdown_5g6g": test_profile.ip_dropdown_5g6g,
        "ap_ip": test_profile.ap_ip,
        "username": test_profile.username,
        "password": test_profile.password,
        "test_type": test_profile.test_type,
        "timeout_seconds": test_profile.timeout_seconds,
    }
    if test_profile.ap_name:
        profile_fields["ap_name"] = test_profile.ap_name
    if test_profile.user_information:
        profile_fields["user_information"] = test_profile.user_information
    if test_profile.attenuation:
        profile_fields["start_atten"] = test_profile.attenuation.start
        profile_fields["step_size"] = test_profile.attenuation.step
        profile_fields["steps"] = test_profile.attenuation.steps
    if test_profile.finish_detection:
        profile_fields["finish_config"] = test_profile.finish_detection.model_dump()

    for k, v in profile_fields.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)

    return cfg


def find_product_profile_path(
    product_id: str,
    profiles_root: str | None = None,
) -> str | None:
    """Locate the product YAML by product ID in the profiles/products/ dir."""
    if profiles_root is None:
        profiles_root = str(
            Path(__file__).parent.parent.parent.parent / "profiles"
        )
    candidates = [
        os.path.join(profiles_root, "products", f"{product_id.lower()}.yaml"),
        os.path.join(profiles_root, "products", f"{product_id}.yaml"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None
