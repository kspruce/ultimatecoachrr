"""
Playbook PDF export.

Uses headless Chromium (Playwright) to:
  1. Snapshot each UltiPlays embed as a PNG (cached against the row's
     updated_at, so unchanged plays are never re-rendered).
  2. Render a print-styled HTML template of the whole playbook and
     print it to PDF.

Sections: Offensive Concepts, Defensive Concepts, Offensive Plays,
Defensive Plays.
"""
import base64
import os
import re
import glob
from datetime import datetime

from flask import current_app, render_template

SNAPSHOT_SUBDIR = 'playbook_snapshots'
EMBED_VIEWPORT = {'width': 1000, 'height': 562}  # 16:9-ish play diagram
EMBED_SETTLE_MS = 2000  # let the animation player draw its first frame


# ── Embed helpers ────────────────────────────────────────────────

def extract_embed_url(embed_html):
    """Pull the iframe src out of stored embed code (or accept a bare URL)."""
    if not embed_html:
        return None
    embed_html = embed_html.strip()
    m = re.search(r'src=["\']([^"\']+)["\']', embed_html)
    if m:
        return m.group(1)
    if embed_html.startswith('http'):
        return embed_html
    return None


def _snapshot_dir():
    path = os.path.join(current_app.instance_path, SNAPSHOT_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def _snapshot_path(kind, item_id, updated_at):
    stamp = int(updated_at.timestamp()) if updated_at else 0
    return os.path.join(_snapshot_dir(), f'{kind}_{item_id}_{stamp}.png')


def _capture_snapshot(page, url, dest_path):
    """Screenshot one embed URL to dest_path. Returns True on success."""
    try:
        try:
            page.goto(url, wait_until='networkidle', timeout=20000)
        except Exception:
            # networkidle can hang on pages that poll; settle for 'load'
            page.goto(url, wait_until='load', timeout=20000)
        page.wait_for_timeout(EMBED_SETTLE_MS)
        page.screenshot(path=dest_path)
        return True
    except Exception as e:
        current_app.logger.warning(f'Playbook export: snapshot failed for {url}: {e}')
        return False


def _get_or_create_snapshot(page, kind, item):
    """Return a snapshot file path for a Play/Formation, or None."""
    url = extract_embed_url(item.ultiplay_embed)
    if not url:
        return None

    dest = _snapshot_path(kind, item.id, item.updated_at)
    if os.path.exists(dest):
        return dest

    # Drop stale snapshots for this item (older updated_at stamps)
    for old in glob.glob(os.path.join(_snapshot_dir(), f'{kind}_{item.id}_*.png')):
        try:
            os.remove(old)
        except OSError:
            pass

    return dest if _capture_snapshot(page, url, dest) else None


def _img_data_uri(path):
    with open(path, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode('ascii')


# ── PDF generation ───────────────────────────────────────────────

def _prepare_item(page, kind, item):
    """Build the dict the template consumes for one play/formation."""
    snapshot = _get_or_create_snapshot(page, kind, item)
    return {
        'obj': item,
        'image': _img_data_uri(snapshot) if snapshot else None,
        'imgur_url': getattr(item, 'imgur_url', None),
        'animation_url': extract_embed_url(item.ultiplay_embed),
    }


def generate_playbook_pdf(formations, offensive_plays, defensive_plays, team_name):
    """Return the playbook as PDF bytes."""
    from playwright.sync_api import sync_playwright  # lazy: optional dependency

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport=EMBED_VIEWPORT)

            sections = [
                ('Offensive Concepts',
                 [_prepare_item(page, 'formation', f) for f in formations if f.type == 'offense']),
                ('Defensive Concepts',
                 [_prepare_item(page, 'formation', f) for f in formations if f.type != 'offense']),
                ('Offensive Plays',
                 [_prepare_item(page, 'play', pl) for pl in offensive_plays]),
                ('Defensive Plays',
                 [_prepare_item(page, 'play', pl) for pl in defensive_plays]),
            ]

            html = render_template(
                'playbook/export_pdf.html',
                team_name=team_name,
                generated=datetime.now().strftime('%d %B %Y'),
                sections=sections,
            )

            pdf_page = browser.new_page()
            pdf_page.set_content(html, wait_until='networkidle')
            return pdf_page.pdf(
                format='A4',
                print_background=True,
                margin={'top': '14mm', 'bottom': '14mm', 'left': '12mm', 'right': '12mm'},
            )
        finally:
            browser.close()
