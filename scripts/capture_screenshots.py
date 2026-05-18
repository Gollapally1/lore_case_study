"""
Capture dashboard screenshots for the case-study artifact.

Headlessly drives a Chromium browser against the Streamlit dashboard at
http://localhost:8501 and saves PNGs into docs/images/. Run after
`streamlit run src/dashboard.py` is up.

Usage:
    python scripts/capture_screenshots.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent.parent / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)

URL = "http://localhost:8501"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Tall viewport so the full Streamlit page fits in one frame —
        # Streamlit's internal scroll container confuses `full_page=True`.
        ctx = browser.new_context(viewport={"width": 1600, "height": 2800},
                                  device_scale_factor=2)
        page = ctx.new_page()

        # --- 1. Overview: full page, all partners ---
        page.goto(URL, wait_until="networkidle")
        # Streamlit charts hydrate after networkidle; give them a beat.
        page.wait_for_timeout(3000)
        page.screenshot(path=OUT / "dashboard_overview.png", full_page=True)
        print("wrote dashboard_overview.png")

        # --- 2. Rollup table: locate the dataframe and screenshot just it ---
        try:
            table = page.locator("[data-testid='stDataFrame']").first
            table.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            table.screenshot(path=OUT / "rollup_table.png")
            print("wrote rollup_table.png")
        except Exception as e:
            print(f"rollup table capture skipped: {e}")

        # --- 3. Filtered view: pick a single partner ---
        # Streamlit renders the multiselect in the sidebar; click it,
        # clear the existing chips, type a single partner.
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(400)

        # Click each "remove tag" (x) button until only one chip remains.
        # The multiselect's chips are <span> with an aria-label of the value.
        # Easiest: open the multiselect and use the "Clear all" if Streamlit
        # exposes it; otherwise, just navigate via the date filter which is
        # less fragile.
        try:
            # Remove every partner chip except acme-corp by clicking each
            # chip's individual "X" button. Backspace-based clearing was
            # flaky because Streamlit re-renders between key events.
            chips = page.get_by_role("button").filter(
                has_text=""  # all buttons
            )
            # The chip-removal buttons have aria-label ending in
            # "close by backspace". Iterate by text.
            for partner in ("ghost-partner-do-not-exist", "globex", "initech",
                            "stark-industries", "umbrella"):
                btn = page.get_by_role("button",
                                       name=f"{partner}, close by backspace")
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(200)

            page.get_by_role("heading", level=1).click()
            page.wait_for_timeout(3000)
            page.screenshot(path=OUT / "dashboard_filtered.png", full_page=True)
            print("wrote dashboard_filtered.png")
        except Exception as e:
            print(f"filtered view skipped: {e}")

        browser.close()


if __name__ == "__main__":
    main()
