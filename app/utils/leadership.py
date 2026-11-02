"""Leadership hub helpers: what a post's link plays as, and turning plain
text into safe HTML with its links and video timestamps linked."""
import re
from urllib.parse import urlparse

from markupsafe import Markup, escape

from app.utils.clip_video import (format_timestamp, is_veo_link, link_start_seconds, parse_timestamp,
                                  youtube_embed_url)
from app.utils.media_embed import youtube_id

_URL = re.compile(r'https?://[^\s<>"\']+')
_TIMESTAMP = re.compile(r'(?<![\w:/.])(\d{1,2}:[0-5]\d(?::[0-5]\d)?)(?![\w:])')


def clean_url(text):
    """An http(s) link, or None for anything else (javascript:, junk)."""
    text = (text or '').strip()
    if not text:
        return None
    if '://' not in text:
        if re.match(r'[a-z][a-z0-9+.-]*:(?!\d)', text, re.I):  # javascript:, mailto: (but not host:port)
            return None
        text = 'https://' + text
    parsed = urlparse(text)
    if parsed.scheme not in ('http', 'https') or '.' not in (parsed.hostname or '') or ' ' in text:
        return None
    return text[:500]


def domain(url):
    host = (urlparse(url or '').hostname or '').lower()
    return host.removeprefix('www.')


def is_video_link(url):
    return bool(youtube_id(url or '') or is_veo_link(url))


def start_from(text, url=None):
    """Seconds from the 'start at' box ('1:30'), else the link's own t=."""
    text = (text or '').strip()
    if text:
        try:
            return parse_timestamp(text)
        except ValueError:
            return None
    return link_start_seconds(url) if url else None


def video_for(post):
    """What the post's footage plays as: {'embed_url', 'link', 'label'} or
    None. A team clip plays its own section; a YouTube link plays in the page
    from the start time; Veo can't be embedded, so it's a link out."""
    clip = post.clip
    if clip is not None:
        if clip.video_source != 'veo' and clip.youtube_link:
            return {'embed_url': youtube_embed_url(clip.youtube_link, post.start_seconds or clip.start_time,
                                                   clip.end_time), 'link': None, 'label': clip.title}
        return {'embed_url': None, 'link': clip.youtube_link, 'label': clip.title}
    if post.url and youtube_id(post.url):
        return {'embed_url': youtube_embed_url(post.url, post.start_seconds), 'link': post.url, 'label': None}
    if post.url and is_veo_link(post.url):
        return {'embed_url': None, 'link': post.url, 'label': 'Veo'}
    return None


def render_text(text, seekable=False):
    """Plain text -> HTML: escaped, links made clickable, and (when there is a
    video to jump in) timestamps like 3:42 made into seek links."""
    out, pos = [], 0
    text = text or ''
    for m in _URL.finditer(text):
        out.append(_timestamps(text[pos:m.start()], seekable))
        url = m.group(0).rstrip('.,;:!?)')
        out.append(Markup('<a href="{0}" target="_blank" rel="noopener noreferrer">{0}</a>').format(url))
        out.append(escape(m.group(0)[len(url):]))
        pos = m.end()
    out.append(_timestamps(text[pos:], seekable))
    return Markup('').join(out)


def _timestamps(text, seekable):
    if not seekable:
        return escape(text)
    out, pos = [], 0
    for m in _TIMESTAMP.finditer(text):
        out.append(escape(text[pos:m.start()]))
        seconds = parse_timestamp(m.group(1))
        out.append(Markup('<a href="#lh-video" class="lh-ts" data-seconds="{0}">{1}</a>')
                   .format(seconds, m.group(1)))
        pos = m.end()
    out.append(escape(text[pos:]))
    return Markup('').join(out)


def ago(when, now=None):
    """'just now', '5 min ago', '3 h ago', 'yesterday', '4 days ago', else '2 Mar'."""
    from datetime import datetime
    if when is None:
        return ''
    now = now or datetime.utcnow()
    seconds = (now - when).total_seconds()
    if seconds < 60:
        return 'just now'
    if seconds < 3600:
        return f'{int(seconds // 60)} min ago'
    if seconds < 86400:
        return f'{int(seconds // 3600)} h ago'
    days = int(seconds // 86400)
    if days == 1:
        return 'yesterday'
    if days < 7:
        return f'{days} days ago'
    return when.strftime('%-d %b' if when.year == now.year else '%-d %b %Y')


__all__ = ['ago', 'clean_url', 'domain', 'is_video_link', 'start_from', 'video_for', 'render_text', 'format_timestamp']
