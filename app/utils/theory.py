"""Theory hub helpers: photo uploads, video titles, tags, search and
reading progress."""
import base64
import io
import logging

from flask import current_app

from app import db
from app.models.theory import (TheoryAssignment, TheoryImage, TheoryRead, TheorySection, TheoryTag,
                               TheoryTopic, video_embed_url)

logger = logging.getLogger(__name__)

MAX_IMAGE_SIDE = 1600  # px; plenty for a phone or laptop screen
IMAGE_QUALITY = 82


class ImageError(ValueError):
    pass


def save_image(file, team_id, user_id):
    """Resize an uploaded photo (turned the right way up, location and
    camera details dropped) and keep it as a TheoryImage. The caller commits."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    raw = file.read()
    if not raw:
        raise ImageError('That file is empty.')
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("That file isn't a photo we can read. Try a JPEG, PNG, WebP or GIF.")
    img = ImageOps.exif_transpose(img)
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
    img = img.convert('RGBA' if has_alpha else 'RGB')
    out = io.BytesIO()
    img.save(out, format='WEBP', quality=IMAGE_QUALITY, method=4)
    image = TheoryImage(team_organization_id=team_id, uploaded_by=user_id, mime_type='image/webp',
                        data=base64.b64encode(out.getvalue()).decode('ascii'),
                        width=img.width, height=img.height)
    db.session.add(image)
    return image


def fetch_video_title(url):
    """The video's title from YouTube or Vimeo, or None. Best effort: a
    slow or failing lookup just leaves the title blank."""
    if current_app.testing or not video_embed_url(url):
        return None
    import requests
    endpoint = ('https://vimeo.com/api/oembed.json' if 'vimeo.com' in url
                else 'https://www.youtube.com/oembed')
    try:
        response = requests.get(endpoint, params={'url': url, 'format': 'json'}, timeout=3)
        if response.ok:
            return (response.json().get('title') or '').strip()[:200] or None
    except Exception as e:
        logger.info('No title for video %s: %s', url, e)
    return None


def parse_tags(text):
    """'Zone, handler  resets,zone' -> ['Zone', 'handler resets'] (first
    spelling wins, case-insensitively)."""
    seen, tags = set(), []
    for part in (text or '').split(','):
        name = ' '.join(part.split())[:50]
        if name and name.lower() not in seen:
            seen.add(name.lower())
            tags.append(name)
    return tags


def tags_for(names, team_id):
    """The team's TheoryTag rows for these names, adding any that are new."""
    existing = {t.name.lower(): t for t in TheoryTag.query.filter_by(team_organization_id=team_id)}
    tags = []
    for name in names:
        tag = existing.get(name.lower())
        if tag is None:
            tag = TheoryTag(name=name, team_organization_id=team_id)
            db.session.add(tag)
            existing[name.lower()] = tag
        tags.append(tag)
    return tags


def drop_unused_tags(team_id):
    for tag in TheoryTag.query.filter_by(team_organization_id=team_id):
        if not tag.topics.count():
            db.session.delete(tag)


def plain_text(markdown_text):
    """Markdown without its markup, for excerpts and search."""
    import re
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', markdown_text or '')   # images
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)                # links -> their text
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[#>*_`~|{}]+', ' ', text)
    return ' '.join(text.split())


def search(topics, q):
    """Topics matching every word of q, best first (title, then tags, then text)."""
    words = q.lower().split()
    scored = []
    for t in topics:
        title = t.name.lower()
        tags = ' '.join(tag.name.lower() for tag in t.tags)
        body = plain_text(t.content).lower()
        if all(w in title or w in tags or w in body for w in words):
            score = sum(5 * (w in title) + 3 * (w in tags) + (w in body) for w in words)
            scored.append((-score, t.name.lower(), t))
    return [t for _, _, t in sorted(scored, key=lambda s: s[:2])]


def snippet(t, q, width=140):
    """A bit of the topic's text around the first word of q."""
    text = plain_text(t.content)
    words = q.lower().split()
    at = min((i for i in (text.lower().find(w) for w in words) if i >= 0), default=0)
    start = max(0, at - width // 3)
    piece = text[start:start + width]
    return ('…' if start else '') + piece + ('…' if start + width < len(text) else '')


def read_ids(user_id, team_id):
    return {topic_id for (topic_id,) in db.session.query(TheoryRead.topic_id)
            .filter_by(user_id=user_id, team_organization_id=team_id)}


def ordered_topics(team_id, include_drafts=False):
    """Every topic on the team in reading order: sections in order, topics
    in order within them."""
    query = (TheoryTopic.query.join(TheorySection, TheorySection.id == TheoryTopic.section_id)
             .filter(TheoryTopic.team_organization_id == team_id))
    if not include_drafts:
        query = query.filter(TheoryTopic.published.is_(True))
    return query.order_by(TheorySection.order, TheorySection.id, TheoryTopic.order, TheoryTopic.id).all()


def continue_reading(user_id, team_id, topics, read):
    """The next unread topic after the one this person read last, in the
    same section (or the first unread one there), else None."""
    last = (TheoryRead.query.filter_by(user_id=user_id, team_organization_id=team_id)
            .order_by(TheoryRead.read_at.desc()).first())
    if last is None:
        return None
    in_section = [t for t in topics if t.section_id == last.topic.section_id]
    after = [t for t in in_section if t.id != last.topic_id]
    ids = [t.id for t in in_section]
    if last.topic_id in ids:
        i = ids.index(last.topic_id)
        after = in_section[i + 1:] + in_section[:i]
    return next((t for t in after if t.id not in read), None)


def assigned_unread(user_id, team_id):
    """[(assignment, topic)] the team has been asked to read and this person
    hasn't, soonest due first."""
    read = read_ids(user_id, team_id)
    rows = (TheoryAssignment.query.join(TheoryTopic, TheoryTopic.id == TheoryAssignment.topic_id)
            .filter(TheoryAssignment.team_organization_id == team_id, TheoryTopic.published.is_(True))
            .all())
    rows = [a for a in rows if a.topic_id not in read]
    return sorted(rows, key=lambda a: (a.due_date is None, a.due_date, a.created_at))


def team_readers(team_id):
    """[(user, name)] for everyone on the team who could read the hub (not
    guests), by name: their player name where they have one."""
    from app.models.team_membership import TeamMembership
    from app.models.user import User
    members = (User.query.join(TeamMembership, TeamMembership.user_id == User.id)
               .filter(TeamMembership.team_organization_id == team_id, TeamMembership.role != 'guest')
               .all())
    named = []
    for user in members:
        player = user.player_for(team_id)
        named.append((user, (player.name if player and player.name else user.username)))
    return sorted(named, key=lambda pair: pair[1].lower())
