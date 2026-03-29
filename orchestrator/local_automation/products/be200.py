"""Intel Wi-Fi 7 BE200 product adapter.

Encodes all capability rules, verification strategies, and recovery
hints specific to the BE200.  This is the first and reference adapter.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.local_automation.products.base import ProductBase

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext
    from orchestrator.local_automation.steps.step_result import VerificationSpec


_CHANNELS_24G = [str(c) for c in range(1, 15)]             # 1..14
_CHANNELS_5G = [
    "36", "40", "44", "48",                                # UNII-1
    "52", "56", "60", "64",                                # UNII-2
    "100", "104", "108", "112", "116", "120",              # UNII-2 Extended
    "124", "128", "132", "136", "140", "144",
    "149", "153", "157", "161", "165",                     # UNII-3
]
_CHANNELS_6G = [str(c) for c in range(1, 234, 4)]          # 1,5,9,...,233

_MODES_24G = ["BW20", "BW40"]
_MODES_5G = ["BW20", "BW40", "BW80", "BW160"]
_MODES_6G = ["BW20", "BW40", "BW80", "BW160", "BW240", "BW320"]
_MODES_MLO = ["BW20", "BW40", "BW80", "BW160", "BW240", "BW320"]


class BE200Adapter(ProductBase):
    """Product adapter for the Intel Wi-Fi 7 BE200 network card."""

    @property
    def name(self) -> str:
        return "INTEL_BE200"

    @property
    def display_name(self) -> str:
        return "Intel Wi-Fi 7 BE200"

    # --- Capability rules ---

    def supported_bands(self) -> list[str]:
        return ["2.4G", "5G", "6G", "MLO"]

    def valid_channels(self, band: str) -> list[str]:
        return {
            "2.4G": _CHANNELS_24G,
            "5G": _CHANNELS_5G,
            "6G": _CHANNELS_6G,
            "MLO": _CHANNELS_24G + _CHANNELS_5G + _CHANNELS_6G,
        }.get(band, [])

    def valid_modes(self, band: str) -> list[str]:
        return {
            "2.4G": _MODES_24G,
            "5G": _MODES_5G,
            "6G": _MODES_6G,
            "MLO": _MODES_MLO,
        }.get(band, [])

    def default_config(self, band: str) -> dict:
        defaults = {
            "2.4G": {
                "rf_channel_2g": "10",
                "rf_channel_5g": "44",
                "rf_channel_6g": "69",
                "user_information": "2G test",
                "mode": "BW20",
                "number_of_pairs": "8",
                "number_of_pairs_5g6g": "0",
                "freq_range": "MLO",
            },
            "5G": {
                "rf_channel_2g": "0",
                "rf_channel_5g": "44",
                "rf_channel_6g": "0",
                "user_information": "5G test",
                "mode": "BW160",
                "number_of_pairs": "0",
                "number_of_pairs_5g6g": "16",
                "freq_range": "MLO",
            },
            "6G": {
                "rf_channel_2g": "0",
                "rf_channel_5g": "0",
                "rf_channel_6g": "69",
                "user_information": "6G test",
                "mode": "BW320",
                "number_of_pairs": "0",
                "number_of_pairs_5g6g": "20",
                "freq_range": "MLO",
            },
            "MLO": {
                "rf_channel_2g": "10",
                "rf_channel_5g": "44",
                "rf_channel_6g": "69",
                "user_information": "MLO test",
                "mode": "BW20",
                "number_of_pairs": "8",
                "number_of_pairs_5g6g": "8",
                "freq_range": "MLO",
            },
        }
        return defaults.get(band, {})

    # --- Paths ---

    def ap_folder(self) -> str:
        return r"E:\AP"

    def client_folder(self) -> str:
        return r"E:\Client"

    # --- UI labels ---

    def ui_labels(self) -> dict[str, str]:
        return {
            "client_name": "INTEL_BE200",
            "ap_name": "RS700",
            "adapter_hint": "Intel(R) Wi-Fi 7 BE200",
            "firmware_rev": "V1.0.10.8",
        }

    # --- Verification specs ---
    #
    # IMPORTANT: LabVIEW text-display offsets vary PER VI and PER control type.
    # Each region below was calibrated via live dark-pixel scan and OCR test
    # on the actual 1288x1040 window on 2026-03-29.
    #
    # 481.300 freq/channel VI: text renders AT or ABOVE click target
    # 481.300 atten VI:        text renders ~14px BELOW click target
    # 400 600 MODE.vi:         text renders ~10px BELOW click target
    # 400 600 IP address.vi:   text renders at dropdown display area

    def verify_band_selection(
        self, ctx: "StepContext", band: str,
        dropdown_id: str = "2g",
    ) -> "VerificationSpec | None":
        from orchestrator.local_automation.steps.step_result import VerificationSpec
        # IP address dropdown displays are ~6px wide -- too small for OCR.
        # Pixel_diff is the primary verification for these controls.
        regions = {
            "2g":  (550, 535, 120, 35),
            "5g":  (870, 535, 120, 35),
        }
        region = regions.get(dropdown_id, regions["2g"])
        expected = (ctx.run_config.ip_dropdown_2g if dropdown_id == "2g"
                    else ctx.run_config.ip_dropdown_5g6g)
        return VerificationSpec(
            pixel_diff_region=region,
            min_diff_pct=1.0,
            expected_text=expected,
        )

    def verify_mode_selection(
        self, ctx: "StepContext", mode: str,
    ) -> "VerificationSpec | None":
        from orchestrator.local_automation.steps.step_result import VerificationSpec
        return VerificationSpec(
            ocr_region=(200, 766, 120, 20),
            expected_text=mode,
            pixel_diff_region=(180, 740, 200, 50),
            min_diff_pct=1.0,
            ocr_psm=7,
            ocr_char_whitelist="BW0123456789",
            ocr_scale_factor=5,
            ocr_threshold=100,
            ocr_invert=True,
            ocr_normalize_digits=False,
        )

    def verify_channel_selection(
        self, ctx: "StepContext", band: str, channel: str,
    ) -> "VerificationSpec | None":
        from orchestrator.local_automation.steps.step_result import VerificationSpec
        # Calibrated on 481.300 freq/channel VI: text at y=740, ~12px ABOVE click y=752
        # NO whitelist + low threshold (40): LabVIEW font causes 4->A, 9->Q;
        # normalize_digits recovers.  Low threshold isolates only darkest strokes.
        field_positions = {
            "2.4G": (405, 740, 57, 18),
            "5G":   (600, 740, 57, 18),
            "6G":   (795, 740, 57, 18),
        }
        region = field_positions.get(band)
        if not region:
            return None
        return VerificationSpec(
            ocr_region=region,
            expected_text=channel,
            pixel_diff_region=(region[0] - 10, region[1] - 5, region[2] + 20, region[3] + 20),
            min_diff_pct=1.0,
            ocr_psm=7,
            ocr_char_whitelist="",
            ocr_scale_factor=5,
            ocr_threshold=40,
            ocr_invert=True,
            ocr_normalize_digits=True,
        )

    def verify_attenuation(
        self, ctx: "StepContext", field_name: str, value: str,
    ) -> "VerificationSpec | None":
        from orchestrator.local_automation.steps.step_result import VerificationSpec
        field_regions = {
            "start_atten": (117, 510, 80, 22),
            "step_size":   (530, 510, 80, 22),
            "steps":       (710, 510, 80, 22),
        }
        region = field_regions.get(field_name)
        if not region:
            return None
        # Low threshold (40) + normalize: LabVIEW font digit misreads recovered
        return VerificationSpec(
            ocr_region=region,
            expected_text=value,
            pixel_diff_region=(region[0], region[1] - 10, region[2], region[3] + 10),
            min_diff_pct=1.0,
            ocr_psm=7,
            ocr_char_whitelist="",
            ocr_scale_factor=5,
            ocr_threshold=40,
            ocr_invert=True,
            ocr_normalize_digits=True,
        )

    def verify_freq_range(
        self, ctx: "StepContext", freq_range: str,
    ) -> "VerificationSpec | None":
        from orchestrator.local_automation.steps.step_result import VerificationSpec
        # Calibrated on 481.300 VI: text at y=333, AT the click target y=344
        # Threshold=80 optimal for text labels on green bg
        return VerificationSpec(
            ocr_region=(460, 333, 120, 18),
            expected_text=freq_range,
            pixel_diff_region=(450, 325, 140, 30),
            min_diff_pct=1.0,
            ocr_psm=7,
            ocr_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.",
            ocr_scale_factor=5,
            ocr_threshold=80,
            ocr_invert=True,
            ocr_normalize_digits=False,
        )

    def verify_user_info(
        self, ctx: "StepContext", user_info: str,
    ) -> "VerificationSpec | None":
        from orchestrator.local_automation.steps.step_result import VerificationSpec
        # User info field position NOT confirmed via live OCR calibration.
        # The text may render at a non-standard location on 481.300 VI.
        # Using pixel_diff as primary method until OCR position is confirmed.
        return VerificationSpec(
            ocr_region=(650, 838, 220, 20),
            expected_text=user_info,
            pixel_diff_region=(640, 830, 240, 35),
            min_diff_pct=1.0,
            ocr_psm=7,
            ocr_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ",
            ocr_scale_factor=5,
            ocr_threshold=100,
            ocr_invert=True,
            ocr_normalize_digits=False,
        )

    def verify_ap_selection(
        self, ctx: "StepContext", ap_name: str,
    ) -> "VerificationSpec | None":
        from orchestrator.local_automation.steps.step_result import VerificationSpec
        return VerificationSpec(
            ocr_region=(0, 0, 1288, 1040),
            expected_text=ap_name,
            title_hint="400 600 AP",
            ocr_psm=6,
            ocr_scale_factor=1,
            ocr_invert=False,
        )

    # --- Recovery hints ---

    def recovery_hints(self, step_name: str, failure: str) -> list[str]:
        step_hints: dict[str, list[str]] = {
            "s14_mode": [
                "press_escape", "click_neutral", "dismiss_popups",
                "refocus_window", "retry_dropdown",
            ],
            "s11_band_select": [
                "press_escape", "click_neutral", "dismiss_popups",
                "refocus_window", "retry_dropdown",
            ],
            "s06_select_ap": [
                "dismiss_popups", "refocus_window", "retry_click",
            ],
            "s15_attenuation": [
                "dismiss_popups", "refocus_window", "clear_field_retry",
            ],
        }
        return step_hints.get(step_name, super().recovery_hints(step_name, failure))
