"""
Playbook PDF export.

Renders a print-styled HTML template of the whole playbook (concepts +
plays) and prints it to PDF with headless Chromium (Playwright).

Diagrams come from the stored image links (Play.image_url /
Formation.imgur_url - e.g. ImgBB or Imgur direct links); Chromium fetches
them while rendering, so no screenshotting of UltiPlays embeds is needed.
Each item also gets a link to its live animation.

Sections: Offensive Concepts, Defensive Concepts, Offensive Plays,
Defensive Plays.
"""
import re
from datetime import datetime

from flask import render_template


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


def _prepare_item(item):
    """Build the dict the template consumes for one play/formation."""
    image = getattr(item, 'image_url', None) or getattr(item, 'imgur_url', None)
    return {
        'obj': item,
        'image': image or None,
        'animation_url': extract_embed_url(item.ultiplay_embed),
    }


def generate_playbook_pdf(formations, offensive_plays, defensive_plays, team_name):
    """Return the playbook as PDF bytes."""
    from playwright.sync_api import sync_playwright  # lazy: optional dependency

    sections = [
        ('Offensive Concepts',
         [_prepare_item(f) for f in formations if f.type == 'offense']),
        ('Defensive Concepts',
         [_prepare_item(f) for f in formations if f.type != 'offense']),
        ('Offensive Plays',
         [_prepare_item(pl) for pl in offensive_plays]),
        ('Defensive Plays',
         [_prepare_item(pl) for pl in defensive_plays]),
    ]

    html = render_template(
        'playbook/export_pdf.html',
        team_name=team_name,
        generated=datetime.now().strftime('%d %B %Y'),
        sections=sections,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            # networkidle so remote diagram images finish loading before print
            page.set_content(html, wait_until='networkidle')
            return page.pdf(
                format='A4',
                print_background=True,
                margin={'top': '14mm', 'bottom': '14mm', 'left': '12mm', 'right': '12mm'},
            )
        finally:
            browser.close()
