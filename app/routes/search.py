"""Search across the team's players, games, tournaments, sessions, drills,
plays, theory and clips (/search). Everything is looked up for the team
being viewed, and each section follows the same rules as its own pages:
switched-off features are left out, and players don't see draft plays,
unpublished theory or hidden clips."""
from flask import Blueprint, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.team_settings import TeamSettings
from app.utils.team_filter import get_current_team_id

bp = Blueprint('search', __name__)

PER_GROUP = 8
MIN_LENGTH = 2


def _like(q):
    """The search words as a LIKE pattern, with % and _ taken literally."""
    escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def _matches(*columns, like):
    return db.or_(*(c.ilike(like, escape='\\') for c in columns))


def find(q, team_id, is_coach):
    """Groups of results: [{'title', 'icon', 'items': [{'label', 'detail', 'url'}]}]."""
    from app.models.clip import Clip
    from app.models.drill import SavedDrill
    from app.models.game import Game
    from app.models.playbook import Play
    from app.models.player import Player
    from app.models.session import SessionPlan
    from app.models.theory import TheoryTopic
    from app.models.tournament import Tournament

    settings = TeamSettings.query.filter_by(team_id=team_id).first()
    on = lambda feature: settings is None or bool(getattr(settings, feature, True))  # noqa: E731
    like = _like(q)
    groups = []

    def add(title, icon, rows):
        if rows:
            groups.append({'title': title, 'icon': icon, 'items': rows})

    def day(d):
        return f'{d.day} {d.strftime("%b %Y")}' if d else ''

    players = (Player.query.filter(Player.team_organization_id == team_id, _matches(Player.name, like=like))
               .order_by(Player.active.desc(), Player.name).limit(PER_GROUP).all())
    add('Players', 'bi-person', [{
        'label': p.name,
        'detail': ' · '.join(x for x in (f'#{p.jersey_number}' if p.jersey_number else '',
                                         (p.position or '').capitalize()) if x),
        'url': url_for('team.player_detail', player_id=p.id)} for p in players])

    games = (Game.query.filter(Game.team_organization_id == team_id, _matches(Game.opponent, like=like))
             .order_by(Game.date.desc(), Game.id.desc()).limit(PER_GROUP).all())
    add('Games', 'bi-controller', [{
        'label': f'vs {g.opponent}',
        'detail': ' · '.join(x for x in (day(g.date), g.tournament.name if g.tournament else '',
                                         f'{g.our_score}–{g.their_score}' if g.is_played else '') if x),
        'url': url_for('game.detail', game_id=g.id)} for g in games])

    tournaments = (Tournament.query
                   .filter(Tournament.team_organization_id == team_id,
                           _matches(Tournament.name, Tournament.location, like=like))
                   .order_by(Tournament.start_date.desc()).limit(PER_GROUP).all())
    add('Tournaments', 'bi-trophy', [{
        'label': t.name, 'detail': ' · '.join(x for x in (day(t.start_date), t.location or '') if x),
        'url': url_for('tournament.detail', tournament_id=t.id)} for t in tournaments])

    if on('sessions_enabled'):
        sessions = (SessionPlan.query
                    .filter(SessionPlan.team_organization_id == team_id,
                            _matches(SessionPlan.title, SessionPlan.focus_area, like=like))
                    .order_by(SessionPlan.date.desc()).limit(PER_GROUP).all())
        add('Sessions', 'bi-clipboard-check', [{
            'label': s.title, 'detail': ' · '.join(x for x in (day(s.date), s.focus_area or '') if x),
            'url': url_for('session.detail', session_id=s.id)} for s in sessions])

    if on('drills_enabled'):
        drills = (SavedDrill.query
                  .filter(SavedDrill.team_organization_id == team_id,
                          _matches(SavedDrill.title, SavedDrill.description, SavedDrill.focus_area, like=like))
                  .order_by(SavedDrill.title).limit(PER_GROUP).all())
        add('Drills', 'bi-diagram-3', [{
            'label': d.title, 'detail': d.focus_area or '',
            'url': url_for('session.drill_detail', drill_id=d.id)} for d in drills])

    if on('playbook_enabled'):
        plays = Play.query.filter(Play.team_organization_id == team_id,
                                  _matches(Play.name, Play.call, like=like))
        if not is_coach:
            plays = plays.filter(Play.status != 'draft')
        add('Plays', 'bi-diagram-2', [{
            'label': p.name, 'detail': ' · '.join(x for x in ((p.type or '').capitalize(),
                                                              f'"{p.call}"' if p.call else '') if x),
            'url': url_for('playbook.view_play', play_id=p.id)}
            for p in plays.order_by(Play.name).limit(PER_GROUP).all()])

    if on('theory_enabled'):
        topics = TheoryTopic.query.filter(TheoryTopic.team_organization_id == team_id,
                                          _matches(TheoryTopic.name, TheoryTopic.content, like=like))
        if not is_coach:
            topics = topics.filter(TheoryTopic.published.is_(True))
        add('Theory', 'bi-mortarboard', [{
            'label': t.name, 'detail': t.section.name if t.section else '',
            'url': url_for('theory.topic', topic_id=t.id)}
            for t in topics.order_by(TheoryTopic.name).limit(PER_GROUP).all()])

    if on('clip_enabled'):
        clips = Clip.query.filter(Clip.team_organization_id == team_id,
                                  _matches(Clip.title, Clip.description, like=like))
        if not is_coach:
            clips = clips.filter(db.or_(Clip.is_hidden.is_(False), Clip.is_hidden.is_(None)))
        add('Clips', 'bi-camera-video', [{
            'label': c.title or 'Untitled clip', 'detail': f'vs {c.game.opponent}' if c.game else '',
            'url': url_for('clip.view_clip', clip_id=c.id)}
            for c in clips.order_by(Clip.created_at.desc()).limit(PER_GROUP).all()])

    return groups


@bp.route('/search')
@login_required
def index():
    q = (request.args.get('q') or '').strip()[:80]
    team_id = get_current_team_id()
    groups = []
    if team_id and len(q) >= MIN_LENGTH:
        groups = find(q, team_id, bool(current_user.is_coach or current_user.is_admin))
    return render_template('search.html', title='Search', q=q, groups=groups,
                           too_short=bool(q) and len(q) < MIN_LENGTH,
                           total=sum(len(g['items']) for g in groups))
