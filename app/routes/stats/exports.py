from flask import redirect, url_for, flash, send_file
import io
import csv
import tempfile
from flask_login import login_required, current_user
from app import db
from app.models.player import Player
from app.models.game import Game
from app.models.point import Point, LineUp
from datetime import datetime
from app.utils.team_filter import get_current_team_id

from app.routes.stats import bp, is_admin, is_coach
from app.stats.cache import calculate_per, get_cached_team_averages
from app.stats.history import get_player_game_history
from app.stats.players import get_players_base_stats


def _csv_response(rows, headers, filename):
    """Build a CSV file response from a list of row dicts."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    # Write to a temp file so send_file can stream it
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w', encoding='utf-8')
    tmp.write(output.getvalue())
    tmp.close()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        tmp.name,
        as_attachment=True,
        download_name=f'{filename}_{timestamp}.csv',
        mimetype='text/csv'
    )

@bp.route('/player/<int:player_id>/history.csv')
@login_required
def export_player_history_csv(player_id):
    """Download a player's per-game stat history as CSV."""
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    # Permission check: only the player themselves, admins, or coaches
    if not (is_admin(current_user) or is_coach(current_user) or
            (current_user.player and current_user.player.id == player_id)):
        flash('You do not have permission to export this player\'s stats.', 'danger')
        return redirect(url_for('stats_dashboard.player_stats', player_id=player_id))

    player_games = get_player_game_history(player, None, None)

    headers = [
        'date', 'opponent', 'result',
        'points_played', 'o_line_points_played', 'd_line_points_played',
        'goals', 'assists', 'hockey_assists', 'blocks',
        'completions', 'throws', 'completion_rate',
        'catches', 'drops', 'catch_rate',
        'throwaways', 'turnovers', 'plus_minus',
        'hucks', 'break_throws', 'break_throw_percentage',
        'o_line_conversion_rate', 'd_line_conversion_rate',
        'per',
    ]

    rows = []
    for gd in sorted(player_games, key=lambda x: x['game'].date or datetime.min.date()):
        g = gd['game']
        s = gd['stats']
        rows.append({
            'date':                  g.date.strftime('%Y-%m-%d') if g.date else '',
            'opponent':              g.opponent,
            'result':                'W' if getattr(g, 'is_win', False) else ('L' if getattr(g, 'is_loss', False) else ''),
            'points_played':         s.get('points_played', 0),
            'o_line_points_played':  s.get('o_line_points_played', 0),
            'd_line_points_played':  s.get('d_line_points_played', 0),
            'goals':                 s.get('goals', 0),
            'assists':               s.get('assists', 0),
            'hockey_assists':        s.get('hockey_assists', 0),
            'blocks':                s.get('blocks', 0),
            'completions':           s.get('completions', 0),
            'throws':                s.get('throws', 0),
            'completion_rate':       round(s.get('completion_rate', 0), 1),
            'catches':               s.get('catches', 0),
            'drops':                 s.get('drops', 0),
            'catch_rate':            round(s.get('catch_rate', 0), 1),
            'throwaways':            s.get('throwaways', 0),
            'turnovers':             s.get('turnovers', 0),
            'plus_minus':            s.get('goals', 0) + s.get('assists', 0) + s.get('blocks', 0) - s.get('turnovers', 0),
            'hucks':                 s.get('hucks', 0),
            'break_throws':          s.get('break_throws', 0),
            'break_throw_percentage': round(s.get('break_throw_percentage', 0), 1),
            'o_line_conversion_rate': round(s.get('o_line_conversion_rate', 0), 1),
            'd_line_conversion_rate': round(s.get('d_line_conversion_rate', 0), 1),
            'per':                   round(s.get('per', 0), 2),
        })

    safe_name = player.name.replace(' ', '_').lower()
    return _csv_response(rows, headers, f'player_{safe_name}_history')

