"""Restart the LabVIEW application completely."""
import subprocess
import time
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.local_automation.screen_utils import (
    capture_window, get_window_rect, set_window_rect,
    save_screenshot, close_window,
)
import orchestrator.local_automation.labview_runner as lv_runner
from orchestrator.local_automation.labview_runner import (
    _enum_lv_windows, _force_fg, find_labview_window,
)

user32 = ctypes.windll.user32

wins = _enum_lv_windows()
for h, t, w, ht, r in wins:
    print(f"Closing: {t!r} (hwnd={h})")
    close_window(h)

print("Killing visible LabVIEW crash reporters...")
subprocess.run(
    [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-Process | Where-Object { $_.MainWindowTitle -like '*Crash Reporter*' } | Stop-Process -Force",
    ],
    capture_output=True,
    text=True,
)

time.sleep(5.0)

wins2 = _enum_lv_windows()
if wins2:
    print(f"Still {len(wins2)} windows after close attempt:")
    for h, t, w, ht, r in wins2:
        print(f"  lingering hwnd={h} title={t!r}")
else:
    print("All visible LabVIEW windows closed")

print("Killing lingering LabVIEW process tree...")
subprocess.run(
    ["taskkill", "/IM", "480.000.v2.03.exe", "/F", "/T"],
    capture_output=True,
    text=True,
)
time.sleep(3.0)

exe = r"C:\480.builds\v2.03\480.000.v2.03.exe"
if not os.path.isfile(exe):
    print(f"EXE not found: {exe}")
    sys.exit(1)

print(f"Launching: {exe}")
subprocess.Popen([exe])

lv_runner.LV_PID = None

for i in range(30):
    time.sleep(2)
    hwnd = find_labview_window()
    if hwnd:
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        print(f"Found window: {title.value!r} (hwnd={hwnd})")
        time.sleep(8.0)

        for h, t, w, ht, r in _enum_lv_windows():
            print(f"  hwnd={h} title={t!r}")

        set_window_rect(hwnd, 0, 0, 1288, 860)
        time.sleep(0.5)
        _force_fg(hwnd)
        time.sleep(0.5)
        img = capture_window(hwnd)
        save_screenshot(img, "artifacts", "diag_relaunched.png")
        print("Relaunched and captured")
        break
else:
    print("LabVIEW did not start within timeout")
