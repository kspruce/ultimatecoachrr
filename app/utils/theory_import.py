"""Load a markdown file of theory cards into a team's Theory hub, from
Theory > New > Import cards or `flask import-theory`.

Each `# Heading` names a section (made if the team hasn't got one by that
name). Each `## Card 12 · Getting open` heading under it starts a topic in
that section: the text after the number is its title and everything up to
the next heading is its content. Any other `##` heading before a section's
first card (e.g. "How to use these cards") becomes a note for coaches.
Cards arrive as drafts, so coaches can publish each one in the week it is
taught.

Re-importing adds new cards and moves cards already on the site (matched
on title, anywhere in the hub) into the section the file puts them in. Their
wording is left as coaches edited it unless replace is set. A section left
empty by those moves is removed.
"""
import re
from dataclasses import dataclass, field

from app import db
from app.models.theory import TheorySection, TheoryTopic, unique_slug

MAX_FILE_BYTES = 1024 * 1024
MAX_CARDS = 200
NAME_MAX = 100

TITLE_RE = re.compile(r'^#\s+(.+?)\s*#*\s*$')
HEADING_RE = re.compile(r'^##\s+(.+?)\s*#*\s*$')
CARD_RE = re.compile(r'^Card\s+(\d+)\s*[·:.\-–—|]\s*(.+)$', re.I)
FENCE_RE = re.compile(r'^\s*(```|~~~)')
BYLINE_RE = re.compile(r'·\s*@\S+\s*$')  # "Oct 29, 2026 · @Kieran"


class TheoryImportError(Exception):
    def __init__(self, errors):
        super().__init__('; '.join(errors))
        self.errors = errors


def parse_cards(text):
    """{'sections': [{'name', 'description', 'topics': [{'name', 'content',
    'number'}]}]} from the markdown, or TheoryImportError listing what's
    wrong."""
    sections, current, stray = [], None, False
    in_fence = False
    for line in text.replace('\r\n', '\n').split('\n'):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else HEADING_RE.match(line)
        title = None if in_fence else TITLE_RE.match(line)
        if title:
            sections.append({'name': title.group(1).strip(), 'intro': [], 'blocks': []})
            current = None
        elif heading:
            current = {'heading': heading.group(1).strip(), 'lines': []}
            if sections:
                sections[-1]['blocks'].append(current)
            else:
                stray = True
        elif current is not None:
            current['lines'].append(line)
        elif sections:
            sections[-1]['intro'].append(line)

    errors, names, numbers = [], set(), []
    if stray:
        errors.append('Start the file with a "# Section name" line: every card needs a section above it.')
    for section in sections:
        if len(section['name']) > NAME_MAX:
            errors.append(f'The section "# {section["name"][:60]}…" is {len(section["name"])} characters; '
                          f'the most is {NAME_MAX}.')
        topics = section['topics'] = []
        for block in section.pop('blocks'):
            card = CARD_RE.match(block['heading'])
            if card:
                number, name = int(card.group(1)), card.group(2).strip()
                numbers.append(number)
            elif not any(t['number'] is not None for t in topics):
                number, name = None, block['heading']  # a note before the section's cards
            else:
                errors.append(f'"{block["heading"][:60]}" comes after cards in {section["name"]} '
                              'but isn\'t a "Card N · Title" heading.')
                continue
            content = '\n'.join(block['lines']).strip('\n')
            label = f'Card {number}' if number is not None else f'"{name[:60]}"'
            if len(name) > NAME_MAX:
                errors.append(f'{label}: the title is {len(name)} characters; the most is {NAME_MAX}.')
            if not content.strip():
                errors.append(f'{label} has nothing under its heading.')
            if name.lower() in names:
                errors.append(f'Two cards are called "{name[:60]}". Titles must differ.')
            names.add(name.lower())
            topics.append({'name': name, 'content': content, 'number': number})
        # The section blurb: the first paragraph under its heading, if any
        paragraphs = [p for p in '\n'.join(section.pop('intro')).strip().split('\n\n')
                      if p.strip() and not BYLINE_RE.search(p.strip())]
        first = paragraphs[0] if paragraphs else ''
        section['description'] = ('' if first.lstrip().startswith(('|', '-', '*', '>'))
                                  else ' '.join(first.split())[:1000])

    if not numbers:
        errors.append('No cards found. Each card needs a heading like "## Card 1 · The Herd Way".')
    if len(names) > MAX_CARDS:
        errors.append(f'{len(names)} cards is too many for one import; the most is {MAX_CARDS}.')
    if len(set(numbers)) != len(numbers):
        dupes = sorted({n for n in numbers if numbers.count(n) > 1})
        errors.append('Card numbers used twice: ' + ', '.join(map(str, dupes)) + '.')
    seen = set()
    for section in sections:
        if section['name'].lower() in seen:
            errors.append(f'The section "{section["name"][:60]}" appears twice. Put all its cards under one heading.')
        seen.add(section['name'].lower())
    if errors:
        raise TheoryImportError(errors)
    return {'sections': [s for s in sections if s['topics']]}


