# app/utils/schedule_parse.py
"""Turn a pasted tournament schedule into games, one line per game:

    Sat 09:00 vs Rival FC Field 3
    Sat 11:30 v Hucks @ Pitch 2
    2026-11-08 10:00 Brighton Breeze
    Sunday 2pm vs Kent (field 4)

A day name picks that day within the tournament; no date means the first
day. Time, "vs" and the field are all optional; the opponent is required.
"""
import re
from datetime import date, datetime, timedelta

DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

_ISO = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})\b')
_DMY = re.compile(r'^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b')
_DAY = re.compile(r'^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\b', re.I)
_TIME = re.compile(r'^(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b', re.I)
_VS = re.compile(r'^(?:vs\.?|v\.?|versus|against)(?:\s+|$)', re.I)
_FIELD = re.compile(r'(?:\s*[,\-–]\s*|\s+)(?:\(\s*)?((?:field|pitch|court)\s*[\w-]+)\s*\)?\s*$', re.I)
_AT = re.compile(r'\s+@\s*(.+)$')


def _tournament_days(start, end):
    if not start:
        return []
    end = end or start
    return [start + timedelta(days=i) for i in range((end - start).days + 1)][:14]


def _take_date(text, start, end):
    m = _ISO.match(text)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])), text[m.end():].strip(), None
        except ValueError:
            return None, text[m.end():].strip(), f'"{m[0]}" isn\'t a date'
    m = _DMY.match(text)
    if m and (m[3] or ':' not in text[:m.end()]):
        year = int(m[3]) if m[3] else (start or date.today()).year
        if year < 100:
            year += 2000
        try:
            return date(year, int(m[2]), int(m[1])), text[m.end():].strip(), None
        except ValueError:
            return None, text[m.end():].strip(), f'"{m[0]}" isn\'t a date'
    m = _DAY.match(text)
    if m:
        weekday = DAYS.index(m[1].lower()[:3])
        days = [d for d in _tournament_days(start, end) if d.weekday() == weekday]
        rest = text[m.end():].strip()
        if days:
            return days[0], rest, None
        if start:
            return None, rest, f'The tournament has no {m[0].rstrip(".")}'
        return None, rest, None
    return None, text, None


def _take_time(text):
    m = _TIME.match(text)
    # A bare number with nothing after it is the opponent's name, not a time
    if not m or not (m[2] or m[3]):
        return None, text, None
    hour, minute = int(m[1]), int(m[2] or 0)
    meridian = (m[3] or '').lower()
    if meridian == 'pm' and hour < 12:
        hour += 12
    elif meridian == 'am' and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None, text[m.end():].strip(), f'"{m[0].strip()}" isn\'t a time'
    return datetime(2000, 1, 1, hour, minute).time(), text[m.end():].strip(), None


def parse_line(line, start=None, end=None):
    """One game from one line: {'date', 'start_time', 'opponent', 'field',
    'error', 'line'}."""
    text = ' '.join(line.strip().split())
    game = {'line': text, 'date': None, 'start_time': None, 'opponent': '', 'field': None, 'error': None}
    errors = []
    day, text, err = _take_date(text, start, end)
    errors.append(err)
    text = text.lstrip(',- ')
    start_time, text, err = _take_time(text)
    errors.append(err)
    text = _VS.sub('', text.lstrip(',- '))
    m = _AT.search(text) or _FIELD.search(text)
    if m:
        game['field'] = m[1].strip().rstrip(')').strip()[:50]
        text = text[:m.start()]
    game['opponent'] = text.strip(' ,-–')[:100]
    game['date'] = day or start
    game['start_time'] = start_time
    if not game['opponent']:
        errors.append('No opponent')
    game['error'] = '; '.join(e for e in errors if e) or None
    return game


def parse_schedule(text, start=None, end=None):
    return [parse_line(line, start, end) for line in (text or '').splitlines()
            if line.strip() and not line.strip().startswith('#')]
