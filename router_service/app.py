"""Router-control FastAPI service — runs on 22.100 (Layer 4).

This service runs on the machine that has a wired LAN connection to the
router (192.168.1.x).  It exposes a small HTTP API that the orchestrator
calls over the safe 22.x management network.  Playwright browser
automation happens **locally** on this machine, so the orchestrator never
needs a route to 192.168.1.x.

Start:
    uvicorn router_service.app:app --host 0.0.0.0 --port 8081
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from orchestrator.logging.json_logger import get_logger
from router.netgear_rs700.driver import NetgearRS700Driver
from router.netgear_rs700.selectors import BandConfig

load_dotenv()
logger = get_logger("router_service")

INSTALL_DIR = os.path.abspath(".")
PW_BROWSERS_DIR = os.path.join(INSTALL_DIR, ".playwright")
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = PW_BROWSERS_DIR

SERVICE_BIND_IP = os.environ.get("SERVICE_BIND_IP", "0.0.0.0")
SERVICE_MODE = os.environ.get("SERVICE_MODE", "lab")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")

app = FastAPI(
    title="Router Control Service",
    description="Runs on 22.100 — proxies Playwright router commands for the orchestrator.",
    version="1.0.0",
)

ARTIFACTS_DIR = os.path.join(INSTALL_DIR, "artifacts", "router_service")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

ROUTER_USER = os.environ.get("ROUTER_USER", "admin")
ROUTER_PASS = os.environ.get("ROUTER_PASS", "")

TASK_NAME = "RASAgent-RouterService"


def _load_build_info() -> dict:
    path = os.path.join(INSTALL_DIR, "build_info.json")
    if os.path.isfile(path):
        import json as _json
        with open(path, encoding="utf-8") as f:
            return _json.load(f)
    version_path = os.path.join(INSTALL_DIR, "VERSION")
    if os.path.isfile(version_path):
        with open(version_path) as f:
            return {"version": f.read().strip()}
    return {}


_BUILD_INFO = _load_build_info()


@app.on_event("startup")
async def _validate_bind_ip():
    """Secondary safety check: warn/reject if bind IP is inappropriate."""
    if SERVICE_MODE == "production" and SERVICE_BIND_IP == "0.0.0.0":
        logger.error(
            "SERVICE_BIND_IP=0.0.0.0 rejected in production mode. "
            "Set SERVICE_BIND_IP to the 22-domain IP in .env.",
            extra={"action": "startup", "step": "bind_rejected"},
        )
        sys.exit(1)
    if SERVICE_BIND_IP == "0.0.0.0":
        logger.warning(
            "SERVICE_BIND_IP=0.0.0.0 (lab mode). "
            "Set to 22-domain IP for production.",
            extra={"action": "startup", "step": "bind_warning"},
        )


@app.on_event("startup")
async def _validate_admin_api_key():
    """Validate ADMIN_API_KEY is set in production mode."""
    if SERVICE_MODE != "lab" and not ADMIN_API_KEY:
        logger.error(
            "ADMIN_API_KEY not set in production mode. "
            "Set ADMIN_API_KEY in .env for admin endpoints.",
            extra={"action": "startup", "step": "api_key_rejected"},
        )
        sys.exit(1)
    if SERVICE_MODE == "lab" and not ADMIN_API_KEY:
        logger.warning(
            "ADMIN_API_KEY not set (lab mode). "
            "Admin endpoints are unprotected.",
            extra={"action": "startup", "step": "api_key_warning"},
        )


async def require_admin_key(x_api_key: str = Header(None)) -> str:
    """Dependency: verify X-API-Key header matches ADMIN_API_KEY.

    In lab mode, allows access if no key is configured.
    In production mode, key is required and must match.
    """
    if not ADMIN_API_KEY:
        if SERVICE_MODE != "lab":
            raise HTTPException(status_code=403, detail="ADMIN_API_KEY not configured")
        # Lab mode with no key: allow
        return ""

    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing X-API-Key header")

    return x_api_key


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class BandConfigRequest(BaseModel):
    ssid: str
    password: str
    channel: Optional[str] = None
    security: str = "wpa2"


class RouterApplyRequest(BaseModel):
    base_url: str = "http://192.168.1.1"
    bands: dict[str, BandConfigRequest]
    router_user: Optional[str] = None
    router_pass: Optional[str] = None


class RouterApplyResponse(BaseModel):
    success: bool
    detected_bands: list[str] = Field(default_factory=list)
    configured_bands: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class RouterStatusBand(BaseModel):
    ssid: Optional[str] = None
    channel: Optional[str] = None
    passphrase: Optional[str] = None
    security: Optional[str] = None


class RouterStatusResponse(BaseModel):
    success: bool
    bands: dict[str, RouterStatusBand] = Field(default_factory=dict)
    error: Optional[str] = None


class DetectBandsResponse(BaseModel):
    success: bool
    bands: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    router_reachable: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Quick liveness check — also probes whether the router LAN is reachable."""
    import httpx
    reachable = False
    try:
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            resp = await client.get(
                "http://192.168.1.1",
                follow_redirects=True,
                auth=(ROUTER_USER, ROUTER_PASS),
            )
            reachable = resp.status_code < 500
    except Exception:
        pass
    return HealthResponse(status="ok", router_reachable=reachable)


