"""Pydantic models for product profiles and test matrices.

Profiles are data-only.  All behavior and capability rules live in
product adapters (products/*.py).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AttenuationConfig(BaseModel):
    """Attenuation sweep parameters."""
    start: str = "0"
    step: str = "3"
    steps: str = "30"


class ProductProfileData(BaseModel):
    """Static product data loaded from profiles/products/<name>.yaml.

    Does NOT contain behavior -- that lives in the product adapter.
    """
    product: str = Field(..., description="Machine-readable product ID (matches adapter name)")
    display_name: str = Field("", description="Human-readable product name")
    client_name: str = Field(..., description="Client name in E:\\Client folder")
    ap_name: str = Field("RS700", description="AP name in E:\\AP folder")
    adapter_hint: str = Field("", description="Windows adapter description substring")
    firmware_rev: str = Field("", description="Firmware revision to fill in step 07")
    ap_folder: str = Field(r"E:\AP", description="Path to AP definitions")
    client_folder: str = Field(r"E:\Client", description="Path to client definitions")
    exe_path: str = Field(
        r"C:\480.builds\v2.03\480.000.v2.03.exe",
        description="LabVIEW executable path",
    )


class TestProfile(BaseModel):
    """A single test case: product + band + parameters.

    Loaded from profiles/test_matrix/<name>.yaml.
    """
    name: str = Field(..., description="Human-readable test name")
    product: str = Field(..., description="Product ID (references products/<id>.yaml)")
    band: str = Field(..., description="Test band: 2.4G, 5G, 6G, or MLO")
    freq_range: str = Field("MLO", description="Frequency range selection")

    rf_channel_2g: str = Field("0", description="2.4G RF channel (0 = unused)")
    rf_channel_5g: str = Field("0", description="5G RF channel (0 = unused)")
    rf_channel_6g: str = Field("0", description="6G RF channel (0 = unused)")

    mode: str = Field(..., description="Bandwidth mode (BW20, BW40, ...)")
    number_of_pairs: str = Field("0", description="Chariot pairs for 2G/MLO")
    number_of_pairs_5g6g: str = Field("0", description="Chariot pairs for 5G/6G")

    attenuation: AttenuationConfig = Field(default_factory=AttenuationConfig)
    design_stage: str = Field("Beta")
    region: str = Field("US")

    user_information: str = Field("", description="Free text shown in LabVIEW")
    ip_dropdown_2g: str = Field("3")
    ip_dropdown_5g6g: str = Field("3")
    ap_ip: str = Field("192.168.1.1")

    username: str = Field("Alex")
    password: str = Field("123")
    test_type: str = Field("1 rpm (fast)")

    timeout_seconds: int = Field(14400, description="Max wait for test completion")

    finish_detection: Optional[FinishDetectionConfig] = None


class FinishDetectionConfig(BaseModel):
    """How to detect when the LabVIEW test completes."""
    result_file_dir: str = Field(r"D:\480\LOG\RBU")
    result_file_glob: str = Field("*.pdf")
    timeout_sec: int = Field(14400)
    poll_interval_sec: int = Field(30)


# Rebuild model to resolve forward reference
TestProfile.model_rebuild()


class TestMatrixEntry(BaseModel):
    """One entry in a test matrix -- references a test profile by path."""
    profile: str = Field(..., description="Path to test profile YAML")
    enabled: bool = Field(True)


class TestMatrix(BaseModel):
    """A collection of test profiles to execute sequentially."""
    name: str = Field(..., description="Matrix name")
    description: str = Field("")
    stop_on_failure: bool = Field(True)
    entries: list[TestMatrixEntry] = Field(default_factory=list)
