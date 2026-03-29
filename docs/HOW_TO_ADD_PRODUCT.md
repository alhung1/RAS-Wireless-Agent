# How to add a new product (adapter + profiles)

This flow matches the **implemented** registration and loader behavior in `orchestrator/local_automation/profiles/loader.py` and `products/`.

## 1. Subclass `ProductBase`

Create **`orchestrator/local_automation/products/<your_product>.py`**:

- Implement **`name`** (machine id, e.g. `INTEL_AX210`), **`display_name`**, **`supported_bands`**, **`valid_channels`**, **`valid_modes`**, **`default_config(band)`**.
- Override **`ap_folder`** / **`client_folder`** if paths differ from defaults (`E:\AP`, `E:\Client`).
- Implement **`verify_*`** methods that return **`VerificationSpec`** (or use shared helpers) for each native step that will run on this product — mirror the pattern in **`products/be200.py`** (regions are **calibrated per product + LabVIEW skin**).

Optional: override **`ui_labels()`** for OCR text expectations.

## 2. Register the adapter

In **`profiles/loader.py`**, extend **`_register_builtin_products()`**:

```python
from orchestrator.local_automation.products.your_product import YourAdapter
register_product("YOUR_PRODUCT_ID", YourAdapter)
```

The id is matched **case-insensitively** (`product_id.upper()`).

## 3. Product profile YAML

Add **`profiles/products/<lowercase_hint>.yaml`** matching **`ProductProfileData`** (`profiles/schema.py`):

- **`product`**: same id as `register_product`
- **`client_name`**, **`ap_name`**, optional **`ap_folder`**, **`client_folder`**, **`exe_path`**, **`firmware_rev`**, etc.

**Loader helper:** `find_product_profile_path(product_id, profiles_root)` discovers the file; `load_product_profile` parses it.

## 4. Test profile YAML

Add **`profiles/test_matrix/<name>.yaml`** as a **`TestProfile`**:

- **`name`**, **`product`** (must resolve adapter + optional product YAML), **`band`**, **`mode`**, channels, **`attenuation`**, **`finish_detection`**, credentials fields, etc.

Reference: **`profiles/test_matrix/be200_2g.yaml`**.

## 5. Verification spec design

- **Prefer OCR** with **`VerificationSpec`**: `ocr_region`, `expected_text`, `ocr_threshold`, `ocr_scale_factor`, `ocr_invert`, `ocr_char_whitelist`, `ocr_psm`, **`ocr_normalize_digits`** for numeric fields.
- **Pixel diff** when controls are too small or OCR is unstable; document tradeoffs (see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).
- Execution pipeline: **`ui/verification.py`** (`execute_verification`, `_run_ocr_with_spec`).

Native steps call **`ctx.product.verify_…(ctx, …)`** — keep product-specific numbers and rectangles in the adapter, not scattered in generic engine code.

## 6. Calibration notes

1. Run **`scripts/run_single_step.py`** or **`run_profile.py --step N`** to isolate a screen (note: `run_single_step` uses **direct `STEP_SEQUENCE`** calls, not `StepEngine` — see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).
2. Capture screenshots under **`artifacts/`**; tune regions in the adapter until OCR or pixel_diff evidence is stable.
3. Re-run **live validation** on the target machine; dry-run alone does not prove UI correctness.
4. Add **`scripts/validate_profiles.py`** to CI for schema + capability checks.

## 7. Legacy `run_labview_flow`

Set **`LV_PRODUCT`** to your new registered id so the thin facade resolves the correct adapter during preflight.