@app.get("/router/debug-login")
async def debug_login_page():
    """Load the router login page and return its HTML for selector debugging."""
    from playwright.async_api import async_playwright
    html = ""
    url = ""
    screenshot_b64 = ""
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        await page.goto("http://192.168.1.1", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        url = page.url
        html = await page.content()
        import base64
        screenshot_bytes = await page.screenshot()
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
        await ctx.close()
        await browser.close()
        await pw.stop()
    except Exception as exc:
        html = f"ERROR: {exc}"
    return {"url": url, "html": html, "screenshot_b64": screenshot_b64}


@app.post("/router/apply", response_model=RouterApplyResponse)
async def router_apply(req: RouterApplyRequest):
    """Configure router wireless settings via Playwright.

    The orchestrator sends band configs over the 22.x network; this
    service runs the browser automation locally against the router LAN.
    """
    user = req.router_user or ROUTER_USER
    password = req.router_pass or ROUTER_PASS
    if not password:
        raise HTTPException(status_code=400, detail="Router password not configured")

    band_configs: dict[str, BandConfig] = {}
    for band_key, bcr in req.bands.items():
        band_configs[band_key] = BandConfig(
            ssid=bcr.ssid,
            password=bcr.password,
            channel=bcr.channel,
            security=bcr.security,
        )

    driver = NetgearRS700Driver(base_url=req.base_url, artifacts_dir=ARTIFACTS_DIR)
    try:
        await driver.open()
        await driver.login(user, password)

        await driver.set_wireless(band_configs)

        logger.info("Router settings applied via service",
                     extra={"action": "router_apply", "step": "done"})
        return RouterApplyResponse(
            success=True,
            detected_bands=list(band_configs.keys()),
            configured_bands=list(band_configs.keys()),
        )
    except Exception as exc:
        logger.error("Router apply failed: %s", exc,
                     extra={"action": "router_apply", "step": "error"})
        return RouterApplyResponse(success=False, error=str(exc))
    finally:
        await driver.close()


@app.post("/router/detect-bands", response_model=DetectBandsResponse)
async def router_detect_bands(
    base_url: str = "http://192.168.1.1",
    router_user: Optional[str] = None,
    router_pass: Optional[str] = None,
):
    """Detect which bands the router supports (read-only, no apply)."""
    user = router_user or ROUTER_USER
    password = router_pass or ROUTER_PASS

    driver = NetgearRS700Driver(base_url=base_url, artifacts_dir=ARTIFACTS_DIR)
    try:
        await driver.open()
        await driver.login(user, password)
        detected = await driver.detect_available_bands()
        return DetectBandsResponse(success=True, bands=detected)
    except Exception as exc:
        logger.error("Band detection failed: %s", exc,
                     extra={"action": "detect_bands", "step": "error"})
        return DetectBandsResponse(success=False, error=str(exc))
    finally:
        await driver.close()


@app.get("/router/status", response_model=RouterStatusResponse)
async def router_status():
    """Read current SSID, channel, passphrase, and security per band."""
    user = ROUTER_USER
    password = ROUTER_PASS

    driver = NetgearRS700Driver(artifacts_dir=ARTIFACTS_DIR)
    try:
        await driver.open()
        await driver.login(user, password)

        all_bands = await driver.read_all_bands()
        bands: dict[str, RouterStatusBand] = {}
        for band_key, info in all_bands.items():
            bands[band_key] = RouterStatusBand(
                ssid=info.get("ssid"),
                channel=info.get("channel"),
                passphrase=info.get("passphrase"),
                security=info.get("security"),
            )

        return RouterStatusResponse(success=True, bands=bands)
    except Exception as exc:
        logger.error("Router status failed: %s", exc,
                     extra={"action": "router_status", "step": "error"})
        return RouterStatusResponse(success=False, error=str(exc))
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# Admin endpoints — remote deployment & lifecycle
# ---------------------------------------------------------------------------


class UpdateRequest(BaseModel):
    zip_url: str
    restart: bool = True


class UpdateResponse(BaseModel):
    success: bool
    message: str = ""
    error: Optional[str] = None


class RestartResponse(BaseModel):
    success: bool
    message: str = ""


@app.post("/admin/update", response_model=UpdateResponse)
async def admin_update(req: UpdateRequest, _: str = Depends(require_admin_key)):
    """Download new code from orchestrator and replace the install directory.

    Steps:
      1. Download zip from ``req.zip_url``
      2. Extract to a staging dir
      3. Swap code files (preserve .venv and .env)
      4. Optionally restart via scheduled task
    """
    import httpx as _httpx

    logger.info("Admin update from %s", req.zip_url,
                extra={"action": "admin_update", "step": "start"})

    staging = os.path.join(tempfile.gettempdir(), "RASAgent_update")
    zip_path = os.path.join(tempfile.gettempdir(), "RASAgent_update.zip")

    try:
        async with _httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(req.zip_url)
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                f.write(resp.content)
        logger.info("Downloaded %d bytes", os.path.getsize(zip_path),
                     extra={"action": "admin_update", "step": "downloaded"})

        if os.path.exists(staging):
            shutil.rmtree(staging)
        shutil.unpack_archive(zip_path, staging)
        os.remove(zip_path)

        src = staging
        nested = [d for d in os.listdir(staging)
                  if os.path.isdir(os.path.join(staging, d))]
        if len(nested) == 1 and os.path.exists(
                os.path.join(staging, nested[0], "requirements.txt")):
            src = os.path.join(staging, nested[0])

        preserve = {".venv", ".env", ".playwright", "artifacts"}
        for item in os.listdir(INSTALL_DIR):
            if item in preserve:
                continue
            path = os.path.join(INSTALL_DIR, item)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)

        for item in os.listdir(src):
            if item in preserve:
                continue
            s = os.path.join(src, item)
            d = os.path.join(INSTALL_DIR, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        shutil.rmtree(staging, ignore_errors=True)
        logger.info("Code updated in %s", INSTALL_DIR,
                     extra={"action": "admin_update", "step": "swapped"})

        if req.restart:
            _schedule_restart()
            return UpdateResponse(
                success=True,
                message="Code updated. Service restarting via scheduled task.",
            )

        return UpdateResponse(success=True, message="Code updated. Restart skipped.")

    except Exception as exc:
        logger.error("Admin update failed: %s", exc,
                     extra={"action": "admin_update", "step": "error"})
        return UpdateResponse(success=False, error=str(exc))


@app.get("/admin/version")
async def admin_version():
    """Return build version, commit, and runtime info."""
    import platform
    return {
        **_BUILD_INFO,
        "python": platform.python_version(),
        "service_mode": SERVICE_MODE,
        "bind_ip": SERVICE_BIND_IP,
    }


@app.post("/admin/restart", response_model=RestartResponse)
async def admin_restart(_: str = Depends(require_admin_key)):
    """Restart the service by stopping and re-starting the scheduled task."""
    try:
        _schedule_restart()
        return RestartResponse(success=True, message="Restart initiated via scheduled task.")
    except Exception as exc:
        return RestartResponse(success=False, message=str(exc))


def _schedule_restart():
    """Restart via a detached batch file + os._exit(1) as fallback.

    Primary: a batch file that kills our PID, waits, then re-starts the task.
    The bat is launched with CREATE_BREAKAWAY_FROM_JOB so it survives
    the task scheduler terminating the job object.

    Fallback: if the batch file approach fails (e.g. BREAKAWAY not allowed),
    os._exit(1) triggers the scheduled task's RestartInterval policy (1 min).
    """
    import threading

    bat_path = os.path.join(tempfile.gettempdir(), "ras_restart.bat")
    my_pid = os.getpid()
    bat_content = (
        "@echo off\r\n"
        "timeout /t 3 /nobreak >nul\r\n"
        f"taskkill /f /pid {my_pid} >nul 2>&1\r\n"
        "timeout /t 8 /nobreak >nul\r\n"
        f'schtasks /run /tn "{TASK_NAME}"\r\n'
        f'del "%~f0"\r\n'
    )
    with open(bat_path, "w") as f:
        f.write(bat_content)

    CREATE_NEW_PROCESS_GROUP = 0x00000200
    DETACHED_PROCESS = 0x00000008
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000

    try:
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Restart batch launched (pid=%d): %s", my_pid, bat_path,
                     extra={"action": "admin_restart", "step": "bat_launched"})
    except OSError as e:
        logger.warning("Batch launch failed (%s), falling back to os._exit(1)", e,
                       extra={"action": "admin_restart", "step": "bat_failed"})

    def _fallback_exit():
        """Fallback: exit with code 1 so RestartInterval kicks in after ~1 min."""
        import time
        time.sleep(15)
        logger.info("Fallback: exiting with code 1 for task restart policy",
                     extra={"action": "admin_restart", "step": "fallback_exit"})
        os._exit(1)

    threading.Thread(target=_fallback_exit, daemon=True).start()


