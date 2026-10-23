# app/routes/seasons.py
"""Seasons and squads: the season switcher, starting a new season, and
editing any season's dates and roster (past seasons stay editable)."""
from datetime import date, datetime
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.game import Game
from app.models.player import Player
from app.models.season import Season, SeasonRoster, Squad
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from app.utils import season as seasons
from app.utils.team_filter import get_current_team_id
from app.utils.utils import coach_required

bp = Blueprint('seasons', __name__, url_prefix='/team/seasons')


def _safe_next(default):
    target = request.values.get('next') or request.referrer or ''
    parsed = urlparse(target)
    if parsed.netloc and parsed.netloc != request.host:
        return default
    path = parsed.path or ''
    if not path.startswith('/') or path.startswith(('//', '/\\')):
        return default
    return path + (f'?{parsed.query}' if parsed.query else '')


def _strip_view_args(url):
    """Drop ?season= / ?squad= so the remembered choice takes over."""
    parsed = urlparse(url)
    query = '&'.join(part for part in parsed.query.split('&')
                     if part and not part.startswith(('season=', 'squad=')))
    return parsed.path + (f'?{query}' if query else '')


def _team_season_or_404(season_id):
    return Season.query.filter_by(id=season_id, team_organization_id=get_current_team_id()).first_or_404()


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date() if value else None
    except ValueError:
        return None


