"""Failure diagnosis -- determine what went wrong after a step fails.

Produces a Diagnosis object that the recovery layer and step-specific
recover() methods use to decide corrective actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Diagnosis:
    """Structured description of what went wrong."""
    step_name: str = ""
    issues: list[str] = field(default_factory=list)
    active_window_title: str = ""
    expected_window_title: str = ""
    popup_dismissed: int = 0
    dialog_dismissed: int = 0
    screenshot_path: str = ""

    def to_dict(self) -> dict:
        return {
            "step_name": self.step_name,
            "issues": self.issues,
            "active_window_title": self.active_window_title,
            "expected_window_title": self.expected_window_title,
            "popup_dismissed": self.popup_dismissed,
            "dialog_dismissed": self.dialog_dismissed,
            "screenshot_path": self.screenshot_path,
        }
