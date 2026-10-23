"""Announce new things in a team's Discord once they're saved.

New one-off sessions (not the dates a training schedule makes: the weekly
post covers those), tournaments and games go out when the team has "new
events" on; clips and theory topics when it has "new items" on. Rows are
noted as they're inserted and posted after the commit, on a background
thread, so a slow or broken Discord never holds up the page.
"""
import logging
import threading

from flask import current_app, has_app_context
from sqlalchemy import event, select
from sqlalchemy.orm import Session as OrmSession

logger = logging.getLogger(__name__)
_registered = False

# model name -> TeamSettings flag that turns its announcements on
FLAGS = {
    'SessionPlan': 'discord_notify_new_events',
    'Tournament': 'discord_notify_new_events',
    'Game': 'discord_notify_new_events',
    'Clip': 'discord_notify_new_items',
    'TheoryTopic': 'discord_notify_new_items',
}


def register():
    global _registered
    if _registered:
        return
    _registered = True
    from app.models.clip import Clip
    from app.models.game import Game
    from app.models.session import SessionPlan
    from app.models.theory import TheoryTopic
    from app.models.tournament import Tournament

    for model in (SessionPlan, Tournament, Game, Clip, TheoryTopic):
        event.listen(model, 'after_insert', _noted)
    event.listen(OrmSession, 'after_commit', _after_commit)
    event.listen(OrmSession, 'after_rollback', lambda session: session.info.pop('discord_new', None))


def _noted(mapper, connection, target):
    name = type(target).__name__
    team_id = getattr(target, 'team_organization_id', None)
    if not team_id or (name == 'SessionPlan' and target.schedule_id):
        return
    from app.models.team_settings import TeamSettings
    table = TeamSettings.__table__
    wanted = connection.execute(
        select(table.c.discord_enabled, table.c[FLAGS[name]]).where(table.c.team_id == team_id)).first()
    if not wanted or not wanted[0] or not wanted[1]:
        return
    from sqlalchemy.orm import object_session
    session = object_session(target)
    if session is not None:
        session.info.setdefault('discord_new', []).append((name, target.id))


def _after_commit(session):
    items = session.info.pop('discord_new', None)
    if not items or not has_app_context():
        return
    app = current_app._get_current_object()

    def run():
        with app.app_context():
            for name, row_id in items:
                try:
                    announce(name, row_id)
                except Exception as e:  # never let a post break anything
                    logger.warning('Discord announcement of %s %s failed: %s', name, row_id, e)

    threading.Thread(target=run, daemon=True).start()


def announce(name, row_id):
    from app import db
    from app.discord import messages, notify
    from app.models.clip import Clip
    from app.models.game import Game
    from app.models.session import SessionPlan
    from app.models.theory import TheoryTopic
    from app.models.tournament import Tournament

    model = {'SessionPlan': SessionPlan, 'Tournament': Tournament, 'Game': Game,
             'Clip': Clip, 'TheoryTopic': TheoryTopic}[name]
    row = db.session.get(model, row_id)
    if row is None:
        return False
    link = messages.link
    if name == 'SessionPlan':
        payload = messages.session_post(row, intro='📅 New session added')
    elif name == 'Tournament':
        dates = row.start_date.strftime('%a %-d %b') if row.start_date else 'Dates to be set'
        payload = messages.announcement(f'🏆 New tournament: {row.name}', f'{dates} · {row.location or ""}'.strip(' ·'),
                                        link('tournament.detail', tournament_id=row.id), messages.GOLD)
    elif name == 'Game':
        payload = messages.announcement(f'🥏 New game: vs {row.opponent or "TBD"}',
                                        row.date.strftime('%a %-d %b') if row.date else None,
                                        link('game.detail', game_id=row.id), messages.RED)
    elif name == 'Clip':
        payload = messages.announcement(f'🎬 New clip: {row.title}', None, link('clip.view_clip', clip_id=row.id))
    else:
        payload = messages.announcement(f'📚 New theory: {row.title}', None, link('theory.topic', topic_id=row.id))
    return notify.post(row.team_organization_id, payload)
