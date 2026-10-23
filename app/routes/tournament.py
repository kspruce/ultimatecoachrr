# app/routes/tournament.py
"""Tournaments: one page per tournament with three tabs.

- Overview: dates, notes, games; a player sees whether they're going and
  answers with one tap.
- Squad (coaches): everyone it's for, their answer, and the coach's pick,
  saved as each box is ticked.
- Games: the schedule, and (for coaches) a players x games grid.
"""
import logging
from datetime import date, datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import text
from app import db
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.player import Player
from app.forms.tournament import TournamentForm, TournamentFilterForm
from app.forms.rsvp_form import RSVPForm
from app.utils.utils import coach_required
from app.utils import event_notify
from app.utils import rsvp as rsvps
from app.utils.schedule_parse import parse_schedule
from app.utils.team_filter import get_current_team_id, team_player_ids, team_row_or_404
from app.utils.season import (current_season, get_or_create_season, label_year, scope_tournaments, season_for_date,
                              team_seasons, team_squads, viewing_season, viewing_squad)

bp = Blueprint('tournament', __name__, url_prefix='/tournaments')
logger = logging.getLogger(__name__)

TABS = ('overview', 'squad', 'games')


@bp.route('/')
@login_required
def index():
    form = TournamentFilterForm()
    delete_form = FlaskForm()  # Add this for CSRF protection
    
    # The season (and squad) being viewed, or ?season=<year|all>
    team_id = get_current_team_id()
    form.season.choices = [('all', 'All time')] + [(str(s.year), s.name) for s in team_seasons(team_id)]
    season = viewing_season(team_id)
    form.season.data = str(season.year) if season else 'all'

    query = scope_tournaments(Tournament.query.filter_by(team_organization_id=team_id), team_id)

    # Get tournaments and sort by start date (most recent first)
    tournaments = query.order_by(Tournament.start_date.desc()).all()

    my_rsvps = {}
    if current_user.player:
        my_rsvps = {r.tournament_id: r for r in TournamentRSVP.query.filter_by(player_id=current_user.player.id)}

    return render_template('tournament/index.html', 
                         tournaments=tournaments, 
                         form=form,
                         delete_form=delete_form,
                         my_rsvps=my_rsvps,
                         today=date.today())

def _season_choices(form):
    team_id = get_current_team_id()
    form.season.choices = [('', 'From the start date')] + [(str(s.year), s.name) for s in team_seasons(team_id)]
    form.squad_id.choices = [('', 'Whole club')] + [(str(s.id), s.name) for s in team_squads(team_id)]


def _apply_season(form, tournament):
    """The picked season (made if it's a new year), else the one the start
    date is in; the tournament's games move with it."""
    team_id = get_current_team_id()
    year = label_year(form.season.data)
    season = None
    if year:
        season = get_or_create_season(team_id, year)
    elif tournament.start_date and team_seasons(team_id):
        season = season_for_date(team_id, tournament.start_date) or get_or_create_season(
            team_id, tournament.start_date.year)
    if season is not None:
        tournament.season_obj = season
        tournament.season = season.name
    squad_id = next((s.id for s in team_squads(team_id) if str(s.id) == (form.squad_id.data or '')), None)
    tournament.squad_id = squad_id
    if tournament.id is not None:
        for game in tournament.games:
            if season is not None:
                game.season = season
            game.squad_id = squad_id


def _fill_from_form(form, tournament):
    tournament.name = form.name.data
    tournament.start_date = form.start_date.data
    tournament.end_date = form.end_date.data
    tournament.location = form.location.data
    tournament.rsvp_deadline = form.rsvp_deadline.data
    tournament.squad_size_target = form.squad_size_target.data
    tournament.notes = (form.notes.data or '').strip() or None
    _apply_season(form, tournament)


def _parse_day(value):
    try:
        return datetime.strptime(value or '', '%Y-%m-%d').date()
    except ValueError:
        return None


