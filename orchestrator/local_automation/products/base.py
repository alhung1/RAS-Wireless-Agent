"""Product adapter base class.

Profiles hold data; product adapters hold behavior and capability rules.
Every supported product (BE200, AX210, ...) subclasses ProductBase and
overrides the methods that differ from the defaults.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext
    from orchestrator.local_automation.steps.step_result import VerificationSpec


class ProductBase(ABC):
    """Abstract base for product-specific adapters.

    Subclasses must implement the abstract methods.  Default behavior
    for non-abstract methods is safe for most products; override only
    what differs.
    """

    # --- Identity ---

    @property
    @abstractmethod
    def name(self) -> str:
        """Short machine-readable product name (e.g. 'INTEL_BE200')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for reports (e.g. 'Intel Wi-Fi 7 BE200')."""

    # --- Capability rules ---

    @abstractmethod
    def supported_bands(self) -> list[str]:
        """Bands this product can test (e.g. ['2.4G', '5G', '6G', 'MLO'])."""

    @abstractmethod
    def valid_channels(self, band: str) -> list[str]:
        """Valid RF channel strings for *band*."""

    @abstractmethod
    def valid_modes(self, band: str) -> list[str]:
        """Valid bandwidth modes for *band* (e.g. ['BW20', 'BW40'])."""

    @abstractmethod
    def default_config(self, band: str) -> dict:
        """Default RunConfig overrides for *band*.

        Returns a dict of field_name -> value that the profile loader
        merges into the RunConfig when the profile does not specify them.
        """

    # --- Paths ---

    def ap_folder(self) -> str:
        """Filesystem path to the AP definition folder."""
        return r"E:\AP"

    def client_folder(self) -> str:
        """Filesystem path to the client definition folder."""
        return r"E:\Client"

    # --- UI labels (for OCR / visual verification) ---

    def ui_labels(self) -> dict[str, str]:
        """Product-specific UI label strings used in OCR verification.

        Keys are semantic names; values are the text expected on screen.
        Override if a product uses different labels in the LabVIEW UI.
        """
        return {}

    # --- Verification specs ---

    def verify_band_selection(
        self, ctx: "StepContext", band: str,
        dropdown_id: str = "2g",
    ) -> "VerificationSpec | None":
        """Return a VerificationSpec for confirming band selection, or None."""
        return None

    def verify_mode_selection(
        self, ctx: "StepContext", mode: str,
    ) -> "VerificationSpec | None":
        """Return a VerificationSpec for confirming mode selection, or None."""
        return None

    def verify_channel_selection(
        self, ctx: "StepContext", band: str, channel: str,
    ) -> "VerificationSpec | None":
        """Return a VerificationSpec for confirming channel value, or None."""
        return None

    def verify_attenuation(
        self, ctx: "StepContext", field_name: str, value: str,
    ) -> "VerificationSpec | None":
        """Return a VerificationSpec for an attenuation field, or None."""
        return None

    def verify_ap_selection(
        self, ctx: "StepContext", ap_name: str,
    ) -> "VerificationSpec | None":
        """Return a VerificationSpec for AP selection confirmation, or None."""
        return None

    # --- Recovery hints ---

    def recovery_hints(self, step_name: str, failure: str) -> list[str]:
        """Ordered list of recovery actions to try for a step failure.

        Actions are symbolic names that the recovery layer interprets:
          "press_escape", "click_neutral", "dismiss_popups",
          "refocus_window", "retry_dropdown", "retry_click"

        Default implementation returns a generic sequence.
        """
        return ["dismiss_popups", "refocus_window", "press_escape", "click_neutral"]