class FixPlaywrightResponse(BaseModel):
    success: bool
    message: str = ""
    source: Optional[str] = None


@app.post("/admin/fix-playwright", response_model=FixPlaywrightResponse)
async def admin_fix_playwright(_: str = Depends(require_admin_key)):
    """Copy Playwright browsers to the install-local .playwright directory.

    When the service runs as SYSTEM, Playwright looks in SYSTEM's LOCALAPPDATA
    which is different from the user who installed the browsers.  This endpoint
    searches for an existing Playwright install in any user profile and copies
    it to ``C:\\RASAgent\\.playwright``.
    """
    import glob as _glob

    if os.path.exists(os.path.join(PW_BROWSERS_DIR, "chromium_headless_shell-1208")):
        return FixPlaywrightResponse(
            success=True,
            message="Playwright browsers already in place.",
            source=PW_BROWSERS_DIR,
        )

    search_patterns = [
        r"C:\Users\*\AppData\Local\ms-playwright",
        r"C:\WINDOWS\system32\config\systemprofile\AppData\Local\ms-playwright",
    ]

    source = None
    for pattern in search_patterns:
        matches = _glob.glob(pattern)
        for m in matches:
            if os.path.isdir(m) and any(
                d.startswith("chromium") for d in os.listdir(m)
            ):
                source = m
                break
        if source:
            break

    if not source:
        return FixPlaywrightResponse(
            success=False,
            message="No Playwright browser installation found on this machine.",
        )

    logger.info("Copying Playwright browsers from %s to %s", source, PW_BROWSERS_DIR,
                extra={"action": "fix_playwright", "step": "copy"})

    if os.path.exists(PW_BROWSERS_DIR):
        shutil.rmtree(PW_BROWSERS_DIR)
    shutil.copytree(source, PW_BROWSERS_DIR)

    return FixPlaywrightResponse(
        success=True,
        message=f"Copied Playwright browsers to {PW_BROWSERS_DIR}",
        source=source,
    )


