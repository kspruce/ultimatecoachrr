from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from flask_wtf import FlaskForm
from sqlalchemy import or_, text
from sqlalchemy.orm import joinedload
from app import db
from app.models.game import Game
from app.models.tournament import Tournament
from app.forms.game import GameForm, GameFilterForm
from app.models.point import Point, LineUp
from app.models.player import Player
from app.models.event import Event, Pull
from app.models.gameday import GameDayPlayerStats
from app.utils.utils import coach_required, stat_taker_required
from datetime import datetime
from app.models.game_player import GamePlayer
from app.utils.rsvp import assign_default_players
from app.models.scouting import scouting_for_game
from app.utils.team_filter import get_current_team_id, team_player_ids
from app.utils.point_flow import analysis_progress
from app.utils.season import scope_games, scope_tournaments, team_squads, viewing_squad

bp = Blueprint('game', __name__, url_prefix='/games')


@bp.route('/')
@login_required
def index():
    form = GameFilterForm(team_id=get_current_team_id())
    delete_form = FlaskForm()  # Add this for CSRF protection
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    opponent = request.args.get('opponent', '')
    result = request.args.get('result', '')
    
    # Set form values from query parameters
    if tournament_id:
        form.tournament_id.data = tournament_id
    form.opponent.data = opponent
    form.result.data = result
    
    # Build query based on filters: a tournament, else the season (and squad) being viewed
    query = Game.query.filter_by(team_organization_id=get_current_team_id())
    
    if tournament_id and tournament_id > 0:
        query = query.filter(Game.tournament_id == tournament_id)
    else:
        query = scope_games(query)
    if opponent:
        query = query.filter(Game.opponent.ilike(f'%{opponent}%'))
    if result == 'win':
        query = query.filter(Game.our_score > Game.their_score)
    elif result == 'loss':
        query = query.filter(Game.our_score < Game.their_score)
    elif result == 'tie':
        query = query.filter(Game.our_score == Game.their_score)
    
    # Get games and sort by date (most recent first)
    games = query.order_by(Game.date.desc()).all()
    
    # Get tournaments for quick filters
    tournaments = scope_tournaments(Tournament.query.filter_by(team_organization_id=get_current_team_id())).order_by(Tournament.start_date.desc()).all()
    
    return render_template('game/index.html', 
                         games=games, 
                         form=form,
                         delete_form=delete_form,
                         tournaments=tournaments)

@bp.route('/<int:game_id>')
@login_required
def detail(game_id):
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    all_players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).all()
    
    delete_form = FlaskForm()  # Add CSRF form here too

    # Get players assigned to the game — single JOIN query instead of two round-trips
    game_players = (
        Player.query
        .join(GamePlayer, GamePlayer.player_id == Player.id)
        .filter(
            GamePlayer.game_id == game_id,
            # Older bulk assignments were saved without a team id.
            or_(GamePlayer.team_organization_id == get_current_team_id(),
                GamePlayer.team_organization_id.is_(None)),
            Player.team_organization_id == get_current_team_id(),
        )
        .all()
    )

    # Fall back to the first-point lineup if no GamePlayer records exist
    # Fix: use class-bound attributes for joinedload (SQLAlchemy 2.x requires this)
    if not game_players and game.points.count() > 0:
        first_point = game.points.options(
            joinedload(Point.lineups).joinedload(LineUp.player)
        ).first()
        if first_point:
            game_players = [
                lu.player for lu in first_point.lineups
                if lu.player and lu.player.team_organization_id == get_current_team_id()
            ]

    team_id = get_current_team_id()

    # ── Gameday stats fallback ────────────────────────────────────────────
    # Check if positional analysis events exist for this game
    has_positional_stats = db.session.query(Event.id)\
        .join(Point, Event.point_id == Point.id)\
        .filter(Point.game_id == game_id)\
        .limit(1).scalar() is not None

    # Always fetch gameday stats — shown as fallback when no positional data
    gameday_stats_raw = GameDayPlayerStats.query.filter_by(
        game_id=game_id,
        team_organization_id=team_id
    ).all()

    # Attach player details and sort by plus_minus descending
    for stat in gameday_stats_raw:
        stat.player_details = db.session.get(Player, stat.player_id)
    gameday_stats = sorted(
        [s for s in gameday_stats_raw if s.player_details],
        key=lambda s: (s.plus_minus or 0),
        reverse=True
    )

    scouting_report, scouting_matches = scouting_for_game(game)

    return render_template('game/detail.html',
                         game=game,
                         scouting_report=scouting_report,
                         scouting_matches=scouting_matches,
                         all_players=all_players,
                         game_players=game_players,
                         delete_form=delete_form,
                         gameday_stats=gameday_stats,
                         has_positional_stats=has_positional_stats,
                         progress=analysis_progress(game))

