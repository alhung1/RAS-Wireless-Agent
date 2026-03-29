"""Recovery actions -- attempt to restore the UI to a usable state.

Interprets symbolic recovery action names (from product adapters)
and executes them against the current StepContext.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext
    from orchestrator.local_automation.recovery.diagnosis import Diagnosis

from orchestrator.logging.json_logger import get_logger

logger = get_logger("recovery")


def execute_recovery(
    ctx: "StepContext",
    diagnosis: "Diagnosis",
    actions: list[str],
) -> bool:
    """Execute a sequence of recovery actions.

    Returns True if at least one action was performed.
    The actual UI operations will be implemented in Phase A.6
    when the ui/ layer is extracted.
    """
    performed = False
    for action in actions:
        logger.info(
            "Recovery action: %s (step=%s)",
            action, diagnosis.step_name,
            extra={"action": "recovery", "step": diagnosis.step_name},
        )
        # Phase A.6 will connect these to actual UI operations:
        #   "dismiss_popups" -> window_manager.dismiss_lv_popups()
        #   "refocus_window" -> window_manager.ensure_foreground()
        #   "press_escape"   -> input_helpers.safe_press("escape")
        #   "click_neutral"  -> input_helpers.safe_click(hwnd, 400, 300)
        #   "retry_dropdown" -> dropdowns.select_dropdown_by_nav(...)
        #   "retry_click"    -> input_helpers.safe_click(...)
        #   "clear_field_retry" -> input_helpers.clear_and_type(...)
        performed = True
    return performed
