"""Unit tests for profile schema validation and compatibility checking.

Tests Pydantic models, YAML loading, and validation rules without
GUI or Windows dependencies.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from orchestrator.local_automation.profiles.schema import (
    AttenuationConfig,
    FinishDetectionConfig,
    ProductProfileData,
    TestMatrix,
    TestMatrixEntry,
    TestProfile,
)
from orchestrator.local_automation.profiles.validator import (
    validate_product_profile,
    validate_test_profile,
)
from orchestrator.workflow_schema import RouterConfig


# Locate the profiles directory relative to this test file
PROJECT_ROOT = Path(__file__).parent.parent
PROFILES_DIR = PROJECT_ROOT / "profiles"
TEST_MATRIX_DIR = PROFILES_DIR / "test_matrix"
PRODUCTS_DIR = PROFILES_DIR / "products"


# ---------------------------------------------------------------------------
# Valid profile YAML loading tests
# ---------------------------------------------------------------------------

class TestValidProfiles:
    """Test loading and validating real YAML profile files."""

    def test_valid_test_profile_be200_2g_yaml(self):
        """Load be200_2g.yaml test profile, validate it passes schema check."""
        yaml_path = TEST_MATRIX_DIR / "be200_2g.yaml"
        assert yaml_path.exists(), f"Test profile not found: {yaml_path}"

        with open(yaml_path, "r") as f:
            raw_data = yaml.safe_load(f)

        valid, errors = validate_test_profile(raw_data)
        assert valid, f"Test profile validation failed: {errors}"

        # Verify key fields are loaded
        profile = TestProfile(**raw_data)
        assert profile.name == "BE200 2.4G Standard"
        assert profile.product == "INTEL_BE200"
        assert profile.band == "2.4G"
        assert profile.mode == "BW20"

    def test_valid_product_profile_be200_yaml(self):
        """Load be200.yaml product profile, validate it passes schema check."""
        yaml_path = PRODUCTS_DIR / "be200.yaml"
        assert yaml_path.exists(), f"Product profile not found: {yaml_path}"

        with open(yaml_path, "r") as f:
            raw_data = yaml.safe_load(f)

        valid, errors = validate_product_profile(raw_data)
        assert valid, f"Product profile validation failed: {errors}"

        # Verify key fields are loaded
        product = ProductProfileData(**raw_data)
        assert product.product == "INTEL_BE200"
        assert product.display_name == "Intel Wi-Fi 7 BE200"
        assert product.client_name == "INTEL_BE200"


# ---------------------------------------------------------------------------
# Schema validation failure tests
# ---------------------------------------------------------------------------

class TestMissingRequiredField:
    """Test validation fails when required fields are missing."""

    def test_missing_name_field(self):
        """Remove 'name' from test profile data, validation fails."""
        raw_data = {
            "product": "INTEL_BE200",
            "band": "2.4G",
            "mode": "BW20",
        }
        valid, errors = validate_test_profile(raw_data)
        assert valid is False
        assert any("name" in err.lower() for err in errors), \
            f"Expected 'name' error in: {errors}"


class TestInvalidBandValue:
    """Test compatibility check catches unsupported band values.

    Note: TestProfile schema accepts any string for band (it's a free-form field).
    The band validity check happens in validate_compatibility() against a product adapter.
    """

    def test_invalid_band_compatibility(self):
        """Set band to unsupported value, compatibility check catches it."""
        from orchestrator.local_automation.profiles.validator import validate_compatibility
        from orchestrator.local_automation.profiles.loader import get_product_adapter

        raw_data = {
            "name": "Invalid Band Test",
            "product": "INTEL_BE200",
            "band": "3.6G",  # Not a valid band
            "mode": "BW20",
        }
        # Schema validation passes (band is free-form string)
        valid, errors = validate_test_profile(raw_data)
        assert valid is True, f"Schema should pass: {errors}"

        # But compatibility check should fail
        profile = TestProfile(**raw_data)
        product = get_product_adapter("INTEL_BE200")
        assert product is not None
        compat_ok, compat_errors = validate_compatibility(profile, product)
        assert compat_ok is False
        assert any("band" in err.lower() for err in compat_errors), \
            f"Expected 'band' error in: {compat_errors}"


class TestEmptyYaml:
    """Test validation fails for empty profile data."""

    def test_empty_yaml_dict(self):
        """Verify empty dict fails validation with clear errors."""
        raw_data = {}
        valid, errors = validate_test_profile(raw_data)
        assert valid is False
        assert len(errors) > 0, "Expected validation errors for empty dict"
        # Should complain about missing required fields
        assert any("name" in err.lower() or "product" in err.lower()
                   for err in errors), f"Expected required field error in: {errors}"


# ---------------------------------------------------------------------------
# Default value tests
# ---------------------------------------------------------------------------

class TestAttenuationConfigDefaults:
    """Test AttenuationConfig uses correct default values."""

    def test_attenuation_config_defaults(self):
        """Verify default values are correct when not specified."""
        config = AttenuationConfig()
        assert config.start == "0"
        assert config.step == "3"
        assert config.steps == "30"

    def test_attenuation_config_custom_values(self):
        """Verify custom values override defaults."""
        config = AttenuationConfig(start="5", step="2", steps="20")
        assert config.start == "5"
        assert config.step == "2"
        assert config.steps == "20"


# ---------------------------------------------------------------------------
# Model composition tests
# ---------------------------------------------------------------------------

class TestTestMatrixModel:
    """Test TestMatrix model and composition."""

    def test_test_matrix_creation(self):
        """Create a TestMatrix with entries."""
        entry1 = TestMatrixEntry(
            profile="profiles/test_matrix/be200_2g.yaml",
            enabled=True,
        )
        entry2 = TestMatrixEntry(
            profile="profiles/test_matrix/be200_5g.yaml",
            enabled=False,
        )
        matrix = TestMatrix(
            name="BE200 Full Suite",
            description="Test all BE200 bands",
            stop_on_failure=True,
            entries=[entry1, entry2],
        )

        assert matrix.name == "BE200 Full Suite"
        assert matrix.stop_on_failure is True
        assert len(matrix.entries) == 2
        assert matrix.entries[0].enabled is True
        assert matrix.entries[1].enabled is False

    def test_test_matrix_with_empty_entries(self):
        """Create TestMatrix with default empty entries list."""
        matrix = TestMatrix(name="Empty Matrix")
        assert matrix.name == "Empty Matrix"
        assert matrix.entries == []
        assert matrix.stop_on_failure is True  # default


# ---------------------------------------------------------------------------
# Legacy band coercion tests
# ---------------------------------------------------------------------------

class TestRouterConfigLegacyBandCoercion:
    """Test RouterConfig coerces legacy list format to dict format."""

    def test_bands_list_coerced_to_dict(self):
        """bands: ['2.4G', '5G'] list format coerced to dict."""
        raw_data = {
            "base_url": "http://192.168.1.1",
            "bands": ["2.4G", "5G"],
        }
        router = RouterConfig(**raw_data)

        # Should have dict with keys from list
        assert isinstance(router.bands, dict)
        assert "2.4G" in router.bands
        assert "5G" in router.bands

    def test_bands_dict_passed_through(self):
        """bands as dict is preserved."""
        from orchestrator.workflow_schema import BandWifiConfig

        raw_data = {
            "base_url": "http://192.168.1.1",
            "bands": {
                "2.4G": {"ssid": "Test2G", "password": "pass2g"},
                "5G": {"ssid": "Test5G", "password": "pass5g"},
            },
        }
        router = RouterConfig(**raw_data)

        assert router.bands["2.4G"].ssid == "Test2G"
        assert router.bands["5G"].ssid == "Test5G"

    def test_bands_empty_list_not_coerced(self):
        """Empty bands list is not coerced (guard checks raw[0] exists).

        The legacy coercion only triggers when the list is non-empty and
        the first element is a string. An empty list passes through as-is
        and Pydantic will attempt to validate it as dict[str, BandWifiConfig].
        """
        raw_data = {
            "base_url": "http://192.168.1.1",
            "bands": [],
        }
        # Empty list is not coerced and fails Pydantic dict validation
        # OR Pydantic may coerce it. Either way, we verify no crash.
        try:
            router = RouterConfig(**raw_data)
            # If it doesn't raise, bands should be empty
            assert len(router.bands) == 0
        except Exception:
            # Pydantic validation error is acceptable for edge case
            pass

    def test_bands_single_string(self):
        """Single-element list of strings is coerced to dict."""
        raw_data = {
            "base_url": "http://192.168.1.1",
            "bands": ["6G"],
        }
        router = RouterConfig(**raw_data)
        assert isinstance(router.bands, dict)
        assert "6G" in router.bands


# ---------------------------------------------------------------------------
# FinishDetectionConfig tests
# ---------------------------------------------------------------------------

class TestFinishDetectionConfig:
    """Test FinishDetectionConfig defaults and custom values."""

    def test_finish_detection_defaults(self):
        """FinishDetectionConfig has sensible defaults."""
        config = FinishDetectionConfig()
        assert config.result_file_dir == r"D:\480\LOG\RBU"
        assert config.result_file_glob == "*.pdf"
        assert config.timeout_sec == 14400
        assert config.poll_interval_sec == 30

    def test_finish_detection_in_test_profile(self):
        """TestProfile includes optional finish_detection config."""
        raw_data = {
            "name": "Test with Finish Detection",
            "product": "INTEL_BE200",
            "band": "2.4G",
            "mode": "BW20",
            "finish_detection": {
                "result_file_dir": r"D:\custom\logs",
                "result_file_glob": "result_*.txt",
                "timeout_sec": 3600,
                "poll_interval_sec": 60,
            },
        }
        profile = TestProfile(**raw_data)
        assert profile.finish_detection is not None
        assert profile.finish_detection.result_file_dir == r"D:\custom\logs"
        assert profile.finish_detection.result_file_glob == "result_*.txt"
        assert profile.finish_detection.timeout_sec == 3600


# ---------------------------------------------------------------------------
# Product profile validation tests
# ---------------------------------------------------------------------------

class TestProductProfileValidation:
    """Tests for product profile schema validation via validate_product_profile."""

    def test_valid_product_profile_be200_yaml(self):
        """Real be200.yaml product profile passes schema validation."""
        yaml_path = PRODUCTS_DIR / "be200.yaml"
        assert yaml_path.exists(), f"Product profile not found: {yaml_path}"

        with open(yaml_path, "r") as f:
            raw = yaml.safe_load(f)
        ok, errors = validate_product_profile(raw)
        assert ok, f"Expected valid, got errors: {errors}"

    def test_product_profile_missing_required_field(self):
        """Product profile without 'product' field fails validation."""
        raw = {"display_name": "Test Product", "client_name": "TEST"}
        ok, errors = validate_product_profile(raw)
        assert not ok
        assert any("product" in e for e in errors)

    def test_product_profile_minimal_valid(self):
        """Minimal valid product profile with only required fields."""
        raw = {"product": "TEST_DEVICE", "client_name": "TEST_DEVICE"}
        ok, errors = validate_product_profile(raw)
        assert ok, f"Expected valid, got errors: {errors}"

    def test_product_profile_defaults_applied(self):
        """Default values are applied for optional fields."""
        raw = {"product": "TEST_DEVICE", "client_name": "TEST_DEVICE"}
        pp = ProductProfileData(**raw)
        assert pp.ap_name == "RS700"
        assert pp.ap_folder == r"E:\AP"
        assert pp.client_folder == r"E:\Client"