def _hub_context(tournament):
    """Everything the tournament page needs, for players and coaches."""
    games = (tournament.games.order_by(Game.date.is_(None), Game.date, Game.start_time.is_(None),
                                       Game.start_time, Game.id).all())
    ctx = {'tournament': tournament, 'games': games, 'delete_form': FlaskForm()}

    player = current_user.player
    player_rsvp = None
    if player:
        player_rsvp = TournamentRSVP.query.filter_by(tournament_id=tournament.id, player_id=player.id).first()
        ctx['my_games'] = rsvps.player_games(tournament, player)
    ctx['player_rsvp'] = player_rsvp
    ctx['my_selection'] = rsvps.player_selection(tournament, player_rsvp)
    ctx['rsvp_form'] = RSVPForm(obj=player_rsvp)

    rows = rsvps.squad_rows(tournament)
    ctx['summary'] = rsvps.squad_summary(tournament, rows)
    if current_user.is_coach:
        ctx['rows'] = rows
        ctx['picked'] = rsvps.picked_players(tournament)
        game_ids = [g.id for g in games]
        assigned = {}
        for gp in (GamePlayer.query.filter(GamePlayer.game_id.in_(game_ids)).all() if game_ids else []):
            assigned.setdefault(gp.game_id, set()).add(gp.player_id)
        ctx['assigned'] = assigned
    return ctx


@bp.route('/<int:tournament_id>')
@login_required
def detail(tournament_id):
    tournament = team_row_or_404(Tournament, tournament_id)
    tab = request.args.get('tab', 'overview')
    if tab not in TABS or (tab == 'squad' and not current_user.is_coach):
        tab = 'overview'
    return render_template('tournament/detail.html', tab=tab, **_hub_context(tournament))

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@coach_required
def add():
    form = TournamentForm()
    _season_choices(form)
    team_id = get_current_team_id()
    copy_from = None
    if request.method == 'GET':
        current = current_season(team_id)
        form.season.data = str(current.year) if current else ''
        squad = viewing_squad()
        form.squad_id.data = str(squad.id) if squad else ''
        # "Copy from" a previous tournament: same place, squad, notes and size
        copy_id = request.args.get('copy', type=int)
        copy_from = (Tournament.query.filter_by(id=copy_id, team_organization_id=team_id).first()
                     if copy_id else None)
        if copy_from:
            form.name.data = copy_from.name
            form.location.data = copy_from.location
            form.notes.data = copy_from.notes
            form.squad_size_target.data = copy_from.squad_size_target
            form.squad_id.data = str(copy_from.squad_id or '')
        day = _parse_day(request.args.get('date'))
        if day:
            form.start_date.data = form.end_date.data = day
    if form.validate_on_submit():
        tournament = Tournament(team_organization_id=team_id)
        _fill_from_form(form, tournament)
        
        try:
            db.session.add(tournament)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding tournament: {str(e)}', 'danger')
        else:
            message = f'Tournament {tournament.name} has been added!'
            if form.ask_players.data:
                sent = event_notify.ask_for_availability(tournament)
                if sent:
                    message += f' {sent} player{"s" if sent != 1 else ""} emailed to ask if they can make it.'
            flash(message, 'success')
            return redirect(url_for('tournament.detail', tournament_id=tournament.id))

    previous = (Tournament.query.filter_by(team_organization_id=team_id)
                .order_by(Tournament.start_date.desc().nullslast(), Tournament.id.desc()).limit(10).all())
    return render_template('tournament/form.html', form=form, title='Add Tournament', show_ask=True,
                           copy_from=copy_from, previous=previous)