def _int_or_none(value):
    try:
        return int(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _squad_id(team_id, value):
    squad_id = _int_or_none(value)
    if squad_id and Squad.query.filter_by(id=squad_id, team_organization_id=team_id).first():
        return squad_id
    return None


@bp.route('/view')
@login_required
def view():
    """The season switcher: remember which season (and squad) to show."""
    team_id = get_current_team_id()
    if not team_id:
        abort(404)
    season = request.args.get('season')
    squad = request.args.get('squad')
    if season is not None:
        known = {str(s.year) for s in seasons.team_seasons(team_id)}
        seasons.remember_view(team_id, season=season if season in known or season == seasons.ALL else '')
    if squad is not None:
        known = {str(s.id) for s in seasons.team_squads(team_id)}
        seasons.remember_view(team_id, squad=squad if squad in known or squad == seasons.ALL else '')
    return redirect(_strip_view_args(_safe_next(url_for('main.index'))))


@bp.route('/')
@login_required
@coach_required
def index():
    team_id = get_current_team_id()
    all_seasons = seasons.team_seasons(team_id)
    counts = {}
    for s in all_seasons:
        counts[s.id] = {
            'games': Game.query.filter_by(season_id=s.id).count(),
            'tournaments': Tournament.query.filter_by(season_id=s.id).count(),
            'sessions': SessionPlan.query.filter_by(season_id=s.id).count(),
            'players': s.roster.filter(SeasonRoster.status != 'left').count(),
            'left': s.roster.filter(SeasonRoster.status == 'left').count(),
        }
    return render_template('seasons/index.html', all_seasons=all_seasons, counts=counts,
                           squads=seasons.team_squads(team_id), next_year=_next_year(all_seasons))


def _next_year(all_seasons):
    current = next((s for s in all_seasons if s.is_current), None)
    return (current.year + 1) if current else date.today().year


@bp.route('/<int:season_id>/edit', methods=['POST'])
@login_required
@coach_required
def edit(season_id):
    season = _team_season_or_404(season_id)
    start, end = _parse_date(request.form.get('start_date')), _parse_date(request.form.get('end_date'))
    if not start or not end or start > end:
        flash('Give a start date on or before the end date.', 'danger')
        return redirect(url_for('seasons.index'))
    season.start_date, season.end_date = start, end
    db.session.commit()
    flash(f'{season.name} season dates saved.', 'success')
    return redirect(url_for('seasons.index'))


@bp.route('/<int:season_id>/current', methods=['POST'])
@login_required
@coach_required
def make_current(season_id):
    season = _team_season_or_404(season_id)
    seasons.set_current(season)
    db.session.commit()
    flash(f'{season.name} is now the current season.', 'success')
    return redirect(url_for('seasons.index'))


@bp.route('/add', methods=['POST'])
@login_required
@coach_required
def add():
    """Add a season (e.g. an earlier year to record old results in)."""
    team_id = get_current_team_id()
    year = _int_or_none(request.form.get('year'))
    if not year or not 1900 <= year <= 2200:
        flash('Give a year, e.g. 2025.', 'danger')
        return redirect(url_for('seasons.index'))
    if Season.query.filter_by(team_organization_id=team_id, year=year).first():
        flash(f'There is already a {year} season.', 'warning')
        return redirect(url_for('seasons.index'))
    seasons.get_or_create_season(team_id, year)
    db.session.commit()
    flash(f'{year} season added.', 'success')
    return redirect(url_for('seasons.index'))


@bp.route('/<int:season_id>/delete', methods=['POST'])
@login_required
@coach_required
def delete(season_id):
    """Only an empty season can go: no games, tournaments or sessions."""
    season = _team_season_or_404(season_id)
    if season.is_current:
        flash("The current season can't be deleted.", 'danger')
    elif (Game.query.filter_by(season_id=season.id).first() or Tournament.query.filter_by(season_id=season.id).first()
          or SessionPlan.query.filter_by(season_id=season.id).first()):
        flash(f'{season.name} has games, tournaments or sessions in it, so it stays.', 'danger')
    else:
        db.session.delete(season)
        db.session.commit()
        flash(f'{season.name} season deleted.', 'success')
    return redirect(url_for('seasons.index'))


@bp.route('/new', methods=['GET', 'POST'])
@login_required
@coach_required
def new():
    """Start a new season: pick who carries on, and their squad and shirt."""
    team_id = get_current_team_id()
    previous = seasons.current_season(team_id)
    squads = seasons.team_squads(team_id)
    year = _int_or_none(request.values.get('year')) or _next_year(seasons.team_seasons(team_id))
    default_start, default_end = Season.default_dates(year)

    if request.method == 'POST':
        start = _parse_date(request.form.get('start_date')) or default_start
        end = _parse_date(request.form.get('end_date')) or default_end
        if start > end:
            flash('The start date has to be on or before the end date.', 'danger')
            return redirect(url_for('seasons.new', year=year))
        team_players = {p.id: p for p in Player.query.filter_by(team_organization_id=team_id)}
        entries = []
        for pid in request.form.getlist('player_id'):
            player = team_players.get(_int_or_none(pid))
            if player is None:
                continue
            entries.append({
                'player_id': player.id,
                'squad_id': _squad_id(team_id, request.form.get(f'squad_{player.id}')),
                'jersey_number': _int_or_none(request.form.get(f'jersey_{player.id}')),
                'position': request.form.get(f'position_{player.id}') or player.position,
            })
        season = seasons.start_new_season(team_id, year, start, end, entries, previous=previous)
        db.session.commit()
        seasons.remember_view(team_id, season=str(season.year))
        flash(f'The {season.name} season has started with {len(entries)} players. '
              f'Earlier seasons are kept and can be picked from the season menu.', 'success')
        return redirect(url_for('seasons.roster', season_id=season.id))

    # Last season's roster first (ticked), then everyone else (unticked)
    rows, seen = [], set()
    if previous is not None:
        for entry in previous.roster.join(Player).order_by(Player.name):
            rows.append({'player': entry.player, 'entry': entry, 'checked': entry.on_team})
            seen.add(entry.player_id)
    for player in Player.query.filter_by(team_organization_id=team_id).order_by(Player.name):
        if player.id not in seen:
            rows.append({'player': player, 'entry': None, 'checked': previous is None and player.active})
    return render_template('seasons/new.html', rows=rows, squads=squads, previous=previous, year=year,
                           start_date=default_start, end_date=default_end,
                           existing=Season.query.filter_by(team_organization_id=team_id, year=year).first())


@bp.route('/<int:season_id>/roster', methods=['GET', 'POST'])
@login_required
@coach_required
def roster(season_id):
    """Edit one season's roster: squad, shirt, position, status."""
    team_id = get_current_team_id()
    season = _team_season_or_404(season_id)
    squads = seasons.team_squads(team_id)

    if request.method == 'POST':
        rows = {r.id: r for r in season.roster}
        for row_id, row in rows.items():
            if request.form.get(f'remove_{row_id}'):
                db.session.delete(row)
                continue
            row.squad_id = _squad_id(team_id, request.form.get(f'squad_{row_id}'))
            row.jersey_number = _int_or_none(request.form.get(f'jersey_{row_id}'))
            row.position = request.form.get(f'position_{row_id}') or None
            status = request.form.get(f'status_{row_id}', row.status)
            if status in dict(SeasonRoster.STATUSES):
                if status == 'left' and row.status != 'left':
                    row.left_date = date.today() if season.is_current else season.end_date
                elif status != 'left':
                    row.left_date = None
                row.status = status
        for pid in request.form.getlist('add_player_id'):
            player = Player.query.filter_by(id=_int_or_none(pid), team_organization_id=team_id).first()
            if player and not seasons.roster_entry(player, season):
                seasons.put_on_roster(player, season, _squad_id(team_id, request.form.get('add_squad_id')),
                                      player.jersey_number, player.position)
        db.session.flush()
        if season.is_current:
            seasons.sync_active_flags(team_id)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('That player is already on this roster.', 'warning')
        else:
            flash(f'{season.name} roster saved.', 'success')
        return redirect(url_for('seasons.roster', season_id=season.id))

    entries = season.roster.join(Player).order_by(Player.name).all()
    on_roster = {e.player_id for e in entries}
    others = [p for p in Player.query.filter_by(team_organization_id=team_id).order_by(Player.name)
              if p.id not in on_roster]
    return render_template('seasons/roster.html', season=season, entries=entries, others=others,
                           squads=squads, statuses=SeasonRoster.STATUSES)


# ── Squads ─────────────────────────────────────────────────────────────────

@bp.route('/squads/add', methods=['POST'])
@login_required
@coach_required
def add_squad():
    team_id = get_current_team_id()
    name = (request.form.get('name') or '').strip()[:50]
    if not name:
        flash('Give the squad a name, e.g. 1s.', 'danger')
    elif Squad.query.filter(Squad.team_organization_id == team_id,
                            db.func.lower(Squad.name) == name.lower()).first():
        flash(f'There is already a squad called {name}.', 'warning')
    else:
        last = db.session.query(db.func.max(Squad.sort_order)).filter_by(team_organization_id=team_id).scalar()
        db.session.add(Squad(team_organization_id=team_id, name=name, sort_order=(last or 0) + 1))
        db.session.commit()
        flash(f'Squad {name} added. Put players in it from a season roster.', 'success')
    return redirect(url_for('seasons.index'))


@bp.route('/squads/<int:squad_id>/edit', methods=['POST'])
@login_required
@coach_required
def edit_squad(squad_id):
    squad = Squad.query.filter_by(id=squad_id, team_organization_id=get_current_team_id()).first_or_404()
    name = (request.form.get('name') or '').strip()[:50]
    if name:
        squad.name = name
        try:
            db.session.commit()
            flash('Squad renamed.', 'success')
        except IntegrityError:
            db.session.rollback()
            flash(f'There is already a squad called {name}.', 'warning')
    return redirect(url_for('seasons.index'))


@bp.route('/squads/<int:squad_id>/delete', methods=['POST'])
@login_required
@coach_required
def delete_squad(squad_id):
    """Players, games and tournaments in it stay, just without a squad."""
    team_id = get_current_team_id()
    squad = Squad.query.filter_by(id=squad_id, team_organization_id=team_id).first_or_404()
    for model in (SeasonRoster, Game, Tournament):
        model.query.filter_by(squad_id=squad.id).update({model.squad_id: None}, synchronize_session=False)
    db.session.delete(squad)
    db.session.commit()
    flash(f'Squad {squad.name} deleted. Its players, games and tournaments are kept.', 'success')
    return redirect(url_for('seasons.index'))


@bp.app_template_global()
def season_switch_url(**kwargs):
    """Link for the season switcher that comes back to the current page."""
    if not current_user.is_authenticated:
        return '#'
    return url_for('seasons.view', next=request.full_path.rstrip('?'), **kwargs)
