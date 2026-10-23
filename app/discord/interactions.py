"""Button clicks from Discord (POSTed, signed, to /discord/interactions).

A Yes / Maybe / No click saves the clicker's answer through
app.utils.rsvp.set_rsvp, exactly as the site does, and replies with a
message only they can see.
"""
from app import db
from app.discord import messages

PING, COMPONENT = 1, 3
PONG, REPLY = 1, 4
EPHEMERAL = 64


def reply(text):
    return {'type': REPLY, 'data': {'content': text[:2000], 'flags': EPHEMERAL,
                                    'allowed_mentions': {'parse': []}}}


def handle(payload):
    """The response to one interaction."""
    kind = payload.get('type')
    if kind == PING:
        return {'type': PONG}
    if kind != COMPONENT:
        return reply("Sorry, I don't know that one.")

    parsed = messages.parse_custom_id((payload.get('data') or {}).get('custom_id'))
    if parsed is None:
        return reply("That button doesn't do anything any more.")
    session_id, status = parsed
    who = (payload.get('member') or {}).get('user') or payload.get('user') or {}
    return answer(who.get('id'), session_id, status)


def answer(discord_user_id, session_id, status):
    from app.models.session import SessionPlan
    from app.models.user import User
    from app.utils.rsvp import LABELS, set_rsvp

    session = db.session.get(SessionPlan, session_id)
    if session is None:
        return reply('That session has been deleted.')
    if session.is_cancelled:
        return reply(f'{session.title} on {messages.when(session)} is cancelled.')

    user = User.query.filter_by(discord_id=str(discord_user_id)).first() if discord_user_id else None
    if user is None:
        return reply("I don't know who you are on Ultimate Coach yet. Connect your Discord account "
                     f"(it takes a few seconds), then tap again: {messages.link('discord.connect')}")
    player = user.player_for(session.team_organization_id)
    if player is None:
        return reply("Your Ultimate Coach account isn't linked to a player on this team, "
                     "so I can't answer for you. Ask a coach to link it.")

    set_rsvp(session, player, status)
    db.session.commit()
    return reply(f"Got it: **{LABELS[status]}** for {session.title}, {messages.when(session)}. "
                 f"Change it any time with the buttons or at {messages.link('training.availability')}")
