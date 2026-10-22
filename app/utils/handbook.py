"""Leadership handbook: its sections, the importer for the handbook source
file, and the HTML clean-up used on everything that is stored.

The source (imports/leadership-handbook/handbook.html) is one
<article class="page" id=... data-section=... data-title=...> per page: a
<header> holding the lead, then the body. Links between pages are written
href="#page-id" and turned into page URLs when shown.
"""
import re
from dataclasses import dataclass, field
from html import unescape

import nh3

from app import db
from app.models.handbook import HandbookPage

SECTIONS = [
    ('start', 'Start here', 'What Herd is about, and what we ask of every leader.'),
    ('captaining', 'Captaining', "What the job really is, and it isn't being the best player."),
    ('fun', 'Building a fun team', 'Belonging, identity, Spirit and the freedom to fail.'),
    ('sessions', 'Sessions that make everyone better', 'How we coach, plan sessions, run drills and teach throws.'),
    ('mental', 'The mental game', 'Confidence, focus, nerves and preparing for pressure.'),
    ('season', 'Running a season', 'Planning, squad size, trials, tactics, stats, timeouts and safety.'),
    ('cases', 'Lessons from great teams', 'What champion teams did, condensed into lessons for Herd.'),
    ('ams', 'Amsterdam talks', 'Notes from twelve talks at the Amsterdam coaching conference.'),
]
SECTION_KEYS = [key for key, _, _ in SECTIONS]
SECTION_TITLES = {key: title for key, title, _ in SECTIONS}


# --------------------------------------------------------------------------
# Cleaning HTML
# --------------------------------------------------------------------------

ALLOWED_TAGS = {
    'p', 'br', 'h4', 'ul', 'ol', 'li', 'b', 'strong', 'i', 'em', 'small', 'a', 'div', 'span',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote',
}
ALLOWED_ATTRIBUTES = {'*': {'class'}, 'a': {'href'}}


def clean_html(html):
    """Keep only simple formatting: the tags in ALLOWED_TAGS, class names,
    and links. No scripts, styles, event handlers or embeds."""
    return nh3.clean(html or '', tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
                     url_schemes={'http', 'https', 'mailto'}, link_rel='noopener noreferrer').strip()


def text_of(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()


def link_pages(html, url_for_slug):
    """Turn href="#page-id" into that page's URL."""
    return re.sub(r'href="#([A-Za-z0-9_-]+)"', lambda m: f'href="{url_for_slug(m.group(1))}"', html or '')


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

class HandbookImportError(Exception):
    def __init__(self, errors):
        super().__init__('; '.join(errors))
        self.errors = errors


ARTICLE_RE = re.compile(r'<article\b([^>]*)>(.*?)</article>', re.S)
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
HEADER_RE = re.compile(r'^\s*<header>(.*?)</header>', re.S)
LEAD_RE = re.compile(r'<p class="lead">(.*?)</p>', re.S)
META_RE = re.compile(r'<p class="case-meta">.*?</p>', re.S)


def parse_handbook(text):
    """Pages from the source file, in order: dicts with slug, section,
    title, lead and body_html. Raises HandbookImportError on problems."""
    pages, errors, seen = [], [], set()
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    for attr_text, inner in ARTICLE_RE.findall(text):
        attrs = dict(ATTR_RE.findall(attr_text))
        slug, section, title = attrs.get('id', ''), attrs.get('data-section', ''), attrs.get('data-title', '')
        if not re.fullmatch(r'[a-z0-9-]{1,80}', slug):
            errors.append(f'page {title or "?"!r}: bad or missing id {slug!r}')
            continue
        if slug in seen:
            errors.append(f'{slug}: id used twice')
        seen.add(slug)
        if section not in SECTION_TITLES:
            errors.append(f'{slug}: unknown section {section!r}')
        if not title:
            errors.append(f'{slug}: no data-title')
        header = HEADER_RE.search(inner)
        lead, body = '', inner
        if header:
            body = inner[header.end():]
            m = LEAD_RE.search(header.group(1))
            lead = text_of(m.group(1)) if m else ''
            meta = META_RE.search(header.group(1))
            if meta:  # a case study's team/year chip sits at the top of the body
                body = meta.group(0) + body
        pages.append({'slug': slug, 'section': section, 'title': unescape(title),
                      'lead': unescape(lead), 'body_html': clean_html(body)})
    if not pages and not errors:
        errors.append('no <article class="page"> elements found')
    if errors:
        raise HandbookImportError(errors)
    order = {key: i for i, key in enumerate(SECTION_KEYS)}
    pages.sort(key=lambda p: order[p['section']])  # stable: keeps file order within a section
    return pages


@dataclass
class ImportReport:
    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    dry_run: bool = False

    def text(self):
        lines = ['DRY RUN: nothing was written'] if self.dry_run else []
        lines.append(f'new pages: {len(self.created)}')
        lines.append(f'pages overwritten from the file: {len(self.updated)}')
        if self.kept:
            lines.append(f'pages already on the site, left as edited: {len(self.kept)} (use --replace to overwrite)')
        return '\n'.join(lines)


def import_handbook(path, team, dry_run=False, replace=False):
    """Add the file's pages to the team's handbook. Pages already on the site
    keep their wording (leaders may have edited them) unless replace is set;
    every page's section and order always follow the file."""
    with open(path, encoding='utf-8') as f:
        pages = parse_handbook(f.read())
    existing = {p.slug: p for p in HandbookPage.query.filter_by(team_organization_id=team.id)}
    report = ImportReport(dry_run=dry_run)
    for position, data in enumerate(pages):
        page = existing.get(data['slug'])
        if page is None:
            report.created.append(data['slug'])
            page = HandbookPage(team_organization_id=team.id, slug=data['slug'])
            db.session.add(page)
            fill = True
        else:
            fill = replace
            (report.updated if replace else report.kept).append(data['slug'])
        page.section, page.position = data['section'], position
        if fill:
            page.title, page.lead, page.body_html = data['title'], data['lead'], data['body_html']
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return report
