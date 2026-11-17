"""Player view: coaches, captains and admins see the site as a player does,
without their higher access, and switch back when they're done.

While it's on, their role on every team reads as "player" (and a
superadmin's site-wide powers are off), so pages, menus and permission
checks all behave as they do for a player. Their own player profile is
used if they have one. A coach who doesn't play (or who wants to see
someone else's view) picks a roster player to preview as instead; that's
look-only, so nothing is saved on the player's behalf (see
block_preview_writes in app/__init__.py).
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.models.player import Player
from app.models.user import PLAYER_VIEW_KEY
from app.utils.team_filter import get_current_team_id

bp = Blueprint('player_view', __name__, url_prefix='/player-view')


def _require_eligible():
    if not current_user.can_use_player_view:
        abort(403)


def _roster(team_id):
    return (Player.query.filter_by(team_organization_id=team_id, active=True)
            .order_by(Player.name).all())


def _own_player(team_id):
    return current_user.player_for(team_id) if team_id else None


@bp.route('/', methods=['GET'])
@login_required
def choose():
    """Pick who to see the site as: yourself, a roster player, or a player
    who hasn't linked their account yet."""
    _require_eligible()
    team_id = get_current_team_id()
    state = session.get(PLAYER_VIEW_KEY) or {}
    own = _own_player(team_id)
    players = [p for p in _roster(team_id) if not own or p.id != own.id]
    if current_user.in_player_view:
        selected = str(state.get('player') or ('me' if own else 'none'))
    else:
        selected = 'me' if own else ''
    return render_template('player_view/choose.html', title='Player view', own=own, players=players,
                           selected=selected, next_url=request.args.get('next') or request.referrer)


@bp.route('/start', methods=['POST'])
@login_required
def start():
    _require_eligible()
    team_id = get_current_team_id()
    choice = (request.form.get('player') or 'me').strip()
    own = _own_player(team_id)
    player_id = None
    if choice == 'me':
        if own is None:
            return redirect(url_for('player_view.choose'))
    elif choice != 'none':
        player = Player.query.filter_by(id=int(choice) if choice.isdigit() else -1,
                                        team_organization_id=team_id).first()
        if player is None:
            flash('Pick a player on this team.', 'warning')
            return redirect(url_for('player_view.choose'))
        if not own or player.id != own.id:
            player_id = player.id
    session[PLAYER_VIEW_KEY] = {'user': current_user.id, 'player': player_id}
    # (the bar at the top of every page says who they're seeing it as)
    # The page they came from may be coaches-only: home is always open
    return redirect(url_for('main.index'))


@bp.route('/stop', methods=['POST'])
@login_required
def stop():
    session.pop(PLAYER_VIEW_KEY, None)
    flash('Back to your own view.', 'success')
    # Back to the dashboard: the page they were on was the player's version
    return redirect(url_for('main.index'))