def decode(raw):
    """The uploaded bytes as text, or TheoryImportError."""
    if not raw:
        raise TheoryImportError(['That file is empty.'])
    if len(raw) > MAX_FILE_BYTES:
        raise TheoryImportError([f'That file is over {MAX_FILE_BYTES // 1024} KB.'])
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise TheoryImportError(['That file isn\'t UTF-8 text. Save it as Markdown (.md) and try again.'])


@dataclass
class ImportReport:
    sections: list = field(default_factory=list)
    sections_created: list = field(default_factory=list)
    sections_removed: list = field(default_factory=list)
    created: list = field(default_factory=list)
    moved: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    dry_run: bool = False

    @property
    def section(self):
        """Where to send the coach afterwards: the first section in the file."""
        return self.sections[0]

    def text(self):
        lines = ['DRY RUN: nothing was written'] if self.dry_run else []
        lines.append(f'sections: {len(self.sections)} ({len(self.sections_created)} new)')
        lines.append(f'new cards (drafts): {len(self.created)}')
        lines.append(f'cards moved to another section: {len(self.moved)}')
        lines.append(f'cards overwritten from the file: {len(self.updated)}')
        if self.kept:
            lines.append(f'cards already on the site, left as edited: {len(self.kept)} (use --replace to overwrite)')
        if self.sections_removed:
            lines.append('empty sections removed: ' + ', '.join(self.sections_removed))
        return '\n'.join(lines)

    def summary(self):
        """One line for the site."""
        def n(count, word):
            return f'{count} {word}{"s" if count != 1 else ""}'
        parts = [f'{n(len(self.created), "new card")} added as drafts']
        if self.moved:
            parts.append(f'{n(len(self.moved), "card")} moved to their sections')
        if self.updated:
            parts.append(f'{len(self.updated)} overwritten from the file')
        elif self.kept:
            parts.append(f'{len(self.kept)} already here kept as edited')
        if self.sections_created:
            parts.append(f'{n(len(self.sections_created), "new section")}')
        if self.sections_removed:
            parts.append('emptied and removed: ' + ', '.join(self.sections_removed))
        return ', '.join(parts) + '.'


def import_cards(text, team_id, user_id=None, dry_run=False, replace=False):
    """Put the file's cards in the team's sections of the same names (made
    if needed). The caller commits; with dry_run nothing is changed."""
    parsed = parse_cards(text)
    report = ImportReport(dry_run=dry_run)
    by_name = {s.name.lower(): s for s in TheorySection.query.filter_by(team_organization_id=team_id)}
    existing = {t.name.lower(): t for t in TheoryTopic.query.filter_by(team_organization_id=team_id)
                .order_by(TheoryTopic.id)}
    last_section = db.session.query(db.func.max(TheorySection.order)) \
        .filter_by(team_organization_id=team_id).scalar() or 0
    left = set()  # sections cards were moved out of

    for data in parsed['sections']:
        section = by_name.get(data['name'].lower())
        if section is None:
            last_section += 1
            section = TheorySection(name=data['name'], description=data['description'], order=last_section,
                                    team_organization_id=team_id,
                                    slug=unique_slug(TheorySection, data['name'], team_id))
            by_name[data['name'].lower()] = section
            report.sections_created.append(section.name)
            if not dry_run:
                db.session.add(section)
                db.session.flush()
        report.sections.append(section)

        placed, changed = [], False
        for card in data['topics']:
            topic = existing.get(card['name'].lower())
            if topic is None:
                report.created.append(card['name'])
                changed = True
                if not dry_run:
                    topic = TheoryTopic(section_id=section.id, section=section, name=card['name'],
                                        content=card['content'], published=False,
                                        team_organization_id=team_id, created_by=user_id)
                    db.session.add(topic)
                    placed.append(topic)
                continue
            if topic.section_id != section.id:
                report.moved.append(card['name'])
                changed = True
                left.add(topic.section_id)
                if not dry_run:
                    topic.section_id, topic.section = section.id, section
            if replace:
                report.updated.append(card['name'])
                if not dry_run:
                    topic.name, topic.content = card['name'], card['content']
                    topic.updated_by = user_id or topic.updated_by
            else:
                report.kept.append(card['name'])
            placed.append(topic)

        if changed and not dry_run:
            # The file's order, then whatever else was already in the section
            db.session.flush()
            others = [t for t in section.topics.order_by(TheoryTopic.order.is_(None), TheoryTopic.order,
                                                         TheoryTopic.id) if t not in placed]
            for n, topic in enumerate(placed + others, start=1):
                topic.order = n

    if not dry_run:
        db.session.flush()
    filed = {s.id for s in report.sections}
    moved = {name.lower() for name in report.moved}
    for section_id in left - filed:
        section = db.session.get(TheorySection, section_id)
        remaining = section.topics.count() if not dry_run else sum(
            1 for t in existing.values() if t.section_id == section_id and t.name.lower() not in moved)
        if not remaining:
            report.sections_removed.append(section.name)
            if not dry_run:
                db.session.delete(section)
    return report
