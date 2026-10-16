"""HTML to PDF with headless Chromium (Playwright), as the playbook export
does. nixpacks.toml installs Chromium at build time."""

PAGE_MARGIN = {'top': '14mm', 'bottom': '14mm', 'left': '12mm', 'right': '12mm'}


def html_to_pdf(html):
    """Return PDF bytes for a self-contained HTML page (images inline as data
    URIs). Raises ImportError when Playwright isn't installed."""
    from playwright.sync_api import sync_playwright  # lazy: optional dependency

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until='networkidle')
            return page.pdf(format='A4', print_background=True, margin=PAGE_MARGIN)
        finally:
            browser.close()
