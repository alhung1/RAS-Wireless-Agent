"""All pixel constants, window sizes, and UI layout mappings.

Single source of truth for every hardcoded coordinate in the LabVIEW
v2.03 automation.  Product-agnostic: these describe the LabVIEW UI
layout, not any specific test product.

Calibrated on a 2560x1440 display with 125% DPI scaling.
Window positioned at (0,0) with logical size 1288x1040.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Window sizes (width, height)
# ---------------------------------------------------------------------------

STEP_WINDOW_SIZE = (1288, 1040)
LOGIN_WINDOW_SIZE = (356, 200)
MAIN_WINDOW_SIZE = (1288, 860)
POPUP_SIZE = (800, 900)

WINDOW_WIDTH = 1288
WINDOW_HEIGHT = 1040

# ---------------------------------------------------------------------------
# Step-level retry defaults
# ---------------------------------------------------------------------------

MAX_STEP_RETRIES = 2
RETRY_DELAY_SEC = 2.0

# ---------------------------------------------------------------------------
# Navigation arrows
# ---------------------------------------------------------------------------

ORANGE_ARROW_PX = (1183, 976)
ORANGE_ARROW_LEFT_PX = (60, 977)

# ---------------------------------------------------------------------------
# Step 01: Main screen
# ---------------------------------------------------------------------------

THROUGHPUT_ICON_PX = (130, 240)

# ---------------------------------------------------------------------------
# Step 02: Login dialog (relative to login window)
# ---------------------------------------------------------------------------

LOGIN_USERNAME_PX = (218, 75)
LOGIN_PASSWORD_PX = (218, 129)
LOGIN_GREEN_OK_FALLBACK_PX = (290, 170)

# ---------------------------------------------------------------------------
# Step 03: Test type screen (400 600 test.vi)
# ---------------------------------------------------------------------------

TEST_TYPE_DROPDOWN_PX = (330, 368)

# ---------------------------------------------------------------------------
# Step 05: Freq / Channel screen (481.300.vi)
# ---------------------------------------------------------------------------

FREQ_RANGE_DROPDOWN_PX = (511, 344)
RF_CHANNEL_2G_PX = (460, 752)
RF_CHANNEL_5G_PX = (655, 752)
RF_CHANNEL_6G_PX = (850, 753)
USER_INFO_FIELD_PX = (690, 845)

# ---------------------------------------------------------------------------
# Step 06: Select AP
# ---------------------------------------------------------------------------

AP_ICON_CLICK_PX = (100, 350)

# ---------------------------------------------------------------------------
# Step 07: Use Last AP
# ---------------------------------------------------------------------------

FIRMWARE_REV_FIELD_PX = (610, 335)
USE_LAST_AP_TOGGLE_PX = (700, 229)

# ---------------------------------------------------------------------------
# Step 08: Select Client
# ---------------------------------------------------------------------------

CLIENT_USB_IMAGE_PX = (100, 348)
CLIENT_TEXT_BUTTON_PX = (225, 350)

# ---------------------------------------------------------------------------
# Step 10: Use Last DUT
# ---------------------------------------------------------------------------

USE_LAST_DUT_TOGGLE_PX = (1060, 895)

# ---------------------------------------------------------------------------
# Step 11: IP address / Band select (400 600 IP address Dual LAN.vi)
# ---------------------------------------------------------------------------

IP_BUTTON_1_PX = (360, 830)
IP_2G_DROPDOWN_PX = (600, 552)
IP_2G_ITEM_3_PX = (600, 646)
IP_5G_DROPDOWN_PX = (920, 552)
IP_5G_ITEM_3_PX = (920, 646)
NEUTRAL_CLICK_PX = (400, 300)

# ---------------------------------------------------------------------------
# Step 12: Chariot pairs
# ---------------------------------------------------------------------------

PAIRS_2G_FIELD_PX = (580, 406)
PAIRS_5G_FIELD_PX = (580, 706)

# ---------------------------------------------------------------------------
# Step 14: MODE (400 600 MODE.vi)
# ---------------------------------------------------------------------------

MODE_DROPDOWN_PX = (249, 757)

# ---------------------------------------------------------------------------
# Step 15: Attenuation (481.300 atten.vi)
# ---------------------------------------------------------------------------

START_ATTEN_FIELD_PX = (153, 496)
STEP_SIZE_FIELD_PX = (566, 496)
STEPS_FIELD_PX = (750, 496)

# ---------------------------------------------------------------------------
# Step 16: Design stage (400 600 Chariot.vi)
# ---------------------------------------------------------------------------

DESIGN_STAGE_DROPDOWN_PX = (734, 491)

# ---------------------------------------------------------------------------
# Step 17: Region (400 600 REGION.vi)
# ---------------------------------------------------------------------------

REGION_DROPDOWN_PX = (295, 488)

# ---------------------------------------------------------------------------
# Popup / Done button
# ---------------------------------------------------------------------------

DONE_BUTTON_FALLBACK_PX = (480, 870)

# ---------------------------------------------------------------------------
# Screen title hints (for window identification)
# ---------------------------------------------------------------------------

SCREEN_TITLE_HINTS: dict[str, str | None] = {
    "step_03": "400 600 test",
    "step_04": "table position",
    "step_05": "481",
    "step_11": "IP address",
    "step_13": None,
    "step_14": "MODE",
    "step_15": "atten",
    "step_16": "Chariot",
    "step_17": "REGION",
}

# ---------------------------------------------------------------------------
# Template file names (for template matching)
# ---------------------------------------------------------------------------

SCREEN_TEMPLATES: dict[str, str | None] = {
    "step_01": "throughput_tab.png",
    "step_02": "green_ok_button.png",
    "step_03": "test_type_screen.png",
    "step_05": "freq_channel_screen.png",
    "step_11": "ip_address_screen.png",
    "step_14": "mode_screen.png",
    "step_15": "atten_screen.png",
    "step_16": "design_stage_screen.png",
    "step_17": "region_screen.png",
}

TEMPLATE_NAMES = {
    "throughput_tab": "throughput_tab.png",
    "green_ok_button": "green_ok_button.png",
    "orange_arrow": "orange_arrow.png",
    "done_button": "done_button.png",
    "netgear_logo": "netgear_logo.png",
    "please_wait": "please_wait.png",
    "test_running": "test_running.png",
}

# ---------------------------------------------------------------------------
# Folder paths (LabVIEW listbox data sources)
# ---------------------------------------------------------------------------

AP_FOLDER = r"E:\AP"
CLIENT_FOLDER = r"E:\Client"

# ---------------------------------------------------------------------------
# Default window title search hints
# ---------------------------------------------------------------------------

DEFAULT_LV_TITLE_HINTS = ["480", "481", "400 600", "RvR", "logon", "table"]

POPUP_TITLE_HINTS = ["503 POP UP", "show msg", "Information window",
                     "display status"]
BLOCKER_TITLE_HINTS = ["480_214", "8002", "list in folder"]
