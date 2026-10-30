"""
Playbook PDF export.

Builds a print-styled HTML version of the playbook and prints it to PDF
with headless Chromium (Playwright).

Features:
- Markdown rendering for descriptions, notes and assignment instructions
  (uses the app's registered |markdown Jinja filter).
- Plays in their order within Offense/Defense sections.
- Table of contents with real page numbers (two-pass pagination: render,
  locate invisible per-item markers with pypdf, re-render with the TOC).
- Page footer with team name and page numbers.
- QR code next to each animation link so printed copies can be scanned.
- Optional filters: type ('offense'/'defense') and tag id.
- Disk cache keyed by content timestamps, so unchanged playbooks are
  served instantly.
"""
import base64
import glob
import hashlib
import io
import os
import re
from datetime import datetime

from flask import current_app, render_template, url_for

from app.utils.editor_diagrams import data_uri

PDF_MARGIN = {'top': '14mm', 'bottom': '18mm', 'left': '12mm', 'right': '12mm'}
MARKER_RE = re.compile(r'\[\[itm:([a-z0-9\-]+)\]\]')


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


def _qr_data_uri(url):
    """Small QR code PNG as a data URI (None if qrcode isn't installed)."""
    try:
        import qrcode
    except ImportError:
        return None
    try:
        img = qrcode.make(url, box_size=3, border=1)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception as e:
        current_app.logger.warning(f'Playbook export: QR generation failed: {e}')
        return None


def _image_src(url, team_id):
    """A photo uploaded here goes in inline (the PDF can't fetch from the site)."""
    m = re.match(r'^/(?:playbook|theory)/image/(\d+)$', url or '')
    if not m:
        return url or None
    from app import db
    from app.models.theory import TheoryImage
    image = db.session.get(TheoryImage, int(m.group(1)))
    if image is None or image.team_organization_id != team_id:
        return None
    return f'data:{image.mime_type};base64,{image.data}'


def play_url(play):
    """Where a play's QR code goes: its share link if it has one (opens
    without signing in), else its page (for the team, signed in)."""
    if play.share_token:
        return url_for('playbook.shared_play', token=play.share_token, _external=True)
    return url_for('playbook.view_play', play_id=play.id, _external=True)


def _item(kind, obj):
    """Dict the template consumes for one play."""
    # Drawn in the drill editor: every stage, inline
    stages = [{'label': d.step_label, 'caption': d.caption, 'src': data_uri(d)}
              for d in getattr(obj, 'editor_diagrams', [])]
    stages = [st for st in stages if st['src']]
    # The QR code goes to the play on this site; an old Ultiplays link only
    # while the play isn't drawn
    animation_url = extract_embed_url(obj.ultiplay_embed) if not stages else None
    animation_url = animation_url or play_url(obj)
    return {
        'kind': kind,
        'key': f'{kind}-{obj.id}',
        'obj': obj,
        'stages': stages,
        'image': _image_src(obj.image_url, obj.team_organization_id),
        'animation_url': animation_url,
        'qr': _qr_data_uri(animation_url) if animation_url else None,
    }


def build_sections(plays, type_filter=None, tag_id=None):
    """[(section name, items)]: Offense then Defense, each the plays in
    their order."""
    if tag_id:
        plays = [p for p in plays if any(t.id == tag_id for t in p.tags)]
    sections = []
    for section_name, stype in (('Offense', 'offense'), ('Defense', 'defense')):
        if type_filter and type_filter != stype:
            continue
        items = [_item('play', p) for p in plays if p.type == stype]
        if items:
            sections.append((section_name, items))
    return sections


def _toc_entries(sections):
    """Flatten sections into ordered TOC entries (label, level, key)."""
    entries = []
    for section_name, items in sections:
        entries.append({'label': section_name, 'level': 0, 'key': f'section-{section_name.lower()}'})
        for it in items:
            entries.append({'label': it['obj'].name,
                            'level': 1,
                            'key': it['key']})
    return entries


def _marker_pages(pdf_bytes):
    """Map item key -> 1-based page number by reading invisible markers."""
    from pypdf import PdfReader
    pages = {}
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ''
        except Exception:
            text = ''
        for key in MARKER_RE.findall(text):
            pages.setdefault(key, i)
    return pages, len(reader.pages)


