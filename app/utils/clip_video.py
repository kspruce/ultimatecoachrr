"""Video links on clips: YouTube embeds and timestamp links, and Veo links.

YouTube ids come from media_embed.youtube_id, the one parser for every
YouTube link format (watch, youtu.be, shorts, live, embed)."""
import re

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


def veo_embed_url(link):
    m = _VEO_MATCH.match(link or '')
    return f'https://app.veo.co/embed/{m.group(1)}' if m else None


def shared_embed_url(clip):
    """The player for a clip on its public share page."""
    if clip.video_source == 'veo':
        return veo_embed_url(clip.youtube_link)
    return youtube_embed_url(clip.youtube_link, clip.start_time, clip.end_time)
