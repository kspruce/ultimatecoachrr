# app/utils/season.py
"""Which season (and squad) a page shows, and starting a new season.

Seasons are one calendar year ("2026"). Pages show the season the user is
viewing: the current season unless they picked another one (or "All time")
from the season switcher. Clubs with more than one squad can also narrow
pages to one squad.

`Player.active` is kept equal to "on the current season's roster and not
left", so every player picker that lists active players offers this
season's roster without knowing about seasons.
"""
import re
from datetime import date

from flask import g, has_request_context, request, session as flask_session
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session as OrmSession

from app import db
from app.models.season import Season, SeasonRoster, Squad

ALL = 'all'
_YEAR = re.compile(r'(19|20)\d\d')


# ── Seasons ────────────────────────────────────────────────────────────────

def label_year(label):
    """The year in a season label: '2026' -> 2026, '2025/26' -> 2025."""
    match = _YEAR.search(label or '')
    return int(match.group()) if match else None


def team_seasons(team_id):
    """The team's seasons, newest first (set up from its data the first time)."""
    if not team_id:
        return []
    cache = _request_cache('seasons')
    if team_id not in cache:
        ensure_seasons(team_id)
        cache[team_id] = Season.query.filter_by(team_organization_id=team_id).order_by(Season.year.desc()).all()
    return cache[team_id]


def current_season(team_id):
    return next((s for s in team_seasons(team_id) if s.is_current), None)


def team_squads(team_id):
    if not team_id:
        return []
    cache = _request_cache('squads')
    if team_id not in cache:
        cache[team_id] = (Squad.query.filter_by(team_organization_id=team_id)
                          .order_by(Squad.sort_order, Squad.name).all())
    return cache[team_id]


def forget_cached():
    """Call after adding, removing or switching seasons or squads mid-request."""
    if has_request_context():
        g.pop('_season_cache', None)


def _request_cache(key):
    if not has_request_context():
        return {}
    store = g.setdefault('_season_cache', {})
    return store.setdefault(key, {})


def ensure_seasons(team_id):
    """First time a team is looked at: make a season for every year it has
    games, tournaments or sessions in (this year if it has none), mark the
    current one, put each row in its season and fill the rosters from who
    played. Does nothing once the team has seasons. Commits."""
    if Season.query.filter_by(team_organization_id=team_id).first():
        return False
    from app.models.game import Game
    from app.models.session import SessionPlan
    from app.models.tournament import Tournament

    years = set()
    years.update(d.year for (d,) in db.session.query(Game.date).filter(
        Game.team_organization_id == team_id, Game.date.isnot(None)))
    years.update(d.year for (d,) in db.session.query(Tournament.start_date).filter(
        Tournament.team_organization_id == team_id, Tournament.start_date.isnot(None)))
    years.update(y for (label,) in db.session.query(Tournament.season).filter(
        Tournament.team_organization_id == team_id) if (y := label_year(label)))
    years.update(d.year for (d,) in db.session.query(SessionPlan.date).filter(
        SessionPlan.team_organization_id == team_id, SessionPlan.date.isnot(None)))

    this_year = date.today().year
    if not years:
        years = {this_year}
    if this_year in years:
        current = this_year
    else:
        past = [y for y in years if y < this_year]
        current = max(past) if past else min(years)

    for year in sorted(years):
        start, end = Season.default_dates(year)
        db.session.add(Season(team_organization_id=team_id, year=year, start_date=start, end_date=end,
                              is_current=(year == current)))
    db.session.flush()
    assign_unseasoned(team_id)
    fill_rosters_from_games(team_id)
    sync_active_flags(team_id)
    db.session.commit()
    forget_cached()
    return True


def season_for_date(team_id, day, seasons=None):
    """The season a date falls in: by the seasons' dates, then by year."""
    if day is None:
        return None
    seasons = seasons if seasons is not None else Season.query.filter_by(team_organization_id=team_id).all()
    return (next((s for s in seasons if s.contains(day)), None)
            or next((s for s in seasons if s.year == day.year), None))


