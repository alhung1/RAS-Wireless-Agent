"""Netgear RS700-specific selectors.

The RS700 firmware uses:
  - HTTP Basic Auth (401 challenge, no HTML login form)
  - After auth -> start.htm with frameset: topframe + formframe
  - BASIC > Wireless page: WLG_wireless_tri_band.htm
    Contains all 3 bands (2.4G, 5G, 6G) on a single page.
    Each band uses a different suffix: (none), _an, _an_2.
    Single Apply button submits all bands at once to wireless.cgi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BandConfig:
    """Per-band wireless configuration passed by the caller."""
    ssid: str
    password: str
    channel: Optional[str] = None
    security: str = "wpa2"


@dataclass(frozen=True)
class BandFieldMap:
    """Maps a band to its field names on the tri-band page."""
    ssid: str
    passphrase: str
    channel: str
    security_radio: str
    mode: str
    ssid_broadcast: str
    isolation: str
    setting_div_id: str
    init_channel_hidden: str


TRI_BAND_PAGE = "/WLG_wireless_tri_band.htm"

BAND_FIELDS: dict[str, BandFieldMap] = {
    "2.4G": BandFieldMap(
        ssid="ssid",
        passphrase="passphrase",
        channel="w_channel",
        security_radio="security_type",
        mode="opmode",
        ssid_broadcast="ssid_bc",
        isolation="enable_isolation",
        setting_div_id="setting_2G",
        init_channel_hidden="initChannel",
    ),
    "5G": BandFieldMap(
        ssid="ssid_an",
        passphrase="passphrase_an",
        channel="w_channel_an",
        security_radio="security_type_an",
        mode="opmode_an",
        ssid_broadcast="ssid_bc_an",
        isolation="enable_isolation_an",
        setting_div_id="setting_5G",
        init_channel_hidden="initChannel_an",
    ),
    "6G": BandFieldMap(
        ssid="ssid_an_2",
        passphrase="passphrase_an_2",
        channel="w_channel_an_2",
        security_radio="security_type_an_2",
        mode="opmode_an_2",
        ssid_broadcast="ssid_bc_an_2",
        isolation="enable_isolation_an_2",
        setting_div_id="setting_6G",
        init_channel_hidden="initChannel_an_2",
    ),
}

APPLY_BUTTON = "button#apply, input#apply, button[name='Apply']"

SECURITY_VALUES = {
    "disable": "Disable",
    "wpa2": "WPA2-PSK",
    "auto": "AUTO-PSK",
    "wpa3": "WPA3-Personal",
    "wpa3-mixed": "WPA3-Mixed",
    "owe": "OWE",
    "wpa3-sae": "WPA3-Personal",
}

SECURITY_VALUES_6G = {
    "owe": "OWE",
    "wpa3": "WPA3-Personal",
    "wpa3-sae": "WPA3-Personal",
    "disable": "OWE",
}
