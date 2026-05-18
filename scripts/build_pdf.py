"""
Render case_study.html to a PDF using headless Chromium (already installed
via Playwright for the screenshot capture script). No pandoc / wkhtmltopdf /
weasyprint required.

Usage:
    python scripts/build_case_study.py        # regenerates case_study.html
    python scripts/build_pdf.py               # writes case_study.pdf
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).parent.parent
HTML = REPO / "case_study.html"
PDF = REPO / "case_study.pdf"


def main() -> None:
    if not HTML.exists():
        raise SystemExit(
            f"{HTML.name} not found. Run `python scripts/build_case_study.py` first."
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # file:// so relative image paths (docs/images/*.png) resolve.
        page.goto(HTML.absolute().as_uri(), wait_until="networkidle")
        # Wait until our HTML scaffolding signals Mermaid has finished
        # running. Falls back to a fixed timeout if the marker never appears
        # (e.g. the artifact has no Mermaid blocks).
        try:
            page.wait_for_function(
                "document.body.dataset.mermaidReady === 'true'",
                timeout=15000,
            )
        except Exception:
            pass
        page.wait_for_timeout(800)
        page.pdf(
            path=str(PDF),
            format="Letter",
            print_background=True,
            margin={"top": "0.6in", "bottom": "0.6in",
                    "left": "0.6in", "right": "0.6in"},
            prefer_css_page_size=False,
        )
        browser.close()

    size_kb = PDF.stat().st_size // 1024
    print(f"wrote {PDF.relative_to(REPO)} ({size_kb} KB)")


if __name__ == "__main__":
    main()