def assign_unseasoned(team_id):
    """Put the team's games, tournaments and sessions that have no season
    into one: by date, then the tournament's season, then the current one."""
    from app.models.game import Game
    from app.models.session import SessionPlan
    from app.models.tournament import Tournament

    seasons = Season.query.filter_by(team_organization_id=team_id).all()
    if not seasons:
        return
    current = next((s for s in seasons if s.is_current), None)
    by_year = {s.year: s for s in seasons}

    for t in Tournament.query.filter_by(team_organization_id=team_id, season_id=None):
        season = (season_for_date(team_id, t.start_date, seasons)
                  or by_year.get(label_year(t.season)) or current)
        if season:
            t.season_id = season.id
            t.season = t.season or season.name
    db.session.flush()
    for game in Game.query.filter_by(team_organization_id=team_id, season_id=None):
        season = (season_for_date(team_id, game.date, seasons)
                  or (game.tournament and game.tournament.season_obj) or current)
        if season:
            game.season_id = season.id
        if game.squad_id is None and game.tournament:
            game.squad_id = game.tournament.squad_id
    for s in SessionPlan.query.filter_by(team_organization_id=team_id, season_id=None):
        season = season_for_date(team_id, s.date, seasons) or current
        if season:
            s.season_id = season.id
    db.session.flush()


def fill_rosters_from_games(team_id):
    """Add everyone who played in a season's games to that season's roster,
    and every active player to the current season's."""
    from app.models.game import Game
    from app.models.game_player import GamePlayer
    from app.models.gameday import GameDayPlayerStats
    from app.models.player import Player
    from app.models.point import LineUp, Point

    seasons = Season.query.filter_by(team_organization_id=team_id).all()
    players = {p.id: p for p in Player.query.filter_by(team_organization_id=team_id)}
    have = {(r.season_id, r.player_id) for r in SeasonRoster.query.filter_by(team_organization_id=team_id)}

    played = set()
    played.update(db.session.query(Game.season_id, GamePlayer.player_id).join(GamePlayer, GamePlayer.game_id == Game.id)
                  .filter(Game.team_organization_id == team_id).all())
    played.update(db.session.query(Game.season_id, LineUp.player_id).join(Point, Point.game_id == Game.id)
                  .join(LineUp, LineUp.point_id == Point.id).filter(Game.team_organization_id == team_id).all())
    played.update(db.session.query(Game.season_id, GameDayPlayerStats.player_id)
                  .join(GameDayPlayerStats, GameDayPlayerStats.game_id == Game.id)
                  .filter(Game.team_organization_id == team_id).all())
    for season in seasons:
        if season.is_current:
            played.update((season.id, pid) for pid, p in players.items() if p.active)

    for season_id, player_id in sorted(played, key=lambda pair: (pair[0] or 0, pair[1] or 0)):
        player = players.get(player_id)
        if season_id is None or player is None or (season_id, player_id) in have:
            continue
        db.session.add(SeasonRoster(team_organization_id=team_id, season_id=season_id, player_id=player_id,
                                    jersey_number=_shirt(player.jersey_number), position=player.position,
                                    joined_date=player.joined_team_date,
                                    status='active' if player.active else 'left'))
        have.add((season_id, player_id))
    db.session.flush()


def sync_active_flags(team_id):
    """Player.active = on the current season's roster and hasn't left."""
    from app.models.player import Player

    current = Season.query.filter_by(team_organization_id=team_id, is_current=True).first()
    if current is None:
        return
    on_team = {r.player_id for r in current.roster if r.on_team}
    for player in Player.query.filter_by(team_organization_id=team_id):
        player.active = player.id in on_team
    db.session.flush()


def set_current(season):
    """Make `season` the team's current season (the caller commits)."""
    Season.query.filter(Season.team_organization_id == season.team_organization_id,
                        Season.id != season.id, Season.is_current.is_(True)).update(
        {Season.is_current: False}, synchronize_session='fetch')
    db.session.flush()
    season.is_current = True
    db.session.flush()
    sync_active_flags(season.team_organization_id)
    forget_cached()


def get_or_create_season(team_id, year, start_date=None, end_date=None):
    season = Season.query.filter_by(team_organization_id=team_id, year=year).first()
    if season is None:
        default_start, default_end = Season.default_dates(year)
        season = Season(team_organization_id=team_id, year=year,
                        start_date=start_date or default_start, end_date=end_date or default_end)
        db.session.add(season)
        db.session.flush()
        assign_unseasoned(team_id)
    else:
        if start_date:
            season.start_date = start_date
        if end_date:
            season.end_date = end_date
    forget_cached()
    return season


