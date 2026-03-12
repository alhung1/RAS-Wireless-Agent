"""Debug: explore the RS700 login flow by clicking Cancel on recovery page,
and also try different URLs to find the real login page."""
import asyncio
import base64
import os
from playwright.async_api import async_playwright

ROUTER_URL = "http://192.168.1.1"
os.makedirs("artifacts", exist_ok=True)


async def explore():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(ignore_https_errors=True)
    page = await ctx.new_page()

    # Step 1: Load main page
    print("=" * 60)
    print("Step 1: Load http://192.168.1.1")
    print("=" * 60)
    await page.goto(ROUTER_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    print(f"  URL: {page.url}")
    print(f"  Title: {await page.title()}")
    ss = await page.screenshot()
    with open("artifacts/step1_initial.png", "wb") as f:
        f.write(ss)

    # Step 2: If recovery page, click Cancel
    cancel_btn = page.locator("button#cancel")
    if await cancel_btn.count() > 0:
        print("\n" + "=" * 60)
        print("Step 2: Recovery page detected, clicking Cancel...")
        print("=" * 60)
        await cancel_btn.click()
        await page.wait_for_timeout(3000)
        print(f"  URL after Cancel: {page.url}")
        print(f"  Title: {await page.title()}")
        html2 = await page.content()
        ss2 = await page.screenshot()
        with open("artifacts/step2_after_cancel.png", "wb") as f:
            f.write(ss2)

        inputs = []
        for inp in await page.locator("input").all():
            name = await inp.get_attribute("name") or ""
            typ = await inp.get_attribute("type") or ""
            iid = await inp.get_attribute("id") or ""
            inputs.append(f"name={name} type={typ} id={iid}")
        print(f"  Input fields: {inputs}")

        print(f"\n  HTML (first 3000 chars):")
        print(html2[:3000])
    else:
        print("  No Cancel button found")

    # Step 3: Try known Netgear login URLs
    test_urls = [
        "/MNU_access_Login2.htm",
        "/currentsetting.htm",
        "/login.htm",
        "/index.htm",
    ]
    for i, path in enumerate(test_urls):
        print(f"\n{'='*60}")
        print(f"Step 3.{i}: Try {ROUTER_URL}{path}")
        print("=" * 60)
        try:
            await page.goto(f"{ROUTER_URL}{path}", wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(2000)
            print(f"  URL: {page.url}")
            print(f"  Title: {await page.title()}")
            inputs = []
            for inp in await page.locator("input").all():
                name = await inp.get_attribute("name") or ""
                typ = await inp.get_attribute("type") or ""
                inputs.append(f"name={name} type={typ}")
            print(f"  Inputs: {inputs}")
        except Exception as e:
            print(f"  Failed: {e}")

    await ctx.close()
    await browser.close()
    await pw.stop()
    print("\nDone. Check artifacts/ for screenshots.")


asyncio.run(explore())