@app.get("/debug/probe-urls")
async def debug_probe_urls():
    """Fast URL probe: test candidate wireless page URLs via httpx from 22.100."""
    if SERVICE_MODE == "production":
        raise HTTPException(status_code=404, detail="Debug endpoints disabled in production mode")

    import httpx as _httpx

    user = ROUTER_USER
    password = ROUTER_PASS

    candidates = [
        "/WLG_wireless.htm",
        "/WLG_wireless2.htm",
        "/WLG_wireless3.htm",
        "/WLG_wireless4.htm",
        "/WLG_wireless5.htm",
        "/WLG_wireless6.htm",
        "/WLG_wireless_dual_498.htm",
        "/WLG_wireless_tri.htm",
        "/WLG_wireless_triband.htm",
        "/WLG_wireless_dual.htm",
        "/bas_wireless.htm",
        "/bas_wireLess.htm",
        "/BAS_wireless.htm",
        "/WLG_wireless_498.htm",
        "/WLG_wireless_basic.htm",
        "/WLG_wireless_allband.htm",
        "/WirelessSettings.htm",
        "/wifi.htm",
        "/WLG_wireless_tri_498.htm",
    ]

    results = []
    async with _httpx.AsyncClient(
        verify=False, timeout=8.0,
        auth=(user, password),
    ) as client:
        for path in candidates:
            url = f"http://192.168.1.1{path}"
            try:
                resp = await client.get(url, follow_redirects=True)
                body = resp.content
                has_ssid = b"ssid" in body.lower()
                has_5g = b"5g" in body.lower() or b"5ghz" in body.lower()
                has_6g = b"6g" in body.lower() or b"6ghz" in body.lower()
                has_pass = b"passphrase" in body.lower()
                title_start = body.find(b"<title>")
                title_end = body.find(b"</title>")
                title = body[title_start + 7:title_end].decode("utf-8", errors="replace") if title_start >= 0 and title_end > title_start else ""
                results.append({
                    "url": url, "path": path,
                    "status": resp.status_code, "final_url": str(resp.url),
                    "size": len(body), "title": title,
                    "has_ssid": has_ssid, "has_5g": has_5g,
                    "has_6g": has_6g, "has_passphrase": has_pass,
                })
            except Exception as e:
                results.append({"url": url, "path": path, "error": str(e)[:100]})

    return {"probes": results}