@bp.route('/game/<int:game_id>/export.csv')
@login_required
def export_game_csv(game_id):
    """Download all player stats for a single game as CSV (admin/coach only)."""
    if not (is_admin(current_user) or is_coach(current_user)):
        flash('Only admins and coaches can export game stats.', 'danger')
        return redirect(url_for('stats_dashboard.game_stats', game_id=game_id))

    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    player_ids = db.session.query(LineUp.player_id).join(Point).filter(
        Point.game_id == game_id,
        LineUp.team_organization_id == get_current_team_id(),
        Point.team_organization_id == get_current_team_id()
    ).distinct().all()
    players = Player.query.filter(
        Player.id.in_([p[0] for p in player_ids]),
        Player.team_organization_id == get_current_team_id()
    ).all()

    team_avgs = get_cached_team_averages([game])
    player_stats_dict = get_players_base_stats(players, [game])

    headers = [
        'name', 'jersey_number', 'position', 'gender',
        'points_played', 'o_line_points_played', 'd_line_points_played',
        'goals', 'assists', 'hockey_assists', 'blocks',
        'completions', 'throws', 'completion_rate',
        'throwaways', 'drops', 'turnovers', 'plus_minus',
        'hucks', 'break_throws', 'break_throw_percentage',
        'o_line_conversion_rate', 'd_line_conversion_rate',
        'per',
    ]

    rows = []
    for player in sorted(players, key=lambda p: p.name):
        if player.id not in player_stats_dict:
            continue
        s = player_stats_dict[player.id]
        s['per'] = calculate_per(player, [game], team_avgs)
        rows.append({
            'name':                   player.name,
            'jersey_number':          getattr(player, 'jersey_number', ''),
            'position':               getattr(player, 'position', ''),
            'gender':                 getattr(player, 'gender', ''),
            'points_played':          s.get('points_played', 0),
            'o_line_points_played':   s.get('o_line_points_played', 0),
            'd_line_points_played':   s.get('d_line_points_played', 0),
            'goals':                  s.get('goals', 0),
            'assists':                s.get('assists', 0),
            'hockey_assists':         s.get('hockey_assists', 0),
            'blocks':                 s.get('blocks', 0),
            'completions':            s.get('completions', 0),
            'throws':                 s.get('throws', 0),
            'completion_rate':        round(s.get('completion_rate', 0), 1),
            'throwaways':             s.get('throwaways', 0),
            'drops':                  s.get('drops', 0),
            'turnovers':              s.get('turnovers', 0),
            'plus_minus':             s.get('goals', 0) + s.get('assists', 0) + s.get('blocks', 0) - s.get('turnovers', 0),
            'hucks':                  s.get('hucks', 0),
            'break_throws':           s.get('break_throws', 0),
            'break_throw_percentage': round(s.get('break_throw_percentage', 0), 1),
            'o_line_conversion_rate': round(s.get('o_line_conversion_rate', 0), 1),
            'd_line_conversion_rate': round(s.get('d_line_conversion_rate', 0), 1),
            'per':                    round(s.get('per', 0), 2),
        })

    date_str = game.date.strftime('%Y%m%d') if game.date else 'unknown'
    opponent_safe = game.opponent.replace(' ', '_').lower() if game.opponent else 'opponent'
    return _csv_response(rows, headers, f'game_{date_str}_vs_{opponent_safe}')

@bp.route('/team/export.csv')
@login_required
def export_team_season_csv():
    """Download season player stats (all games) as CSV (admin/coach only)."""
    if not (is_admin(current_user) or is_coach(current_user)):
        flash('Only admins and coaches can export team stats.', 'danger')
        return redirect(url_for('stats_dashboard.team_stats'))

    games = Game.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(Game.date).all()

    players = Player.query.filter_by(
        team_organization_id=get_current_team_id(),
        is_active=True
    ).all()

    team_avgs = get_cached_team_averages(games)
    player_stats_dict = get_players_base_stats(players, games)

    headers = [
        'name', 'jersey_number', 'position', 'gender',
        'games_played', 'points_played', 'o_line_points_played', 'd_line_points_played',
        'goals', 'assists', 'hockey_assists', 'blocks',
        'completions', 'throws', 'completion_rate',
        'catches', 'drops', 'catch_rate',
        'throwaways', 'turnovers', 'plus_minus',
        'hucks', 'break_throws', 'break_throw_percentage',
        'goals_per_point', 'assists_per_point', 'blocks_per_point',
        'o_line_conversion_rate', 'd_line_conversion_rate',
        'per',
    ]

    rows = []
    for player in sorted(players, key=lambda p: p.name):
        if player.id not in player_stats_dict:
            continue
        s = player_stats_dict[player.id]
        if s.get('points_played', 0) == 0:
            continue  # Skip players with no recorded activity
        s['per'] = calculate_per(player, games, team_avgs)
        rows.append({
            'name':                   player.name,
            'jersey_number':          getattr(player, 'jersey_number', ''),
            'position':               getattr(player, 'position', ''),
            'gender':                 getattr(player, 'gender', ''),
            'games_played':           s.get('games_played', 0),
            'points_played':          s.get('points_played', 0),
            'o_line_points_played':   s.get('o_line_points_played', 0),
            'd_line_points_played':   s.get('d_line_points_played', 0),
            'goals':                  s.get('goals', 0),
            'assists':                s.get('assists', 0),
            'hockey_assists':         s.get('hockey_assists', 0),
            'blocks':                 s.get('blocks', 0),
            'completions':            s.get('completions', 0),
            'throws':                 s.get('throws', 0),
            'completion_rate':        round(s.get('completion_rate', 0), 1),
            'catches':                s.get('catches', 0),
            'drops':                  s.get('drops', 0),
            'catch_rate':             round(s.get('catch_rate', 0), 1),
            'throwaways':             s.get('throwaways', 0),
            'turnovers':              s.get('turnovers', 0),
            'plus_minus':             s.get('goals', 0) + s.get('assists', 0) + s.get('blocks', 0) - s.get('turnovers', 0),
            'hucks':                  s.get('hucks', 0),
            'break_throws':           s.get('break_throws', 0),
            'break_throw_percentage': round(s.get('break_throw_percentage', 0), 1),
            'goals_per_point':        round(s.get('goals_per_point', 0), 3),
            'assists_per_point':      round(s.get('assists_per_point', 0), 3),
            'blocks_per_point':       round(s.get('blocks_per_point', 0), 3),
            'o_line_conversion_rate': round(s.get('o_line_conversion_rate', 0), 1),
            'd_line_conversion_rate': round(s.get('d_line_conversion_rate', 0), 1),
            'per':                    round(s.get('per', 0), 2),
        })

    return _csv_response(rows, headers, 'team_season_stats')
