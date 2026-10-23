"""What the bot posts: sessions with Yes / Maybe / No buttons, the weekly
round-up, reminders and announcements.

Each button carries the session it's for in its custom_id
("rsvp:<session id>:<status>"), so clicks work on any post, however old,
and after the site restarts.
"""
from flask import current_app

GREEN, AMBER, RED, BLUE, GOLD = 0x2E9E5B, 0xE0A526, 0xC8423B, 0x3B6FD8, 0xC9A227
BUTTONS = [('attending', 'Yes', 3, '✅'), ('maybe', 'Maybe', 2, '❓'), ('not_attending', 'No', 4, '❌')]
STATUS_WORDS = {'attending': 'Yes', 'maybe': 'Maybe', 'not_attending': 'No'}


def link(endpoint, **values):
    """An absolute link to a page on the site (works outside requests)."""
    base = (current_app.config.get('BASE_URL') or '').rstrip('/')
    path = current_app.url_map.bind('localhost').build(endpoint, values)
    return base + path


def when(session):
    text = session.date.strftime('%a %-d %b') if session.date else 'Date to be set'
    if session.start_time:
        text += f" · {session.start_time:%H:%M}"
        if session.end_time:
            text += f"–{session.end_time:%H:%M}"
    return text


def custom_id(session_id, status):
    return f'rsvp:{session_id}:{status}'


def parse_custom_id(value):
    """(session id, status) from a button's custom_id, or None."""
    parts = (value or '').split(':')
    if len(parts) == 3 and parts[0] == 'rsvp' and parts[1].isdigit() and parts[2] in STATUS_WORDS:
        return int(parts[1]), parts[2]
    return None


def rsvp_row(session):
    buttons = [{'type': 2, 'style': style, 'label': label, 'emoji': {'name': emoji},
                'custom_id': custom_id(session.id, status)}
               for status, label, style, emoji in BUTTONS]
    buttons.append({'type': 2, 'style': 5, 'label': 'Details', 'url': link('session.detail', session_id=session.id)})
    return {'type': 1, 'components': buttons}


def session_embed(session, counts=None):
    fields = [{'name': 'When', 'value': when(session), 'inline': True}]
    if session.location:
        fields.append({'name': 'Where', 'value': session.location[:1024], 'inline': True})
    if session.squads:
        fields.append({'name': 'Squads', 'value': session.squad_names, 'inline': True})
    if counts:
        fields.append({'name': 'Coming so far',
                       'value': f"✅ {counts['attending']}  ❓ {counts['maybe']}  ❌ {counts['not_attending']}",
                       'inline': False})
    embed = {'title': session.title[:256], 'url': link('session.detail', session_id=session.id),
             'color': GREEN, 'fields': fields}
    if session.is_cancelled:
        embed['color'] = RED
        embed['title'] = f'Cancelled: {session.title}'[:256]
        if session.cancel_reason:
            embed['description'] = session.cancel_reason[:2000]
    return embed


def session_post(session, intro=None, counts=None):
    """One session, with answer buttons (dropped when sent by webhook)."""
    payload = {'embeds': [session_embed(session, counts)],
               'allowed_mentions': {'parse': []}}
    if intro:
        payload['content'] = intro
    if not session.is_cancelled:
        payload['components'] = [rsvp_row(session)]
        payload['embeds'][0].setdefault('footer', {'text': 'Answer with the buttons, or on the site'})
    return payload


def week_intro(team_name, count):
    return {'content': (f"**This week's training for {team_name}** – {count} session"
                        f"{'s' if count != 1 else ''}. Tap Yes, Maybe or No on each one. "
                        f"[All your dates]({link('training.availability')})"),
            'allowed_mentions': {'parse': []}}


def reminder(sessions, statuses):
    """A direct message asking a player to firm up their answers (up to five
    sessions: one row of buttons each)."""
    lines = []
    for s in sessions:
        said = STATUS_WORDS.get(statuses.get(s.id))
        lines.append(f"• **{s.title}** – {when(s)}" + (f" (you said {said})" if said else ' (no answer yet)'))
    return {
        'content': ("Can you confirm whether you're coming?\n" + '\n'.join(lines) +
                    f"\n\nOr answer for every date here: {link('training.availability')}"),
        'components': [rsvp_row(s) for s in sessions[:5]],
        'allowed_mentions': {'parse': []},
    }


def cancelled(session):
    payload = session_post(session, intro=f"❌ **{session.title}** on {when(session)} is cancelled.")
    return payload


def announcement(title, description, url, color=BLUE, fields=None):
    embed = {'title': title[:256], 'url': url, 'color': color}
    if description:
        embed['description'] = description[:2000]
    if fields:
        embed['fields'] = fields
    return {'embeds': [embed], 'allowed_mentions': {'parse': []}}


def plain(text):
    return {'content': text[:2000], 'allowed_mentions': {'parse': []}}