@app.get("/debug/fetch-page")
async def debug_fetch_page(url: str = "http://192.168.1.1/WLG_wireless.htm"):
    """Fetch raw HTML from a router page via httpx (with Basic Auth)."""
    if SERVICE_MODE == "production":
        raise HTTPException(status_code=404, detail="Debug endpoints disabled in production mode")

    import httpx as _httpx

    user = ROUTER_USER
    password = ROUTER_PASS
    async with _httpx.AsyncClient(
        verify=False, timeout=15.0, auth=(user, password),
    ) as client:
        resp = await client.get(url, follow_redirects=True)
        return {
            "url": url, "final_url": str(resp.url),
            "status": resp.status_code,
            "html": resp.text,
        }


@app.get("/debug/topframe-html")
async def debug_topframe_html():
    """Dump the topframe HTML after login for navigation analysis."""
    if SERVICE_MODE == "production":
        raise HTTPException(status_code=404, detail="Debug endpoints disabled in production mode")

    from playwright.async_api import async_playwright

    user = ROUTER_USER
    password = ROUTER_PASS

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(
        ignore_https_errors=True,
        http_credentials={"username": user, "password": password},
    )
    page = await ctx.new_page()

    result: dict[str, Any] = {}
    try:
        await page.goto("http://192.168.1.1", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        topframe = page.frame("topframe")
        if topframe:
            top_html = await topframe.content()
            result["topframe_html"] = top_html
            result["topframe_url"] = topframe.url

            basic_link = topframe.get_by_text("BASIC", exact=True)
            if await basic_link.count() > 0:
                await basic_link.first.click()
                await page.wait_for_timeout(3000)
                top_html_after = await topframe.content()
                result["topframe_html_after_basic_click"] = top_html_after
                result["topframe_url_after"] = topframe.url

        formframe = page.frame("formframe")
        if formframe:
            result["formframe_url"] = formframe.url

        result["frames"] = [{"name": f.name, "url": f.url} for f in page.frames]
    except Exception as e:
        result["error"] = str(e)
    finally:
        await ctx.close()
        await browser.close()
        await pw.stop()

    return result


@app.get("/debug/explore-basic-wireless")
async def debug_explore_basic_wireless():
    """Explore the BASIC > Wireless page to discover field names per band.

    Strategy:
      1. Login with HTTP Basic Auth
      2. Dump topframe HTML to understand sidebar navigation
      3. Dismiss any modal overlay, then use sidebar navigation
      4. If sidebar click fails, try direct URL probing from 22.100
      5. Dump all form fields from the resulting page
    """
    if SERVICE_MODE == "production":
        raise HTTPException(status_code=404, detail="Debug endpoints disabled in production mode")

    from playwright.async_api import async_playwright
    import base64

    user = ROUTER_USER
    password = ROUTER_PASS
    results: dict[str, Any] = {}

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(
        ignore_https_errors=True,
        http_credentials={"username": user, "password": password},
    )
    page = await ctx.new_page()

    async def _dump_frame_fields(frame) -> dict:
        """Extract all inputs, selects, buttons from a frame."""
        data: dict[str, Any] = {"url": frame.url}
        inputs = await frame.locator("input").all()
        input_list = []
        for inp in inputs:
            try:
                name = await inp.get_attribute("name") or ""
                typ = await inp.get_attribute("type") or ""
                id_attr = await inp.get_attribute("id") or ""
                val = await inp.get_attribute("value") or ""
                vis = await inp.is_visible()
                checked = ""
                if typ in ("checkbox", "radio"):
                    try:
                        checked = str(await inp.is_checked())
                    except Exception:
                        pass
                input_list.append({
                    "name": name, "type": typ, "id": id_attr,
                    "value": val, "visible": vis, "checked": checked,
                })
            except Exception:
                pass
        data["inputs"] = input_list

        selects = await frame.locator("select").all()
        select_list = []
        for sel in selects:
            try:
                name = await sel.get_attribute("name") or ""
                id_attr = await sel.get_attribute("id") or ""
                val = await sel.input_value()
                vis = await sel.is_visible()
                options_els = await sel.locator("option").all()
                opts = []
                for o in options_els[:30]:
                    try:
                        o_val = await o.get_attribute("value") or ""
                        o_text = (await o.inner_text()).strip()
                        opts.append({"value": o_val, "text": o_text})
                    except Exception:
                        pass
                select_list.append({
                    "name": name, "id": id_attr, "value": val,
                    "visible": vis, "options_sample": opts,
                })
            except Exception:
                pass
        data["selects"] = select_list

        buttons = await frame.locator(
            "input[type='button'], input[type='submit'], button"
        ).all()
        btn_list = []
        for btn in buttons:
            try:
                name = await btn.get_attribute("name") or ""
                id_attr = await btn.get_attribute("id") or ""
                val = await btn.get_attribute("value") or ""
                text = ""
                try:
                    text = (await btn.inner_text()).strip()
                except Exception:
                    pass
                vis = await btn.is_visible()
                btn_list.append({
                    "name": name, "id": id_attr, "value": val,
                    "text": text, "visible": vis,
                })
            except Exception:
                pass
        data["buttons"] = btn_list

        html = await frame.locator("body").inner_html()
        data["html_length"] = len(html)
        data["html_first_8000"] = html[:8000]
        return data

    try:
        await page.goto(
            "http://192.168.1.1", wait_until="domcontentloaded", timeout=30000
        )
        await page.wait_for_timeout(3000)
        results["login_url"] = page.url
        results["frames"] = [
            {"name": f.name, "url": f.url} for f in page.frames
        ]

        topframe = page.frame("topframe")
        formframe = page.frame("formframe")

        # --- Step 1: Dump topframe full HTML ---
        if topframe:
            top_html = await topframe.locator("body").inner_html()
            results["topframe_html_length"] = len(top_html)
            results["topframe_html"] = top_html[:15000]

        # --- Step 2: Try to dismiss any SSO modal in formframe ---
        if formframe:
            try:
                modal = formframe.locator("div#modalBox, div.modal, form[name='SSOAPI']")
                if await modal.count() > 0:
                    close_btn = formframe.locator(
                        "button.close, .modal-close, [data-dismiss='modal'], "
                        "button:has-text('Close'), button:has-text('No'), "
                        "button:has-text('Cancel'), a:has-text('Close')"
                    )
                    if await close_btn.count() > 0:
                        await close_btn.first.click(timeout=5000)
                        await page.wait_for_timeout(2000)
                        results["modal_dismissed"] = True
                    else:
                        await formframe.evaluate(
                            "document.querySelectorAll('.modal, #modalBox, form[name=SSOAPI]')"
                            ".forEach(el => el.style.display = 'none')"
                        )
                        results["modal_hidden_js"] = True
            except Exception as e:
                results["modal_error"] = str(e)

        # --- Step 3: Click BASIC tab in topframe, then look for Wireless link ---
        nav_worked = False
        if topframe:
            try:
                basic_link = topframe.get_by_text("BASIC", exact=True)
                if await basic_link.count() > 0:
                    await basic_link.first.click()
                    await page.wait_for_timeout(3000)
                    results["basic_tab_clicked"] = True

                    top_html_after = await topframe.locator("body").inner_html()
                    results["topframe_html_after_basic"] = top_html_after[:15000]

                    wireless = topframe.get_by_text("Wireless", exact=True)
                    if await wireless.count() > 0:
                        await wireless.first.click()
                        await page.wait_for_timeout(4000)
                        formframe = page.frame("formframe")
                        if formframe and "DashBoard" not in formframe.url:
                            nav_worked = True
                            results["nav_method"] = "basic_tab_then_wireless"
                    else:
                        wireless2 = topframe.locator("text=/[Ww]ireless/")
                        if await wireless2.count() > 0:
                            texts = []
                            for i in range(min(3, await wireless2.count())):
                                texts.append(await wireless2.nth(i).inner_text())
                            results["wireless_partial_matches"] = texts
            except Exception as e:
                results["basic_nav_error"] = str(e)

        # --- Step 4: Direct URL probing via Playwright page.request (from 22.100) ---
        candidate_urls = [
            "http://192.168.1.1/WLG_wireless_dual_498.htm",
            "http://192.168.1.1/WLG_wireless_tri.htm",
            "http://192.168.1.1/WLG_wireless_triband.htm",
            "http://192.168.1.1/bas_wireless.htm",
            "http://192.168.1.1/bas_wireLess.htm",
            "http://192.168.1.1/WLG_wireless.htm",
            "http://192.168.1.1/WLG_wireless_498.htm",
            "http://192.168.1.1/WLG_wireless_basic.htm",
            "http://192.168.1.1/WLG_wireless_dual.htm",
            "http://192.168.1.1/WLG_wireless5.htm",
            "http://192.168.1.1/WLG_wireless6.htm",
            "http://192.168.1.1/BAS_wireless.htm",
        ]
        url_probes = []
        if not nav_worked:
            for url in candidate_urls:
                try:
                    resp = await page.request.get(url, timeout=8000)
                    body = await resp.body()
                    has_5g = b"5g" in body.lower() or b"5ghz" in body.lower()
                    has_6g = b"6g" in body.lower() or b"6ghz" in body.lower()
                    url_probes.append({
                        "url": url, "status": resp.status, "size": len(body),
                        "has_5g": has_5g, "has_6g": has_6g,
                    })
                    if resp.ok and len(body) > 500 and (has_5g or has_6g):
                        formframe = page.frame("formframe")
                        if formframe:
                            await formframe.goto(
                                url, wait_until="domcontentloaded", timeout=15000
                            )
                            await page.wait_for_timeout(2000)
                            formframe = page.frame("formframe")
                            nav_worked = True
                            results["nav_method"] = f"direct_url:{url}"
                            break
                except Exception as e:
                    url_probes.append({"url": url, "error": str(e)[:100]})
            results["url_probes"] = url_probes

        # If no multi-band URL found, fall back to WLG_wireless.htm (2.4G only)
        if not nav_worked:
            try:
                formframe = page.frame("formframe")
                if formframe:
                    await formframe.goto(
                        "http://192.168.1.1/WLG_wireless.htm",
                        wait_until="domcontentloaded", timeout=15000,
                    )
                    await page.wait_for_timeout(2000)
                    formframe = page.frame("formframe")
                    nav_worked = True
                    results["nav_method"] = "fallback:WLG_wireless.htm"
            except Exception:
                pass

        # --- Step 5: Screenshot + dump fields ---
        formframe = page.frame("formframe")
        if formframe:
            results["formframe_fields"] = await _dump_frame_fields(formframe)
        else:
            results["formframe_fields"] = {"error": "formframe not found"}

        screenshot = await page.screenshot(full_page=True)
        results["screenshot_b64"] = base64.b64encode(screenshot).decode()[:200] + "..."
        ss_path = os.path.join(ARTIFACTS_DIR, "explore_basic_wireless.png")
        with open(ss_path, "wb") as f:
            f.write(screenshot)
        results["screenshot_saved"] = ss_path

    except Exception as exc:
        results["error"] = str(exc)
    finally:
        await ctx.close()
        await browser.close()
        await pw.stop()

    return results
