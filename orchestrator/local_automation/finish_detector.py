"""Detect when a LabVIEW test run has completed.

Supports three detection methods (checked in priority order):
  1. Result file appears  (new PDF/CSV in a watched directory)
  2. Log keyword          (scan a log file for a keyword)
  3. UI text              (screenshot + template/OCR fallback)
Also enforces a hard timeout and optional fail-fast pattern.

Primary detection for the RAS lab: a new PDF appears in
D:\\480\\LOG\\RBU once the LabVIEW test finishes (~3.5 hours).
"""
from __future__ import annotations

import glob
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from orchestrator.logging.json_logger import get_logger

logger = get_logger("finish_detector")


@dataclass
class FinishConfig:
    result_file_dir: str = r"D:\480\LOG\RBU"
    result_file_glob: str = "*.pdf"
    result_file_min_size: int = 100

    log_file_path: str = ""
    log_keyword: str = "Completed"
    log_fail_keyword: str = ""

    ui_hwnd: int = 0
    ui_keywords: list[str] = field(default_factory=lambda: [
        "Completed", "Finished", "PASS", "FAIL", "Done",
    ])
    ui_template: str = ""

    timeout_sec: int = 14400  # 4 hours
    poll_interval_sec: int = 30
    fail_fast_keyword: str = ""


@dataclass
class FinishResult:
    finished: bool = False
    method: str = ""
    elapsed_sec: float = 0.0
    detail: str = ""
    timed_out: bool = False
    failed_fast: bool = False
    screenshot_path: str = ""


def _check_result_file(cfg: FinishConfig,
                       initial_files: set[str] | None = None) -> Optional[str]:
    """Check for NEW result files that weren't present at test start."""
    if not cfg.result_file_dir or not os.path.isdir(cfg.result_file_dir):
        return None
    pattern = os.path.join(cfg.result_file_dir, cfg.result_file_glob)
    current_files = set(glob.glob(pattern))

    known = initial_files or set()
    new_files = current_files - known

    for f in sorted(new_files, key=os.path.getmtime, reverse=True):
        try:
            if os.path.getsize(f) >= cfg.result_file_min_size:
                return f
        except OSError:
            continue
    return None


def _check_log_keyword(cfg: FinishConfig) -> Optional[str]:
    if not cfg.log_file_path or not os.path.isfile(cfg.log_file_path):
        return None
    try:
        with open(cfg.log_file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if cfg.fail_fast_keyword and cfg.fail_fast_keyword in content:
            return f"FAIL_FAST:{cfg.fail_fast_keyword}"
        if cfg.log_keyword and cfg.log_keyword in content:
            return cfg.log_keyword
    except Exception:
        pass
    return None


def _check_ui_text(cfg: FinishConfig, artifacts_dir: str) -> Optional[str]:
    if not cfg.ui_hwnd:
        return None
    try:
        from orchestrator.local_automation.screen_utils import (
            capture_window, save_screenshot,
        )
        screen = capture_window(cfg.ui_hwnd)
        save_screenshot(screen, artifacts_dir, "finish_check_latest.png")

        if cfg.ui_template:
            from orchestrator.local_automation.screen_utils import screen_contains
            if screen_contains(screen, cfg.ui_template, threshold=0.75):
                return f"template:{cfg.ui_template}"

        try:
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                if win.handle == cfg.ui_hwnd:
                    texts = win.texts()
                    combined = " ".join(t for t in texts if t)
                    for kw in cfg.ui_keywords:
                        if kw.lower() in combined.lower():
                            return f"ui_text:{kw}"
                    break
        except Exception:
            pass

    except Exception as exc:
        logger.warning("UI check failed: %s", exc)
    return None


def wait_for_finish(
    cfg: FinishConfig,
    artifacts_dir: str = "artifacts/labview",
    initial_files: Optional[set[str]] = None,
) -> FinishResult:
    """Block until the test finishes or times out.

    *initial_files* is the set of files that existed before the test started
    (in result_file_dir) so we only trigger on NEW files.
    """
    os.makedirs(artifacts_dir, exist_ok=True)
    start = time.monotonic()
    initial = initial_files or set()

    logger.info("Finish detector started (timeout=%ds, poll=%ds, dir=%s, glob=%s)",
                cfg.timeout_sec, cfg.poll_interval_sec,
                cfg.result_file_dir, cfg.result_file_glob,
                extra={"action": "finish_detector", "step": "start"})

    poll_count = 0
    while True:
        elapsed = time.monotonic() - start

        if elapsed >= cfg.timeout_sec:
            return FinishResult(
                finished=False, method="timeout",
                elapsed_sec=elapsed, timed_out=True,
                detail=f"Timed out after {cfg.timeout_sec}s",
            )

        poll_count += 1

        found = _check_result_file(cfg, initial)
        if found:
            logger.info("Result file detected: %s (after %.0fs, %d polls)",
                        found, elapsed, poll_count,
                        extra={"action": "finish_detector", "step": "file_found"})
            return FinishResult(
                finished=True, method="result_file",
                elapsed_sec=elapsed, detail=found,
            )

        kw = _check_log_keyword(cfg)
        if kw:
            is_fail = kw.startswith("FAIL_FAST:")
            logger.info("Log keyword detected: %s", kw,
                        extra={"action": "finish_detector", "step": "log_keyword"})
            return FinishResult(
                finished=True, method="log_keyword",
                elapsed_sec=elapsed, detail=kw,
                failed_fast=is_fail,
            )

        ui = _check_ui_text(cfg, artifacts_dir)
        if ui:
            logger.info("UI text detected: %s", ui,
                        extra={"action": "finish_detector", "step": "ui_text"})
            return FinishResult(
                finished=True, method="ui_text",
                elapsed_sec=elapsed, detail=ui,
            )

        if poll_count % 60 == 0:
            logger.info("Still waiting... %.0fs elapsed, %d polls",
                        elapsed, poll_count,
                        extra={"action": "finish_detector", "step": "heartbeat"})

        remaining = cfg.timeout_sec - elapsed
        sleep_time = min(cfg.poll_interval_sec, remaining)
        if sleep_time > 0:
            time.sleep(sleep_time)