def start_new_season(team_id, year, start_date, end_date, entries, previous=None, left_date=None):
    """Start (or move on to) the season for `year` and make it current.

    `entries` is a list of dicts (player_id, squad_id, jersey_number,
    position) for the players on the new roster. Everyone on `previous`'s
    roster who isn't in `entries` is marked as having left it. Games,
    tournaments, sessions and old rosters are left alone. The caller commits.
    """
    season = get_or_create_season(team_id, year, start_date, end_date)
    existing = {r.player_id: r for r in season.roster}
    keep = set()
    for entry in entries:
        pid = entry['player_id']
        keep.add(pid)
        row = existing.get(pid)
        if row is None:
            row = SeasonRoster(team_organization_id=team_id, season_id=season.id, player_id=pid,
                               joined_date=season.start_date)
            db.session.add(row)
        row.squad_id = entry.get('squad_id')
        row.jersey_number = entry.get('jersey_number')
        row.position = entry.get('position')
        row.status = 'active' if row.status == 'left' else (row.status or 'active')
        row.left_date = None

    if previous is not None and previous.id != season.id:
        for row in previous.roster:
            if row.player_id not in keep and row.status != 'left':
                row.status = 'left'
                row.left_date = left_date or previous.end_date
    db.session.flush()
    _copy_roster_to_players(season, keep)
    set_current(season)
    return season


def _copy_roster_to_players(season, player_ids):
    """The new season's shirt number and position become the player's."""
    for row in season.roster:
        if row.player_id in player_ids and row.player:
            if row.jersey_number is not None:
                row.player.jersey_number = row.jersey_number
            if row.position:
                row.player.position = row.position