@bp.route('/edit/<int:tournament_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit(tournament_id):
    tournament = team_row_or_404(Tournament, tournament_id)

    form = TournamentForm(obj=tournament)
    _season_choices(form)
    if request.method == 'GET':
        form.season.data = str(tournament.season_obj.year) if tournament.season_obj else ''
        form.squad_id.data = str(tournament.squad_id or '')

    if form.validate_on_submit():
        old_deadline = tournament.rsvp_deadline
        _fill_from_form(form, tournament)
        if tournament.rsvp_deadline != old_deadline:
            tournament.reminder_sent_at = None  # a new reply-by date gets its own reminder
        
        db.session.commit()
        flash(f'Tournament {tournament.name} has been updated!', 'success')
        return redirect(url_for('tournament.detail', tournament_id=tournament.id))
    
    return render_template('tournament/form.html', form=form, title='Edit Tournament', show_ask=False)

@bp.route('/delete/<int:tournament_id>', methods=['POST'])
@login_required
@coach_required
def delete(tournament_id):
    try:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        name = tournament.name

        # Delete all related data for each game in the tournament
        for game in tournament.games:
            # Delete throws associated with events in each point
            for point in game.points:
                # Delete throws
                db.session.execute(
                    text("DELETE FROM throw WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )
                
                # Delete player point stats
                db.session.execute(
                    text("DELETE FROM player_point_stats WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )

                # Delete events
                db.session.execute(
                    text("DELETE FROM event WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )
                
                # Delete pulls
                db.session.execute(
                    text("DELETE FROM pull WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )
                
                # Delete lineups
                db.session.execute(
                    text("DELETE FROM line_up WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )

            # Delete points
            db.session.execute(
                text("DELETE FROM point WHERE game_id = :game_id"),
                {"game_id": game.id}
            )

            # Delete clips if any
            if hasattr(game, 'clips'):
                for clip in game.clips:
                    # Delete clip tags
                    db.session.execute(
                        text("DELETE FROM clip_tag_relation WHERE clip_id = :clip_id"),
                        {"clip_id": clip.id}
                    )
                    # Delete clip players
                    db.session.execute(
                        text("DELETE FROM clip_player WHERE clip_id = :clip_id"),
                        {"clip_id": clip.id}
                    )
                # Delete clips
                db.session.execute(
                    text("DELETE FROM clip WHERE game_id = :game_id"),
                    {"game_id": game.id}
                )

            # Delete the game
            db.session.delete(game)

        # Delete all RSVPs
        TournamentRSVP.query.filter_by(tournament_id=tournament_id).delete()
        
        # Finally delete the tournament
        db.session.delete(tournament)
        db.session.commit()
        
        flash(f'Tournament {name} and all associated data has been deleted!', 'success')
        return redirect(url_for('tournament.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting tournament: {str(e)}', 'danger')
        return redirect(url_for('tournament.index'))


# ── Players answering ──────────────────────────────────────────────────────

@bp.route('/<int:tournament_id>/rsvp', methods=['GET', 'POST'])
@login_required
def rsvp(tournament_id):
    """The player's own answer: JSON (one-tap buttons) or a plain form."""
    tournament = team_row_or_404(Tournament, tournament_id)

    if not current_user.player:
        if request.is_json:
            return jsonify({'success': False, 'message': 'You need to link your account to a player first.'}), 403
        flash('You need to link your account to a player before you can RSVP.', 'warning')
        return redirect(url_for('auth.link_player'))

    if request.method == 'GET':
        return redirect(url_for('tournament.detail', tournament_id=tournament.id))

    if request.is_json:
        data = request.get_json(silent=True) or {}
        status, notes = data.get('status'), data.get('notes')
    else:
        status, notes = request.form.get('status'), request.form.get('notes')
    try:
        answer = rsvps.set_tournament_rsvp(tournament, current_user.player, status, notes)
        db.session.commit()
    except rsvps.RSVPError as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(str(e), 'danger')
    else:
        message = f'Thanks: you\'re down as "{answer.status_label}".'
        if answer.is_late:
            message += ' The reply-by date has passed, so the coaches will see it as a late reply.'
        if request.is_json:
            return jsonify({'success': True, 'message': message, 'status': answer.status,
                            'late': answer.is_late})
        flash(message, 'success')
    return redirect(url_for('tournament.detail', tournament_id=tournament.id))


# ── Coaches: the squad ─────────────────────────────────────────────────────

def _team_player_or_404(player_id):
    return Player.query.filter_by(id=player_id, team_organization_id=get_current_team_id()).first_or_404()


@bp.route('/<int:tournament_id>/selection', methods=['POST'])
@login_required
@coach_required
def set_selection(tournament_id):
    """Pick / reserve / not pick one player (saved straight away)."""
    tournament = team_row_or_404(Tournament, tournament_id)
    data = request.get_json(silent=True) or request.form
    player = _team_player_or_404(_int(data.get('player_id')))
    selection = data.get('selection') or None
    try:
        answer = rsvps.set_selection(tournament, player, selection)
        db.session.commit()
    except rsvps.RSVPError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    summary = rsvps.squad_summary(tournament)
    warning = None
    if selection == 'picked' and answer and answer.status == 'not_attending':
        warning = f'{player.name} said they can\'t make it.'
    return jsonify({'success': True, 'summary': summary, 'warning': warning})


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@bp.route('/<int:tournament_id>/publish', methods=['POST'])
@login_required
@coach_required
def publish_selection(tournament_id):
    """Show players whether they're picked, and tell them."""
    tournament = team_row_or_404(Tournament, tournament_id)
    if request.form.get('unpublish'):
        tournament.selection_published = False
        db.session.commit()
        flash('Selection hidden from players again.', 'info')
    else:
        tournament.selection_published = True
        db.session.commit()
        sent = event_notify.announce_selection(tournament)
        flash(f'Squad published.{f" {sent} players emailed." if sent else ""}', 'success')
    return redirect(url_for('tournament.detail', tournament_id=tournament.id, tab='squad'))


@bp.route('/<int:tournament_id>/nudge', methods=['POST'])
@login_required
@coach_required
def nudge(tournament_id):
    """Remind everyone who hasn't replied."""
    tournament = team_row_or_404(Tournament, tournament_id)
    waiting = len(rsvps.no_reply_players(tournament))
    sent = event_notify.remind_no_replies(tournament)
    db.session.commit()
    if not waiting:
        flash('Everyone has replied.', 'info')
    elif sent:
        flash(f'Reminder emailed to {sent} of the {waiting} players who haven\'t replied.', 'success')
    else:
        flash(f'{waiting} players haven\'t replied, but none of them can be emailed '
              '(no account, no email, or emails turned off). Message them directly.', 'warning')
    return redirect(url_for('tournament.detail', tournament_id=tournament.id, tab='squad'))


# Older pages: now tabs of the tournament page
@bp.route('/<int:tournament_id>/rsvps', endpoint='rsvps')
@login_required
@coach_required
def rsvps_page(tournament_id):
    return redirect(url_for('tournament.detail', tournament_id=tournament_id, tab='squad'))


@bp.route('/<int:tournament_id>/assign_players')
@login_required
@coach_required
def assign_players(tournament_id):
    return redirect(url_for('tournament.detail', tournament_id=tournament_id, tab='games'))


@bp.route('/<int:tournament_id>/update_selections', methods=['POST'])
@login_required
@coach_required
def update_selections(tournament_id):
    """Save the whole squad at once (the page works without JavaScript):
    ticked players are picked, everyone else who was picked is unpicked."""
    tournament = team_row_or_404(Tournament, tournament_id)
    chosen = set(team_player_ids(request.form.getlist('selected_players')))
    current = {p.id for p in rsvps.picked_players(tournament)}
    for player_id in chosen | current:
        player = db.session.get(Player, player_id)
        rsvps.set_selection(tournament, player, 'picked' if player_id in chosen else None)
    db.session.commit()
    flash(f'{len(chosen)} players picked for {tournament.name}', 'success')
    return redirect(url_for('tournament.detail', tournament_id=tournament_id, tab='squad'))


# ── Coaches: games ─────────────────────────────────────────────────────────

def _tournament_game_or_404(tournament, game_id):
    return Game.query.filter_by(id=game_id, tournament_id=tournament.id,
                                team_organization_id=get_current_team_id()).first_or_404()


@bp.route('/<int:tournament_id>/games/<int:game_id>/player', methods=['POST'])
@login_required
@coach_required
def set_game_player(tournament_id, game_id):
    """Tick or untick one player for one game (saved straight away)."""
    tournament = team_row_or_404(Tournament, tournament_id)
    game = _tournament_game_or_404(tournament, game_id)
    data = request.get_json(silent=True) or {}
    player = _team_player_or_404(_int(data.get('player_id')))
    rsvps.set_game_player(game, player.id, bool(data.get('playing')))
    db.session.commit()
    return jsonify({'success': True, 'count': game.assigned_players.count()})


@bp.route('/<int:tournament_id>/games/<int:game_id>/fill', methods=['POST'])
@login_required
@coach_required
def fill_game(tournament_id, game_id):
    """Everyone picked plays this game (or nobody, with ?clear=1)."""
    tournament = team_row_or_404(Tournament, tournament_id)
    game = _tournament_game_or_404(tournament, game_id)
    GamePlayer.query.filter_by(game_id=game.id).delete()
    if not request.form.get('clear'):
        for player in rsvps.picked_players(tournament):
            rsvps.set_game_player(game, player.id, True)
    db.session.commit()
    return redirect(url_for('tournament.detail', tournament_id=tournament.id, tab='games'))


@bp.route('/<int:tournament_id>/games/<int:game_id>/update_players', methods=['POST'])
@login_required
@coach_required
def update_game_players(tournament_id, game_id):
    """Update player assignments for a specific game."""
    tournament = team_row_or_404(Tournament, tournament_id)
    game = _tournament_game_or_404(tournament, game_id)
    selected_player_ids = team_player_ids(request.form.getlist('game_players'))
    GamePlayer.query.filter_by(game_id=game_id).delete()
    for player_id in selected_player_ids:
        db.session.add(GamePlayer(game_id=game_id, player_id=player_id,
                                  team_organization_id=get_current_team_id()))
    db.session.commit()
    flash(f'{len(selected_player_ids)} players assigned to game vs {game.opponent}', 'success')
    return redirect(url_for('tournament.detail', tournament_id=tournament_id, tab='games'))


@bp.route('/<int:tournament_id>/bulk-update', methods=['POST'])
@login_required
@coach_required
def bulk_update_game_players(tournament_id):
    """Save the whole players x games grid (the page works without JavaScript)."""
    tournament = team_row_or_404(Tournament, tournament_id)
    for game in tournament.games:
        selected_player_ids = team_player_ids(request.form.getlist(f'game_players_{game.id}'))
        GamePlayer.query.filter_by(game_id=game.id).delete()
        for player_id in selected_player_ids:
            db.session.add(GamePlayer(game_id=game.id, player_id=player_id,
                                      team_organization_id=get_current_team_id()))
    db.session.commit()
    flash("Game assignments updated successfully.", "success")
    return redirect(url_for('tournament.detail', tournament_id=tournament_id, tab='games'))


@bp.route('/<int:tournament_id>/send-schedule', methods=['POST'])
@login_required
@coach_required
def send_schedule(tournament_id):
    tournament = team_row_or_404(Tournament, tournament_id)
    sent = event_notify.send_schedule(tournament)
    flash(f'Schedule emailed to {sent} players.' if sent else
          'Nobody could be emailed: picked players need an account with an email, and games assigned.',
          'success' if sent else 'warning')
    return redirect(url_for('tournament.detail', tournament_id=tournament.id, tab='games'))


@bp.route('/<int:tournament_id>/schedule', methods=['GET', 'POST'])
@login_required
@coach_required
def schedule(tournament_id):
    """Paste the schedule, one game per line; check the preview, then save."""
    tournament = team_row_or_404(Tournament, tournament_id)
    pasted = request.form.get('schedule', '')
    games = parse_schedule(pasted, tournament.start_date, tournament.end_date) if pasted else []
    if request.method == 'POST' and request.form.get('action') == 'save' and games:
        good = [g for g in games if g['opponent']]
        for parsed in good:
            game = Game(opponent=parsed['opponent'], date=parsed['date'], start_time=parsed['start_time'],
                        field=parsed['field'], our_score=0, their_score=0, tournament_id=tournament.id,
                        squad_id=tournament.squad_id, team_organization_id=tournament.team_organization_id)
            db.session.add(game)
            db.session.flush()
            rsvps.assign_default_players(game)
        db.session.commit()
        flash(f'{len(good)} game{"s" if len(good) != 1 else ""} added to {tournament.name}.', 'success')
        return redirect(url_for('tournament.detail', tournament_id=tournament.id, tab='games'))
    return render_template('tournament/schedule.html', tournament=tournament, pasted=pasted, games=games)
