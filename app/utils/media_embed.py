"""Turn a shared link (YouTube, Vimeo, Google Drive, Google Slides/Docs) into
an iframe URL. Anything else is shown as a plain link, so Zoom cloud
recordings, Dropbox and so on still work, they just open in a new tab."""
import re
from urllib.parse import parse_qs, urlparse

_YOUTUBE_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')


def is_web_url(url):
    """Only http(s) links are stored, so a link can never run script."""
    try:
        parsed = urlparse((url or '').strip())
    except ValueError:
        return False
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def youtube_id(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower().removeprefix('www.').removeprefix('m.')
    candidate = None
    if host == 'youtu.be':
        candidate = parsed.path.lstrip('/').split('/')[0]
    elif host in ('youtube.com', 'youtube-nocookie.com'):
        if parsed.path == '/watch':
            candidate = parse_qs(parsed.query).get('v', [None])[0]
        else:
            m = re.match(r'^/(?:embed|live|shorts|v)/([^/?#]+)', parsed.path)
            candidate = m.group(1) if m else None
    return candidate if candidate and _YOUTUBE_ID.match(candidate) else None


def embed_url(url):
    """The URL to put in an <iframe>, or None if the link can't be embedded."""
    if not is_web_url(url):
        return None
    url = url.strip()
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower().removeprefix('www.')

    yt = youtube_id(url)
    if yt:
        return f'https://www.youtube-nocookie.com/embed/{yt}'

    if host == 'vimeo.com':
        m = re.match(r'^/(\d+)(?:/([0-9a-f]+))?', parsed.path)
        if m:
            return f'https://player.vimeo.com/video/{m.group(1)}' + (f'?h={m.group(2)}' if m.group(2) else '')
    if host == 'player.vimeo.com' and parsed.path.startswith('/video/'):
        return url

    if host == 'docs.google.com':
        m = re.match(r'^/presentation/d/([\w-]+)', parsed.path)
        if m:
            return f'https://docs.google.com/presentation/d/{m.group(1)}/embed'
        m = re.match(r'^/(document|spreadsheets)/d/([\w-]+)', parsed.path)
        if m:
            return f'https://docs.google.com/{m.group(1)}/d/{m.group(2)}/preview'
    if host == 'drive.google.com':
        m = re.match(r'^/file/d/([\w-]+)', parsed.path)
        if m:
            return f'https://drive.google.com/file/d/{m.group(1)}/preview'
    return None