def _footer_template(team_name):
    return (
        '<div style="width:100%;font-size:8px;color:#9ca3af;'
        'padding:0 12mm;display:flex;justify-content:space-between;'
        'font-family:Arial,sans-serif;">'
        f'<span>{team_name} — Playbook</span>'
        '<span>Page <span class="pageNumber"></span> of '
        '<span class="totalPages"></span></span></div>'
    )


def generate_playbook_pdf(plays, team_name, type_filter=None,
                          tag_id=None, progress=None):
    """Return the playbook as PDF bytes.

    `progress` is an optional callback (percent:int, label:str) used to
    report generation stages to the UI.
    """
    from playwright.sync_api import sync_playwright  # lazy: optional dependency
    from app.utils.pdf import block_private_requests

    def report(pct, label):
        if progress:
            try:
                progress(pct, label)
            except Exception:
                pass

    report(5, 'Collecting plays…')
    sections = build_sections(plays, type_filter, tag_id)
    generated = datetime.now().strftime('%d %B %Y')
    footer = _footer_template(team_name)

    def render(toc):
        return render_template('playbook/export_pdf.html',
                               team_name=team_name, generated=generated,
                               sections=sections, toc=toc,
                               type_filter=type_filter)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()  # shared context = shared image cache
            block_private_requests(context)

            def to_pdf(html):
                page = context.new_page()
                page.set_content(html, wait_until='networkidle')
                pdf = page.pdf(format='A4', print_background=True,
                               margin=PDF_MARGIN, display_header_footer=True,
                               header_template='<span></span>',
                               footer_template=footer)
                page.close()
                return pdf

            # Pass 1: no TOC -> find which page each item lands on
            report(15, 'Rendering play pages…')
            pdf1 = to_pdf(render(toc=None))
            try:
                pages, base_count = _marker_pages(pdf1)
            except Exception as e:
                current_app.logger.warning(
                    f'Playbook export: TOC pagination unavailable ({e}); exporting without TOC')
                return pdf1

            entries = _toc_entries(sections)

            # Pass 2: include the TOC with dummy numbers to measure its length
            report(50, 'Building table of contents…')
            for e in entries:
                e['page'] = 0
            pdf2 = to_pdf(render(toc=entries))
            _, with_toc_count = _marker_pages(pdf2)
            toc_page_count = with_toc_count - base_count

            # Every section/item starts on a fresh page, so inserting the TOC
            # shifts all content pages by exactly toc_page_count.
            for e in entries:
                e['page'] = pages.get(e['key'], 0) + toc_page_count

            # Final render with real page numbers
            report(75, 'Finalising PDF…')
            result = to_pdf(render(toc=entries))
            report(95, 'Saving…')
            return result
        finally:
            browser.close()


# ── Disk cache ───────────────────────────────────────────────────

def _cache_dir():
    path = os.path.join(current_app.instance_path, 'pdf_cache')
    os.makedirs(path, exist_ok=True)
    return path


def cache_key(team_id, plays, type_filter, tag_id):
    """Digest of everything that affects the PDF's content."""
    parts = [f'team={team_id}', f'type={type_filter}', f'tag={tag_id}']
    for obj in plays:
        stamp = obj.updated_at.isoformat() if obj.updated_at else '0'
        # The share link is in the QR code
        parts.append(f'{obj.__class__.__name__}:{obj.id}:{stamp}:{obj.share_token or ""}')
    return hashlib.sha1('|'.join(parts).encode()).hexdigest()[:16]


def cached_pdf(team_id, key):
    path = os.path.join(_cache_dir(), f'playbook_{team_id}_{key}.pdf')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    return None


def store_cached_pdf(team_id, key, pdf_bytes):
    # Drop older cached versions for this team first
    for old in glob.glob(os.path.join(_cache_dir(), f'playbook_{team_id}_*.pdf')):
        try:
            os.remove(old)
        except OSError:
            pass
    path = os.path.join(_cache_dir(), f'playbook_{team_id}_{key}.pdf')
    try:
        with open(path, 'wb') as f:
            f.write(pdf_bytes)
    except OSError as e:
        current_app.logger.warning(f'Playbook export: could not write cache: {e}')