def _picked_squad_id(form):
    """The squad picked on the form, else the tournament's."""
    picked = next((s.id for s in team_squads(get_current_team_id()) if str(s.id) == (form.squad_id.data or '')), None)
    if picked is None and form.tournament_id.data and form.tournament_id.data > 0:
        tournament = Tournament.query.filter_by(id=form.tournament_id.data,
                                                team_organization_id=get_current_team_id()).first()
        picked = tournament.squad_id if tournament else None
    return picked


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@stat_taker_required
def add():
    form = GameForm(team_id=get_current_team_id())
    if request.method == 'GET':
        squad = viewing_squad()
        form.squad_id.data = str(squad.id) if squad else ''

    if form.validate_on_submit():
        
        game = Game(
            opponent=form.opponent.data,
            our_score=form.our_score.data,
            their_score=form.their_score.data,
            date=form.date.data,
            start_time=form.start_time.data,
            field=(form.field.data or '').strip() or None,
            youtube_link=form.youtube_link.data,
            notes=form.notes.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        
        if form.tournament_id.data > 0:
            game.tournament_id = form.tournament_id.data
        game.squad_id = _picked_squad_id(form)

        db.session.add(game)
        db.session.flush()

        # New games start with the tournament's picked players (or the
        # squad's roster for games outside a tournament)
        assign_default_players(game)

        if form.players_present.data:
            point = Point.query.filter_by(game_id=game.id).first()
            if not point:
                
                point = Point(
                    game_id=game.id,
                    point_number=1,
                    our_line_type='O-Line',
                    our_score_before=0,
                    their_score_before=0,
                    starting_position='offense',
                    point_outcome='scored',
                    our_score_after=1,
                    their_score_after=0,
                    team_organization_id=get_current_team_id()  # Add team organization ID
                )
                db.session.add(point)
                db.session.flush()

            for player_id in form.players_present.data:
                
                lineup = LineUp(
                    player_id=player_id, 
                    point_id=point.id, 
                    line_type='O-Line',
                    team_organization_id=get_current_team_id()  # Add team organization ID
                )
                db.session.add(lineup)

        db.session.commit()
        flash(f'Game against {game.opponent} has been added!', 'success')
        return redirect(url_for('game.index'))
    
    if request.method == 'GET':
        tournament_id = request.args.get('tournament_id', type=int)
        if tournament_id:
            form.tournament_id.data = tournament_id
            tournament = Tournament.query.filter_by(id=tournament_id, team_organization_id=get_current_team_id()).first()
            if tournament and not form.date.data:
                form.date.data = tournament.start_date
        day = request.args.get('date')
        if day:
            try:
                form.date.data = datetime.strptime(day, '%Y-%m-%d').date()
            except ValueError:
                pass

    return render_template('game/form.html', form=form, title='Add Game')

@bp.route('/edit/<int:game_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit(game_id):
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = GameForm(obj=game, team_id=get_current_team_id())
    if request.method == 'GET':
        form.squad_id.data = str(game.squad_id or '')

    if form.validate_on_submit():
        game.opponent = form.opponent.data
        game.our_score = form.our_score.data
        game.their_score = form.their_score.data
        game.date = form.date.data
        game.start_time = form.start_time.data
        game.field = (form.field.data or '').strip() or None
        game.youtube_link = form.youtube_link.data
        game.notes = form.notes.data
        
        if form.tournament_id.data > 0:
            game.tournament_id = form.tournament_id.data
        else:
            game.tournament_id = None
        game.squad_id = _picked_squad_id(form)

        db.session.commit()
        flash(f'Game against {game.opponent} has been updated!', 'success')
        return redirect(url_for('game.detail', game_id=game.id))
    
    return render_template('game/form.html', form=form, title='Edit Game')

@bp.route('/delete/<int:game_id>', methods=['POST'])
@login_required
@coach_required
def delete(game_id):
    try:
        game = Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        opponent = game.opponent

        # First, get all point IDs for this game
        point_ids = [point.id for point in game.points]
        
        if point_ids:
            # Delete GameDayEvent records first (these are causing the foreign key violation)
            db.session.execute(
                text("DELETE FROM game_day_event WHERE point_id IN :point_ids AND team_organization_id = :team_id"),
                {"point_ids": tuple(point_ids) if len(point_ids) > 1 else f"({point_ids[0]})", "team_id": get_current_team_id()}
            )
            
            # Delete GameDayPlayerStats records
            db.session.execute(
                text("DELETE FROM game_day_player_stats WHERE game_id = :game_id AND team_organization_id = :team_id"),
                {"game_id": game_id, "team_id": get_current_team_id()}
            )

        # Delete all related data for each point
        for point in game.points:
            # Delete throws associated with events in this point
            db.session.execute(
                text("DELETE FROM throw WHERE point_id = :point_id AND team_organization_id = :team_id"),
                {"point_id": point.id, "team_id": get_current_team_id()}
            )
            
            # Delete player point stats
            db.session.execute(
                text("DELETE FROM player_point_stats WHERE point_id = :point_id AND team_organization_id = :team_id"),
                {"point_id": point.id, "team_id": get_current_team_id()}
            )
            
            # Delete cutting skills
            db.session.execute(
                text("DELETE FROM cutting_skill WHERE point_id = :point_id AND team_organization_id = :team_id"),
                {"point_id": point.id, "team_id": get_current_team_id()}
            )

            # Delete events
            Event.query.filter_by(point_id=point.id, team_organization_id=get_current_team_id()).delete()
            
            # Delete pulls
            Pull.query.filter_by(point_id=point.id, team_organization_id=get_current_team_id()).delete()
            
            # Delete lineups
            LineUp.query.filter_by(point_id=point.id, team_organization_id=get_current_team_id()).delete()

        # Delete all points
        Point.query.filter_by(game_id=game_id, team_organization_id=get_current_team_id()).delete()

        # Delete clips if any
        if hasattr(game, 'clips'):
            for clip in game.clips:
                # Delete clip tags
                db.session.execute(
                    text("DELETE FROM clip_tag_relation WHERE clip_id = :clip_id AND team_organization_id = :team_id"),
                    {"clip_id": clip.id, "team_id": get_current_team_id()}
                )
                # Delete clip players
                db.session.execute(
                    text("DELETE FROM clip_player WHERE clip_id = :clip_id AND team_organization_id = :team_id"),
                    {"clip_id": clip.id, "team_id": get_current_team_id()}
                )
            # Delete clips
            db.session.execute(
                text("DELETE FROM clip WHERE game_id = :game_id AND team_organization_id = :team_id"),
                {"game_id": game_id, "team_id": get_current_team_id()}
            )

        # Delete game player associations
        GamePlayer.query.filter_by(game_id=game_id, team_organization_id=get_current_team_id()).delete()

        # Finally delete the game
        db.session.delete(game)
        db.session.commit()
        
        message = f'Game against {opponent} and all associated data has been deleted!'
        if request.is_json:
            return jsonify({'success': True, 'message': message})
            
        flash(message, 'success')
        return redirect(url_for('game.index'))
        
    except Exception as e:
        db.session.rollback()
        message = f'Error deleting game: {str(e)}'
        if request.is_json:
            return jsonify({'success': False, 'message': message}), 500
        flash(message, 'danger')
        return redirect(url_for('game.detail', game_id=game_id))

@bp.route('/<int:game_id>/update_players', methods=['POST'])
@login_required
@coach_required
def update_players(game_id):
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    player_ids = team_player_ids(request.form.getlist('player_ids'))

    # Delete existing GamePlayer records
    GamePlayer.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).delete()
    
    # Add new GamePlayer records
    for player_id in player_ids:
        
        game_player = GamePlayer(
            game_id=game_id,
            player_id=player_id,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        db.session.add(game_player)

    db.session.commit()
    flash('Players updated successfully!', 'success')
    return redirect(url_for('game.detail', game_id=game_id))

@bp.route('/add_multiple', methods=['GET', 'POST'])
@login_required
@stat_taker_required
def add_multiple():
    tournament_id = request.args.get('tournament_id', type=int)
    tournament = None
    if tournament_id:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
    
    if request.method == 'POST':
        team_id = get_current_team_id()

        def column(name):
            return request.form.getlist(f'{name}[]')

        def cell(values, i):
            return (values[i] if i < len(values) else '').strip()

        def score(value):
            try:
                return max(int(value), 0)
            except ValueError:
                return 0

        opponents, dates, times, fields = column('opponent'), column('date'), column('start_time'), column('field')
        ours, theirs, links, notes = column('our_score'), column('their_score'), column('youtube_link'), column('notes')
        added = 0
        for i in range(len(opponents)):
            opponent = cell(opponents, i)
            if not opponent:
                continue
            try:
                day = datetime.strptime(cell(dates, i), '%Y-%m-%d').date() if cell(dates, i) else None
            except ValueError:
                day = None
            try:
                start_time = datetime.strptime(cell(times, i), '%H:%M').time() if cell(times, i) else None
            except ValueError:
                start_time = None
            game = Game(
                opponent=opponent[:100],
                our_score=score(cell(ours, i)),
                their_score=score(cell(theirs, i)),
                date=day or (tournament.start_date if tournament else None),
                start_time=start_time,
                field=cell(fields, i)[:50] or None,
                youtube_link=cell(links, i) or None,
                notes=cell(notes, i) or None,
                team_organization_id=team_id,
            )
            if tournament:
                game.tournament_id = tournament.id
                game.squad_id = tournament.squad_id
            db.session.add(game)
            db.session.flush()
            assign_default_players(game)
            added += 1

        db.session.commit()
        flash(f'{added} game{"s" if added != 1 else ""} added!', 'success' if added else 'warning')
        
        if tournament_id:
            return redirect(url_for('tournament.detail', tournament_id=tournament_id, tab='games'))
        return redirect(url_for('game.index'))
    
    return render_template('game/add_multiple.html', tournament=tournament)