def _shirt(value):
    try:
        return int(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


# ── What the user is viewing ───────────────────────────────────────────────

def viewing_season(team_id=None):
    """The season pages show: ?season=<year|all>, else the user's choice
    from the switcher, else the current season. None means all time."""
    from app.utils.team_filter import get_current_team_id

    team_id = team_id or get_current_team_id()
    seasons = team_seasons(team_id)
    if not seasons:
        return None
    choice = request.args.get('season') if has_request_context() else None
    if not choice and has_request_context():
        choice = (flask_session.get('view_season') or {}).get(str(team_id))
    if choice == ALL:
        return None
    # Only a plain year: the sessions page uses ?season= for plan labels like 2027/28
    year = int(choice) if choice and str(choice).isdigit() else None
    return next((s for s in seasons if s.year == year), None) or current_season(team_id)


def viewing_squad(team_id=None):
    """The squad pages are narrowed to, or None for the whole club."""
    from app.utils.team_filter import get_current_team_id

    team_id = team_id or get_current_team_id()
    squads = team_squads(team_id)
    if not squads or not has_request_context():
        return None
    choice = request.args.get('squad')
    if not (choice and choice.isdigit()) and choice != ALL:  # the sessions page's ?squad=1s is something else
        choice = (flask_session.get('view_squad') or {}).get(str(team_id))
    if not choice or choice == ALL:
        return None
    return next((s for s in squads if str(s.id) == str(choice)), None)


def remember_view(team_id, season=None, squad=None):
    """Keep the switcher's choice for this team in the user's session."""
    if season is not None:
        flask_session['view_season'] = {**(flask_session.get('view_season') or {}), str(team_id): str(season)}
    if squad is not None:
        flask_session['view_squad'] = {**(flask_session.get('view_squad') or {}), str(team_id): str(squad)}


def scope_games(query, team_id=None):
    from app.models.game import Game

    season, squad = viewing_season(team_id), viewing_squad(team_id)
    if season is not None:
        query = query.filter(Game.season_id == season.id)
    if squad is not None:
        query = query.filter(Game.squad_id == squad.id)
    return query


def scope_tournaments(query, team_id=None):
    from app.models.tournament import Tournament

    season, squad = viewing_season(team_id), viewing_squad(team_id)
    if season is not None:
        query = query.filter(Tournament.season_id == season.id)
    if squad is not None:
        query = query.filter(Tournament.squad_id == squad.id)
    return query


def scope_sessions(query, team_id=None):
    from app.models.session import SessionPlan

    season = viewing_season(team_id)
    if season is not None:
        query = query.filter(SessionPlan.season_id == season.id)
    return query


def roster_rows(season, squad=None):
    if season is None:
        return []
    query = season.roster
    if squad is not None:
        query = query.filter(SeasonRoster.squad_id == squad.id)
    return query.all()


def season_players(team_id=None):
    """Players for the season and squad being viewed (everyone on its
    roster, including those who left during it). All time: every player.
    A season with no roster yet falls back to the active players."""
    from app.models.player import Player
    from app.utils.team_filter import get_current_team_id

    team_id = team_id or get_current_team_id()
    season, squad = viewing_season(team_id), viewing_squad(team_id)
    if season is None:
        query = Player.query.filter_by(team_organization_id=team_id)
        if squad is not None:
            query = query.filter(Player.id.in_(db.session.query(SeasonRoster.player_id)
                                               .filter(SeasonRoster.squad_id == squad.id)))
        return query.all()
    rows = roster_rows(season, squad)
    if not rows and squad is None:
        return Player.query.filter_by(team_organization_id=team_id, active=True).all()
    return [r.player for r in rows]


def season_context():
    """For templates: the switcher's options and what is being viewed."""
    from app.utils.team_filter import get_current_team_id

    team_id = get_current_team_id()
    if not team_id:
        return {}
    seasons = team_seasons(team_id)
    return {
        'seasons': seasons,
        'current_season': current_season(team_id),
        'viewing_season': viewing_season(team_id),
        'squads': team_squads(team_id),
        'viewing_squad': viewing_squad(team_id),
    }


# ── New rows go into a season ──────────────────────────────────────────────

@event.listens_for(OrmSession, 'before_flush')
def _fill_seasons(session, flush_context, instances):
    """New (or re-dated) games, tournaments and sessions go into the season
    their date is in, making that year's season if needed. Teams without
    seasons yet are left for ensure_seasons()."""
    from app.models.game import Game
    from app.models.session import SessionPlan
    from app.models.tournament import Tournament

    _add_new_players_to_roster(session)
    rows = [o for o in list(session.new) + list(session.dirty)
            if isinstance(o, (Game, Tournament, SessionPlan)) and o.team_organization_id]
    if not rows:
        return
    made = {}
    with session.no_autoflush:
        # Tournaments first so their games can follow them
        for obj in sorted(rows, key=lambda o: not isinstance(o, Tournament)):
            if obj in session.new:
                if obj.season_id is not None or getattr(obj, _SEASON_REL[type(obj).__name__]) is not None:
                    continue
            elif not _redated(obj):
                continue
            seasons = (session.query(Season).filter_by(team_organization_id=obj.team_organization_id).all()
                       + [s for (team, _), s in made.items() if team == obj.team_organization_id])
            if not seasons:
                continue
            season = _season_for_row(session, obj, seasons, made)
            if season is not None:
                _set_season(obj, season)
                if isinstance(obj, Tournament) and not obj.season:
                    obj.season = season.name
            tournament = _game_tournament(session, obj) if isinstance(obj, Game) else None
            if tournament is not None and obj.squad_id is None:
                obj.squad_id = tournament.squad_id


def _add_new_players_to_roster(session):
    """However a player is added (form, import, sign-up link), an active
    one goes on the current season's roster so they stay active."""
    from app.models.player import Player

    new_players = [o for o in session.new if isinstance(o, Player) and o.active and o.team_organization_id]
    if not new_players:
        return
    listed = {id(o.player) for o in session.new if isinstance(o, SeasonRoster) and o.player is not None}
    with session.no_autoflush:
        for player in new_players:
            if id(player) in listed:
                continue
            current = (session.query(Season)
                       .filter_by(team_organization_id=player.team_organization_id, is_current=True).first())
            if current is not None:
                session.add(SeasonRoster(team_organization_id=player.team_organization_id, season=current,
                                         player=player, jersey_number=_shirt(player.jersey_number),
                                         position=player.position, joined_date=date.today()))


_SEASON_REL = {'Game': 'season', 'Tournament': 'season_obj', 'SessionPlan': 'club_season'}


def _set_season(obj, season):
    """Through the relationship, so a season made in this flush works too."""
    from app.models.game import Game
    from app.models.tournament import Tournament

    if isinstance(obj, Game):
        obj.season = season
    elif isinstance(obj, Tournament):
        obj.season_obj = season
    else:
        obj.club_season = season


def _redated(obj):
    from app.models.game import Game
    from app.models.session import SessionPlan

    state = inspect(obj)
    if (state.attrs.season_id.history.has_changes()
            or state.attrs[_SEASON_REL[type(obj).__name__]].history.has_changes()):
        return False  # the season was picked
    if isinstance(obj, Game):
        return state.attrs.date.history.has_changes() or state.attrs.tournament_id.history.has_changes()
    if isinstance(obj, SessionPlan):
        return state.attrs.date.history.has_changes()
    return state.attrs.start_date.history.has_changes()


def _game_tournament(session, game):
    """The game's tournament, also when only tournament_id was set (a new
    game's relationship isn't loaded from its id until after the flush)."""
    from app.models.tournament import Tournament

    if game.tournament is not None:
        return game.tournament
    if game.tournament_id:
        return session.get(Tournament, game.tournament_id)
    return None


def _season_for_row(session, obj, seasons, made):
    from app.models.game import Game
    from app.models.tournament import Tournament

    current = next((s for s in seasons if s.is_current), None)
    if isinstance(obj, Game):
        day = obj.date
        tournament = _game_tournament(session, obj)
        if tournament is not None:
            # A tournament's games are in its season, whatever their own dates
            linked = tournament.season_obj or next(
                (s for s in seasons if s.id is not None and s.id == tournament.season_id), None)
            if linked is not None:
                return linked
            day = day or tournament.start_date
    elif isinstance(obj, Tournament):
        day = obj.start_date
        if day is None:
            year = label_year(obj.season)
            return next((s for s in seasons if s.year == year), None) or current
    else:
        day = obj.date
    if day is None:
        return current
    found = season_for_date(obj.team_organization_id, day, seasons)
    if found is None:
        start, end = Season.default_dates(day.year)
        found = Season(team_organization_id=obj.team_organization_id, year=day.year,
                       start_date=start, end_date=end, is_current=False)
        session.add(found)
        made[(obj.team_organization_id, day.year)] = found
    return found


# ── One player's roster entries ────────────────────────────────────────────

def roster_entry(player, season):
    if season is None or player is None or player.id is None:
        return None
    return SeasonRoster.query.filter_by(season_id=season.id, player_id=player.id).first()


def put_on_roster(player, season, squad_id=None, jersey_number=None, position=None, on_team=True):
    """Add or update the player's entry for `season`; for the current season
    also keep player.active in step. The caller commits."""
    row = roster_entry(player, season)
    if row is None:
        row = SeasonRoster(team_organization_id=season.team_organization_id, season_id=season.id,
                           player=player, joined_date=date.today() if season.is_current else season.start_date)
        db.session.add(row)
    row.squad_id = squad_id
    row.jersey_number = _shirt(jersey_number)
    row.position = position or None
    if on_team and row.status == 'left':
        row.status, row.left_date = 'active', None
    elif not on_team and row.status != 'left':
        row.status, row.left_date = 'left', date.today() if season.is_current else season.end_date
    if season.is_current:
        player.active = on_team
    return row


def player_seasons(player):
    """One row per season the player was on the roster or played in:
    squad, shirt, status, games and points. Newest first."""
    from app.models.game import Game
    from app.models.gameday import GameDayPlayerStats
    from app.models.point import LineUp, Point

    entries = {r.season_id: r for r in player.season_entries}
    games, points = {}, {}
    for season_id, game_id, count in (db.session.query(Game.season_id, Game.id, db.func.count(LineUp.id))
                                      .join(Point, Point.game_id == Game.id).join(LineUp, LineUp.point_id == Point.id)
                                      .filter(LineUp.player_id == player.id).group_by(Game.season_id, Game.id)):
        games.setdefault(season_id, set()).add(game_id)
        points[season_id] = points.get(season_id, 0) + count
    for season_id, game_id, count in (db.session.query(Game.season_id, Game.id, GameDayPlayerStats.points_played)
                                      .join(GameDayPlayerStats, GameDayPlayerStats.game_id == Game.id)
                                      .filter(GameDayPlayerStats.player_id == player.id)):
        if game_id not in games.get(season_id, set()):  # Game Day-only games
            points[season_id] = points.get(season_id, 0) + (count or 0)
        games.setdefault(season_id, set()).add(game_id)

    rows = []
    for season in Season.query.filter(Season.id.in_(set(entries) | {k for k in games if k})).order_by(Season.year.desc()):
        entry = entries.get(season.id)
        rows.append({'season': season, 'entry': entry,
                     'games': len(games.get(season.id, ())), 'points': points.get(season.id, 0)})
    return rows
