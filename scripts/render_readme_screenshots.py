#!/usr/bin/env python3
"""Render README screenshots.

- deviation-table.png: real Playwright capture of the standalone /review page
  (uses SAMPLE_DEVIATION_REVIEW_DATA — the Phase 2 demo data).
- redline-output.png: real Playwright capture of demo/expected-redline.docx
  rendered as HTML (the demo's reference redline for the 5 hand-crafted
  deviations in known-bad-nda.pdf).
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
DEMO_HTML = OUT / "sample-redline.html"

# 1. Render the deviation-table from the live stack.
DEVIATION_URL = "http://localhost:15173/#/review"
# 2. Render the redline from the demo's HTML.
REDLINE_HTML_FILE = (OUT / "sample-redline.html").as_uri()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    # --- deviation-table.png ---
    ctx = browser.new_context(viewport={"width": 1400, "height": 1800}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(DEVIATION_URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)
    out_path = OUT / "deviation-table.png"
    page.screenshot(path=str(out_path), full_page=True)
    print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
    ctx.close()
    # --- redline-output.png (rendered from demo's expected redline HTML) ---
    ctx = browser.new_context(viewport={"width": 1200, "height": 1600}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(REDLINE_HTML_FILE, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1500)
    out_path = OUT / "redline-output.png"
    page.screenshot(path=str(out_path), full_page=True)
    print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
    ctx.close()
    browser.close()
print("DONE")
