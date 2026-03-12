"""Debug: fetch router login page HTML via router_service debug endpoint."""
import base64
import os
import re
import httpx

ROUTER_CONTROL_URL = "http://192.168.22.100:8081"
os.makedirs("artifacts", exist_ok=True)

print("Fetching router login page via debug endpoint...")
resp = httpx.get(f"{ROUTER_CONTROL_URL}/router/debug-login", timeout=60)
data = resp.json()

url = data.get("url", "")
html = data.get("html", "")
print(f"Final URL: {url}")

if "username" in html.lower() and "password" in html.lower():
    print("STATUS: Normal login page detected!")
elif "Recovery" in html or "serialNumber" in html:
    print("STATUS: Password recovery page (router may be locked)")
elif "Unauthorized" in html:
    print("STATUS: 401 Unauthorized")
else:
    print("STATUS: Unknown page type")

inputs = re.findall(r'<input[^>]*>', html)
print(f"\nFound {len(inputs)} <input> elements:")
for inp in inputs:
    print(f"  {inp}")

buttons = re.findall(r'<button[^>]*>.*?</button>', html, re.DOTALL)
print(f"\nFound {len(buttons)} <button> elements:")
for btn in buttons:
    print(f"  {btn[:120]}")

forms = re.findall(r'<form[^>]*>', html)
print(f"\nFound {len(forms)} <form> elements:")
for form in forms:
    print(f"  {form}")

print(f"\n{'='*60}")
print("FULL HTML:")
print("="*60)
print(html)

b64 = data.get("screenshot_b64", "")
if b64:
    with open("artifacts/debug_login_screenshot.png", "wb") as f:
        f.write(base64.b64decode(b64))
    print("\nScreenshot saved to artifacts/debug_login_screenshot.png")
