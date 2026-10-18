"""HTML to PDF with headless Chromium (Playwright), as the playbook export
does. nixpacks.toml installs Chromium at build time."""
import ipaddress
import socket
from urllib.parse import urlparse

PAGE_MARGIN = {'top': '14mm', 'bottom': '14mm', 'left': '12mm', 'right': '12mm'}


def is_public_url(url):
    """True for http(s) links whose host resolves only to public addresses.
    The pages rendered here hold text people typed, so without this a link
    could make the server fetch internal addresses (cloud metadata etc.)."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    return bool(infos) and all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def block_private_requests(target):
    """Let a Playwright page or context load public http(s) URLs only."""
    def handle(route):
        if is_public_url(route.request.url):
            route.continue_()
        else:
            route.abort()
    target.route('**/*', handle)


def html_to_pdf(html):
    """Return PDF bytes for a self-contained HTML page (images inline as data
    URIs). Raises ImportError when Playwright isn't installed."""
    from playwright.sync_api import sync_playwright  # lazy: optional dependency

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            block_private_requests(page)
            page.set_content(html, wait_until='networkidle')
            return page.pdf(format='A4', print_background=True, margin=PAGE_MARGIN)
        finally:
            browser.close()
