"""Playwright driver for Netgear RS700 router.

Uses the BASIC > Wireless tri-band page (WLG_wireless_tri_band.htm) which
contains all 3 bands (2.4G, 5G, 6G) on a single page.  Each band has its
own set of fields with different name suffixes: (none), _an, _an_2.
A single Apply button submits all bands at once.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Frame

from orchestrator.logging.json_logger import get_logger
from orchestrator.utils.retry import retry_async
from orchestrator.utils.timeouts import (
    ROUTER_APPLY_TIMEOUT,
    ROUTER_LOGIN_TIMEOUT,
    ROUTER_NAVIGATE_TIMEOUT,
    POLL_INTERVAL,
    POLL_BACKOFF,
)
from router.netgear_rs700.selectors import (
    BandConfig,
    BandFieldMap,
    BAND_FIELDS,
    TRI_BAND_PAGE,
    APPLY_BUTTON,
    SECURITY_VALUES,
    SECURITY_VALUES_6G,
)
from router.netgear_rs700.evidence import collect_evidence

logger = get_logger("rs700_driver")


class NetgearRS700Driver:
    def __init__(self, base_url: str = "http://192.168.1.1", artifacts_dir: str = "artifacts"):
        self.base_url = base_url.rstrip("/")
        self.artifacts_dir = os.path.abspath(artifacts_dir)
        os.makedirs(self.artifacts_dir, exist_ok=True)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._formframe: Optional[Frame] = None

    async def open(self) -> None:
        logger.info("Opening browser for %s", self.base_url,
                     extra={"action": "open", "step": "start"})
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

    async def login(self, user: str, password: str) -> None:
        """Login via HTTP Basic Auth — create context with http_credentials."""
        logger.info("Logging in as %s (HTTP Basic Auth)", user,
                     extra={"action": "login", "step": "start"})
        self._context = await self._browser.new_context(
            ignore_https_errors=True,
            http_credentials={"username": user, "password": password},
            record_har_path=os.path.join(self.artifacts_dir, "network.har"),
        )
        await self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(ROUTER_LOGIN_TIMEOUT * 1000)

        async def _navigate():
            await self._page.goto(
                self.base_url,
                wait_until="domcontentloaded",
                timeout=ROUTER_LOGIN_TIMEOUT * 1000,
            )

        try:
            await retry_async(_navigate, max_retries=3, backoff=2.0, timeout=60.0)
            await self._page.wait_for_timeout(3000)

            if "start.htm" not in self._page.url and "index.htm" not in self._page.url:
                raise RuntimeError(
                    f"Login may have failed. URL={self._page.url}. "
                    "Expected start.htm or index.htm after Basic Auth."
                )

            formframe = self._page.frame("formframe")
            if formframe is None:
                raise RuntimeError(
                    f"formframe not found after login. URL={self._page.url}, "
                    f"frames={[f.name for f in self._page.frames]}"
                )
            self._formframe = formframe
            await self._dismiss_modal(formframe)
            logger.info(
                "Login successful (formframe=%s)", formframe.url,
                extra={"action": "login", "step": "done"},
            )
        except Exception as exc:
            logger.error("Login failed: %s", exc,
                         extra={"action": "login", "step": "error"})
            await collect_evidence(self._page, self._context, self.artifacts_dir, "login_fail")
            raise

    async def _dismiss_modal(self, frame: Frame) -> None:
        """Hide the Netgear SSO/Nighthawk-app modal that overlays the page."""
        try:
            await frame.evaluate("""
                document.querySelectorAll(
                    '.modal, #modalBox, form[name="SSOAPI"], .modal-backdrop'
                ).forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    el.style.pointerEvents = 'none';
                });
            """)
        except Exception:
            pass

    async def _navigate_to_tri_band(self) -> None:
        """Navigate formframe to the tri-band wireless settings page."""
        frame = self._formframe
        url = f"{self.base_url}{TRI_BAND_PAGE}"
        logger.info("Navigating to tri-band page %s", TRI_BAND_PAGE,
                     extra={"action": "navigate", "step": "start"})
        await frame.goto(url, wait_until="domcontentloaded",
                         timeout=ROUTER_NAVIGATE_TIMEOUT * 1000)
        await frame.wait_for_load_state("networkidle",
                                        timeout=ROUTER_NAVIGATE_TIMEOUT * 1000)
        await self._page.wait_for_timeout(2000)

        await self._dismiss_modal(frame)

        ssid_field = frame.locator(f"input[name='{BAND_FIELDS['2.4G'].ssid}']")
        if await ssid_field.count() == 0:
            raise RuntimeError(
                f"Tri-band page loaded but 2.4G SSID field not found. URL={frame.url}"
            )
        logger.info("Tri-band page loaded", extra={"action": "navigate", "step": "done"})

    async def detect_available_bands(self) -> list[str]:
        """Detect which bands are present on the tri-band page."""
        await self._navigate_to_tri_band()
        frame = self._formframe
        detected: list[str] = []
        for band, fields in BAND_FIELDS.items():
            ssid_loc = frame.locator(f"input[name='{fields.ssid}']")
            if await ssid_loc.count() > 0:
                detected.append(band)
        logger.info("Detected bands: %s", detected,
                     extra={"action": "detect_bands", "step": "done"})
        return detected

    async def _select_channel(self, frame: Frame, fields: BandFieldMap, channel: str) -> None:
        """Select a channel value in the band's channel dropdown."""
        ch_select = frame.locator(f"select[name='{fields.channel}']")
        if await ch_select.count() == 0:
            logger.warning("Channel select '%s' not found", fields.channel,
                           extra={"action": "set_wireless", "step": "no_channel_select"})
            return

        try:
            await ch_select.select_option(value=channel, timeout=3000)
            return
        except Exception:
            pass

        try:
            await ch_select.select_option(label=channel, timeout=3000)
            return
        except Exception:
            pass

        options = ch_select.locator("option")
        count = await options.count()
        for i in range(count):
            opt = options.nth(i)
            label = (await opt.inner_text()).strip()
            if label.startswith(channel) and (
                len(label) == len(channel) or not label[len(channel)].isdigit()
            ):
                val = await opt.get_attribute("value") or label
                await ch_select.select_option(value=val)
                logger.info("Channel %s matched option '%s' (value=%s)",
                            channel, label, val,
                            extra={"action": "set_wireless", "step": "channel_match"})
                return

        logger.warning("Channel %s not found in selector '%s'",
                       channel, fields.channel,
                       extra={"action": "set_wireless", "step": "channel_miss"})

    async def _fill_band(self, frame: Frame, band: str,
                          fields: BandFieldMap, cfg: BandConfig) -> None:
        """Fill SSID, passphrase, security, and channel for one band."""
        logger.info("Filling %s band (ssid=%s, sec=%s, ch=%s)",
                     band, cfg.ssid, cfg.security, cfg.channel,
                     extra={"action": "set_wireless", "step": f"{band}_fill"})

        ssid_loc = frame.locator(f"input[name='{fields.ssid}']")
        await ssid_loc.fill(cfg.ssid)

        sec_map = SECURITY_VALUES_6G if band == "6G" else SECURITY_VALUES
        sec_value = sec_map.get(cfg.security, cfg.security)
        sec_radio = frame.locator(
            f"input[name='{fields.security_radio}'][value='{sec_value}']"
        )
        if await sec_radio.count() > 0:
            if not await sec_radio.is_checked():
                await sec_radio.check(force=True)
                await self._page.wait_for_timeout(500)

        pass_loc = frame.locator(f"input[name='{fields.passphrase}']")
        if await pass_loc.count() > 0 and await pass_loc.is_visible():
            await pass_loc.fill(cfg.password)

        if cfg.channel:
            await self._select_channel(frame, fields, cfg.channel)

    async def set_wireless(self, band_configs: dict[str, BandConfig]) -> None:
        """Configure all requested bands on the tri-band page and click Apply once."""
        await self._navigate_to_tri_band()
        frame = self._formframe

        for band, cfg in band_configs.items():
            fields = BAND_FIELDS.get(band)
            if fields is None:
                logger.warning("Unknown band %s, skipping", band,
                               extra={"action": "set_wireless", "step": "skip"})
                continue

            ssid_loc = frame.locator(f"input[name='{fields.ssid}']")
            if await ssid_loc.count() == 0:
                logger.warning("Band %s SSID field not found, skipping", band,
                               extra={"action": "set_wireless", "step": "skip"})
                continue

            await self._fill_band(frame, band, fields, cfg)

        await self._dismiss_modal(frame)
        for parent_frame in self._page.frames:
            await self._dismiss_modal(parent_frame)

        apply_btn = frame.locator(APPLY_BUTTON)
        if await apply_btn.count() > 0:
            try:
                await apply_btn.first.click(force=True)
            except Exception:
                await frame.evaluate(
                    "document.querySelector(\"button#apply, button[name='Apply']\").click()"
                )
            logger.info("Apply clicked for all bands",
                         extra={"action": "apply", "step": "clicked"})
            await self._page.wait_for_timeout(8000)
        else:
            logger.warning("No Apply button found on tri-band page",
                           extra={"action": "apply", "step": "no_button"})

        await self.wait_until_ready()

    async def apply(self) -> None:
        """No-op — apply is done in set_wireless."""
        pass

    async def navigate_to_wireless(self) -> None:
        """Navigate to the tri-band wireless page."""
        await self._navigate_to_tri_band()

    async def wait_until_ready(self, timeout: float = ROUTER_APPLY_TIMEOUT) -> None:
        """Poll the router until it becomes reachable after apply."""
        logger.info("Waiting for router to become ready (timeout=%ss)", timeout,
                     extra={"action": "wait_ready", "step": "start"})
        interval = POLL_INTERVAL
        elapsed = 0.0
        router_user = os.environ.get("ROUTER_USER", "admin")
        router_pass = os.environ.get("ROUTER_PASS", "")
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
            try:
                async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                    resp = await client.get(
                        self.base_url, follow_redirects=True,
                        auth=(router_user, router_pass),
                    )
                    if resp.status_code < 500:
                        logger.info(
                            "Router reachable (status=%d, elapsed=%.1fs)",
                            resp.status_code, elapsed,
                            extra={"action": "wait_ready", "step": "reachable"},
                        )
                        return
            except Exception:
                logger.info("Router not ready yet (elapsed=%.1fs)", elapsed,
                            extra={"action": "wait_ready", "step": "polling"})
            interval = min(interval * POLL_BACKOFF, 15)
        raise TimeoutError(f"Router not reachable after {timeout}s")

    async def read_band_status(self, band: str) -> dict:
        """Read current SSID and channel for a specific band from the tri-band page."""
        fields = BAND_FIELDS.get(band)
        if fields is None:
            return {}

        frame = self._formframe
        if frame is None:
            return {}

        if TRI_BAND_PAGE not in (frame.url or ""):
            try:
                await self._navigate_to_tri_band()
                frame = self._formframe
            except Exception:
                return {}

        ssid_loc = frame.locator(f"input[name='{fields.ssid}']")
        ssid_val = ""
        if await ssid_loc.count() > 0:
            ssid_val = await ssid_loc.get_attribute("value") or ""

        ch_loc = frame.locator(f"select[name='{fields.channel}']")
        ch_val = ""
        if await ch_loc.count() > 0:
            try:
                ch_val = await ch_loc.input_value()
            except Exception:
                pass

        pass_loc = frame.locator(f"input[name='{fields.passphrase}']")
        pass_val = ""
        if await pass_loc.count() > 0:
            try:
                pass_val = await pass_loc.get_attribute("value") or ""
            except Exception:
                pass

        sec_name = fields.security_radio
        sec_val = ""
        try:
            checked = frame.locator(f"input[name='{sec_name}']:checked")
            if await checked.count() > 0:
                sec_val = await checked.get_attribute("value") or ""
        except Exception:
            pass

        return {
            "ssid": ssid_val,
            "channel": ch_val,
            "passphrase": pass_val,
            "security": sec_val,
        }

    async def read_all_bands(self) -> dict[str, dict]:
        """Read status for all bands from a single page load."""
        await self._navigate_to_tri_band()
        result = {}
        for band in BAND_FIELDS:
            info = await self.read_band_status(band)
            if info.get("ssid"):
                result[band] = info
        return result

    async def close(self) -> None:
        logger.info("Closing browser", extra={"action": "close", "step": "start"})
        try:
            if self._context:
                try:
                    await self._context.tracing.stop(
                        path=os.path.join(self.artifacts_dir, "trace.zip"))
                except Exception:
                    pass
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as exc:
            logger.error("Close error: %s", exc,
                         extra={"action": "close", "step": "error"})
        logger.info("Browser closed", extra={"action": "close", "step": "done"})
