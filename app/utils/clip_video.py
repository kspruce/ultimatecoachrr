"""Video links on clips: YouTube embeds and timestamp links, and Veo links.

YouTube ids come from media_embed.youtube_id, the one parser for every
YouTube link format (watch, youtu.be, shorts, live, embed)."""
import re
from urllib.parse import parse_qs, urlparse

from app.utils.media_embed import youtube_id

_VEO_MATCH = re.compile(r'^https?://app\.veo\.co/matches/([a-zA-Z0-9-]+)')


def youtube_embed_url(link, start=None, end=None):
    """The iframe URL for a YouTube link, starting/ending at the given seconds."""
    video_id = youtube_id(link or '')
    if not video_id:
        return None
    params = [f'{name}={value}' for name, value in (('start', start), ('end', end)) if value]
    return f'https://www.youtube.com/embed/{video_id}' + ('?' + '&'.join(params) if params else '')


def youtube_timestamp_link(link, seconds):
    """A watch link that opens the video at the given second."""
    video_id = youtube_id(link or '')
    if not video_id:
        return None
    return f'https://www.youtube.com/watch?v={video_id}&t={seconds or 0}s'


def shared_embed_url(clip):
    """The player for a clip on its public share page. Veo matches can't be
    embedded, so those pages link out to Veo instead."""
    if clip.video_source == 'veo':
        return None
    return youtube_embed_url(clip.youtube_link, clip.start_time, clip.end_time)


def is_veo_link(link):
    return bool(_VEO_MATCH.match(link or ''))


def parse_timestamp(text):
    """'90', '1:30' or '1:02:03' -> seconds. Raises ValueError otherwise."""
    text = (text or '').strip()
    if not re.fullmatch(r'\d+(:[0-5]?\d){0,2}', text):
        raise ValueError(text)
    seconds = 0
    for part in text.split(':'):
        seconds = seconds * 60 + int(part)
    return seconds


def format_timestamp(seconds):
    """Seconds -> 'm:ss', or 'h:mm:ss' from an hour up."""
    if seconds is None:
        return ''
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def link_start_seconds(link):
    """The start time a YouTube link carries (t=90, t=90s, t=1m30s, start=90)."""
    query = urlparse(link or '').query
    value = (parse_qs(query).get('t') or parse_qs(query).get('start') or [''])[0]
    m = re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?', value)
    if not value or not m:
        return None
    h, mins, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mins * 60 + s or None


def check_link(source, link):
    """What a clip link will play as: {'embed_url', 'start', 'error'}."""
    link = (link or '').strip()
    if source == 'veo':
        if is_veo_link(link):
            return {'embed_url': None, 'start': None, 'error': None}
        if youtube_id(link):
            return {'embed_url': None, 'start': None, 'error': 'That is a YouTube link. Choose YouTube as the source.'}
        return {'embed_url': None, 'start': None,
                'error': 'Not a Veo match link. It should look like https://app.veo.co/matches/…'}
    if youtube_id(link):
        return {'embed_url': youtube_embed_url(link), 'start': link_start_seconds(link), 'error': None}
    if is_veo_link(link):
        return {'embed_url': None, 'start': None, 'error': 'That is a Veo link. Choose Veo as the source.'}
    return {'embed_url': None, 'start': None,
            'error': "Can't play this link. Use a YouTube video link (watch, youtu.be, shorts or live)."}
