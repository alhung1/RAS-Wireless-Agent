"""StepContext -- single typed object that replaces all module-level globals.

Every step, every UI helper, and the engine itself receives a StepContext.
This makes steps independently executable and testable.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from orchestrator.local_automation.products.base import ProductBase


@dataclass
class RunConfig:
    """Typed test-run configuration.

    Mirrors the fields of the legacy RunConfig in labview_runner.py but
    lives in the new engine layer.  The backward-compat wrapper (Phase D)
    will bridge between the two.
    """
    band: str = "2.4G"
    freq_range: str = "MLO"
    rf_channel_2g: str = "10"
    rf_channel_5g: str = "44"
    rf_channel_6g: str = "69"
    user_information: str = "2G test"

    username: str = "Alex"
    password: str = "123"
    test_type: str = "1 rpm (fast)"

    ap_name: str = "RS700"
    client_name: str = "INTEL_BE200"
    firmware_rev: str = "V1.0.10.8"

    mode: str = "BW20"
    graph_range: str = "100"
    number_of_pairs: str = "8"
    number_of_pairs_5g6g: str = "0"

    start_atten: str = "0"
    step_size: str = "3"
    steps: str = "30"

    design_stage: str = "Beta"
    region: str = "US"

    ip_dropdown_2g: str = "3"
    ip_dropdown_5g6g: str = "3"
    ap_ip: str = "192.168.1.1"

    exe_path: str = r"C:\480.builds\v2.03\480.000.v2.03.exe"
    timeout_seconds: int = 14400
    finish_config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class WindowManagerState:
    """Mutable state for window management -- replaces module-level globals.

    Carried inside StepContext so that steps never touch global variables.
    """
    lv_pid: int | None = None
    popup_dismissed_hwnds: set[int] = field(default_factory=set)
    popup_dismiss_times: dict[int, float] = field(default_factory=dict)
    popup_cooldown_sec: float = 3.0


@dataclass
class StepContext:
    """All state needed to execute a step.

    Created once per run, passed to every step and UI helper.
    Replaces LV_PID, _DRY_RUN, _DRY_RUN_IMG, _POPUP_DISMISSED_HWNDS,
    and other module-level mutable state in the legacy code.
    """
    hwnd: int | None = None
    run_config: RunConfig = field(default_factory=RunConfig)
    product: Optional["ProductBase"] = None
    artifacts_dir: str = ""
    run_id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    dry_run: bool = False
    window_mgr: WindowManagerState = field(default_factory=WindowManagerState)
    ocr_available: bool = False
    emergency_stop_file: str = os.path.join("artifacts", "STOP")

    # Accumulates artifact paths during the run
    collected_artifacts: list[str] = field(default_factory=list)

    # Dry-run annotation image (numpy array, set during dry-run)
    dry_run_img: Any = None

    # Lazily-initialized WindowManager (not serializable)
    _window_manager: Any = field(default=None, repr=False)

    def get_window_manager(self):
        """Return a shared WindowManager instance, creating it lazily."""
        if self._window_manager is None:
            from orchestrator.local_automation.ui.window_manager import WindowManager
            self._window_manager = WindowManager()
        return self._window_manager

    def step_artifacts_dir(self, step_name: str) -> str:
        """Return the per-step artifact directory, creating it if needed."""
        d = os.path.join(self.artifacts_dir, "steps", step_name)
        os.makedirs(d, exist_ok=True)
        return d

    def errors_dir(self) -> str:
        d = os.path.join(self.artifacts_dir, "errors")
        os.makedirs(d, exist_ok=True)
        return d
