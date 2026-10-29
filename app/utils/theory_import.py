"""Load a markdown file of theory cards into a team's Theory hub, from
Theory > New > Import cards or `flask import-theory`.

The file's `# Title` names the section. Each `## Card 12 · Getting open`
heading starts a topic (the text after the number is its title) and
everything up to the next `##` heading is its content. Any other `##`
section before the first card (e.g. "How to use these cards") becomes a
note for coaches, kept as a draft. Cards arrive as drafts, so coaches can
publish each one in the week it is taught.

Re-importing adds new cards and leaves ones already in the section (matched
on title) as coaches edited them, unless replace is set.
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


class TheoryImportError(Exception):
    def __init__(self, errors):
        super().__init__('; '.join(errors))
        self.errors = errors


def parse_cards(text):
    """{'section', 'description', 'topics': [{'name', 'content', 'number'}]}
    from the markdown, or TheoryImportError listing what's wrong."""
    section, blocks, current = None, [], None
    in_fence = False
    for line in text.replace('\r\n', '\n').split('\n'):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else HEADING_RE.match(line)
        title = None if in_fence or section or blocks else TITLE_RE.match(line)
        if title:
            section = title.group(1).strip()
        elif heading:
            current = {'heading': heading.group(1).strip(), 'lines': []}
            blocks.append(current)
        elif current is not None:
            current['lines'].append(line)

    errors, topics, names = [], [], set()
    for block in blocks:
        card = CARD_RE.match(block['heading'])
        if card:
            number, name = int(card.group(1)), card.group(2).strip()
        elif not any(t['number'] is not None for t in topics):
            number, name = None, block['heading']  # a note before the cards
        else:
            errors.append(f'"{block["heading"][:60]}" comes after the cards but isn\'t a "Card N · Title" heading.')
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

    if not any(t['number'] is not None for t in topics):
        errors.append('No cards found. Each card needs a heading like "## Card 1 · The Herd Way".')
    if len(topics) > MAX_CARDS:
        errors.append(f'{len(topics)} cards is too many for one import; the most is {MAX_CARDS}.')
    numbers = [t['number'] for t in topics if t['number'] is not None]
    if len(set(numbers)) != len(numbers):
        dupes = sorted({n for n in numbers if numbers.count(n) > 1})
        errors.append('Card numbers used twice: ' + ', '.join(map(str, dupes)) + '.')
    if not section:
        errors.append('The file needs a "# Title" line at the top: it names the section.')
    elif len(section) > NAME_MAX:
        errors.append(f'The "# Title" is {len(section)} characters; the most for a section name is {NAME_MAX}.')
    if errors:
        raise TheoryImportError(errors)

    # The section blurb: the first paragraph of the opening note, if any
    description = ''
    if topics[0]['number'] is None:
        paragraph = topics[0]['content'].strip().split('\n\n')[0]
        if not paragraph.lstrip().startswith(('|', '-', '*', '#', '>')):
            description = ' '.join(paragraph.split())[:1000]
    return {'section': section, 'description': description, 'topics': topics}


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
    section: TheorySection = None
    section_created: bool = False
    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    dry_run: bool = False

    def text(self):
        lines = ['DRY RUN: nothing was written'] if self.dry_run else []
        lines.append(f'section: {self.section.name}' + (' (new)' if self.section_created else ''))
        lines.append(f'new cards (drafts): {len(self.created)}')
        lines.append(f'cards overwritten from the file: {len(self.updated)}')
        if self.kept:
            lines.append(f'cards already on the site, left as edited: {len(self.kept)} (use --replace to overwrite)')
        return '\n'.join(lines)

    def summary(self):
        """One line for the site."""
        parts = [f'{len(self.created)} new card{"s" if len(self.created) != 1 else ""} added as drafts']
        if self.updated:
            parts.append(f'{len(self.updated)} overwritten from the file')
        if self.kept:
            parts.append(f'{len(self.kept)} already here and left as edited')
        return f'{self.section.name}: ' + ', '.join(parts) + '.'


def import_cards(text, team_id, user_id=None, dry_run=False, replace=False):
    """Add the file's cards to the team's section of the same name (made if
    needed). The caller commits; with dry_run nothing is added."""
    parsed = parse_cards(text)
    report = ImportReport(dry_run=dry_run)
    section = (TheorySection.query.filter_by(team_organization_id=team_id)
               .filter(db.func.lower(TheorySection.name) == parsed['section'].lower()).first())
    if section is None:
        report.section_created = True
        last = db.session.query(db.func.max(TheorySection.order)).filter_by(team_organization_id=team_id).scalar()
        section = TheorySection(name=parsed['section'], description=parsed['description'],
                                order=(last or 0) + 1, team_organization_id=team_id,
                                slug=unique_slug(TheorySection, parsed['section'], team_id))
        if not dry_run:
            db.session.add(section)
            db.session.flush()
    report.section = section

    existing = {} if report.section_created else {
        t.name.lower(): t for t in section.topics.filter_by(team_organization_id=team_id)}
    last = 0 if report.section_created else (
        db.session.query(db.func.max(TheoryTopic.order)).filter_by(section_id=section.id).scalar() or 0)
    for card in parsed['topics']:
        topic = existing.get(card['name'].lower())
        if topic is None:
            report.created.append(card['name'])
            if dry_run:
                continue
            last += 1
            db.session.add(TheoryTopic(section_id=section.id, name=card['name'], content=card['content'],
                                       order=last, published=False, team_organization_id=team_id,
                                       created_by=user_id))
        elif replace:
            report.updated.append(card['name'])
            if not dry_run:
                topic.name, topic.content = card['name'], card['content']
                topic.updated_by = user_id or topic.updated_by
        else:
            report.kept.append(card['name'])
    return report
