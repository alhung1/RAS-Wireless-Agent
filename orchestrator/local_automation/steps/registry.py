"""Step registration and sequence builder.

Builds the ordered 19-step automation sequence.  During the transition
period this mixes native BaseStep subclasses (for critical steps) with
LegacyStepWrapper instances (for non-refactored steps).

Native: s00_attach, s05_freq_channel, s06_select_ap, s11_band_select, s14_mode, s15_attenuation.
Remaining indices use LegacyStepWrapper (labview_runner_legacy.step_*).
"""
from __future__ import annotations

from orchestrator.local_automation.steps.base import BaseStep, LegacyStepWrapper


def build_default_sequence() -> list[BaseStep]:
    """Build the default 19-step sequence.

    Uses lazy imports to avoid circular dependencies and to allow
    the legacy module to load only when actually needed.

    Returns a new list each time (safe to modify).
    """
    from orchestrator.local_automation.steps.s00_attach import AttachStep
    from orchestrator.local_automation.steps.s05_freq_channel import FreqChannelStep
    from orchestrator.local_automation.steps.s06_select_ap import SelectAPStep
    from orchestrator.local_automation.steps.s11_band_select import BandSelectStep
    from orchestrator.local_automation.steps.s14_mode import ModeStep
    from orchestrator.local_automation.steps.s15_attenuation import AttenuationStep

    legacy = _build_legacy_map()

    return [
        AttachStep(),
        LegacyStepWrapper("s01_click_throughput",   1,  legacy.get("step_01_click_throughput")),
        LegacyStepWrapper("s02_login",              2,  legacy.get("step_02_login")),
        LegacyStepWrapper("s03_test_type",          3,  legacy.get("step_03_test_type")),
        LegacyStepWrapper("s04_table_position",     4,  legacy.get("step_04_table_position")),
        FreqChannelStep(),                          # step 05 -- NATIVE
        SelectAPStep(),                             # step 06 -- NATIVE
        LegacyStepWrapper("s07_use_last_ap",        7,  legacy.get("step_07_use_last_ap")),
        LegacyStepWrapper("s08_select_client",      8,  legacy.get("step_08_select_client")),
        LegacyStepWrapper("s09_dut_ip",             9,  legacy.get("step_09_dut_ip")),
        LegacyStepWrapper("s10_use_last_dut",       10, legacy.get("step_10_use_last_dut")),
        BandSelectStep(),                           # step 11 -- NATIVE (Phase B)
        LegacyStepWrapper("s12_chariot_pairs",      12, legacy.get("step_12_chariot_pairs")),
        LegacyStepWrapper("s13_pass_through",       13, legacy.get("step_13_pass_through")),
        ModeStep(),                                 # step 14 -- NATIVE (Phase B)
        AttenuationStep(),                          # step 15 -- NATIVE (Phase B.2)
        LegacyStepWrapper("s16_design_stage",       16, legacy.get("step_16_design_stage")),
        LegacyStepWrapper("s17_region",             17, legacy.get("step_17_region")),
        LegacyStepWrapper("s18_final_start",        18, legacy.get("step_18_final_start")),
    ]


def _build_legacy_map() -> dict:
    """Import all legacy step functions from labview_runner.

    Returns a dict of function_name -> function.
    Gracefully returns an empty dict if the legacy module cannot
    be imported (e.g. missing pyautogui on a CI machine).
    """
    try:
        from orchestrator.local_automation import labview_runner_legacy as lr
        return {
            "step_01_click_throughput": lr.step_01_click_throughput,
            "step_02_login": lr.step_02_login,
            "step_03_test_type": lr.step_03_test_type,
            "step_04_table_position": lr.step_04_table_position,
            "step_07_use_last_ap": lr.step_07_use_last_ap,
            "step_08_select_client": lr.step_08_select_client,
            "step_09_dut_ip": lr.step_09_dut_ip,
            "step_10_use_last_dut": lr.step_10_use_last_dut,
            "step_12_chariot_pairs": lr.step_12_chariot_pairs,
            "step_13_pass_through": lr.step_13_pass_through,
            "step_16_design_stage": lr.step_16_design_stage,
            "step_17_region": lr.step_17_region,
            "step_18_final_start": lr.step_18_final_start,
        }
    except Exception:
        return {}
