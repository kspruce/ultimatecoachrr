"""Team roles (Club → Roles): the team's roles, such as "O-line initiation
cutter", and who holds each one this season, first choice first. Coaches
and captains change them here or on a player's profile; players say which
roles they'd like on their own profile. The playbook says what each role
does in each play."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.player import Player
from app.models.playbook import PlayAssignment, PlayerPosition
from app.models.team_organization import TeamOrganization
from app.models.team_role import PlayerRole
from app.utils import roles as team_roles_util
from app.utils.season import current_season, roster_entry, viewing_season
from app.utils.team_filter import get_current_team_id
from app.utils.utils import coach_required

bp = Blueprint('roles', __name__, url_prefix='/team/roles')


def roles_season(team_id):
    """The season being viewed; the current one when "All time" is picked."""
    return viewing_season(team_id) or current_season(team_id)


def role_or_404(role_id):
    return PlayerPosition.query.filter_by(id=role_id, team_organization_id=get_current_team_id()).first_or_404()


def row_or_404(row_id):
    return PlayerRole.query.filter_by(id=row_id, team_organization_id=get_current_team_id(),
                                      kind=PlayerRole.ASSIGNED).first_or_404()


def back(anchor=None):
    url = url_for('roles.index')
    return redirect(f'{url}#{anchor}' if anchor else url)


def clean_line(value):
    return value if value in ('O', 'D') else None


@bp.route('/')
@login_required
@coach_required
def index():
    team_id = get_current_team_id()
    season = roles_season(team_id)
    team = db.session.get(TeamOrganization, team_id)
    roles, unassigned = team_roles_util.board(team_id, season, team)
    plays = {role_id: len(found) for role_id, found in team_roles_util.plays_by_role(team_id).items()}
    return render_template('roles/index.html', title='Roles', season=season, roles=roles,
                           unassigned=unassigned, plays=plays, lines=PlayerPosition.LINES,
                           all_time=viewing_season(team_id) is None)


# ── The roles themselves ───────────────────────────────────────────────────

@bp.route('/starter', methods=['POST'])
@login_required
@coach_required
def starter():
    team_id = get_current_team_id()
    if not team_roles_util.team_roles(team_id):
        team_roles_util.add_starter_roles(team_id)
        db.session.commit()
        flash('Added a starting set of roles. Rename, add or remove them to match how you play.', 'success')
    return back()


@bp.route('/add', methods=['POST'])
@login_required
@coach_required
def add_role():
    team_id = get_current_team_id()
    name = (request.form.get('name') or '').strip()[:50]
    if not name:
        flash('A role needs a name.', 'danger')
        return back()
    role = PlayerPosition(team_organization_id=team_id, name=name, line=clean_line(request.form.get('line')),
                          description=(request.form.get('description') or '').strip()[:200] or None,
                          sort_order=team_roles_util.next_order(team_id))
    db.session.add(role)
    db.session.commit()
    return back(f'role-{role.id}')


@bp.route('/<int:role_id>/edit', methods=['POST'])
@login_required
@coach_required
def edit_role(role_id):
    role = role_or_404(role_id)
    name = (request.form.get('name') or '').strip()[:50]
    if name:
        role.name = name
    role.line = clean_line(request.form.get('line'))
    role.description = (request.form.get('description') or '').strip()[:200] or None
    db.session.commit()
    return back(f'role-{role.id}')


@bp.route('/<int:role_id>/order', methods=['POST'])
@login_required
@coach_required
def order_role(role_id):
    """Up or down among the roles on the same line."""
    role = role_or_404(role_id)
    same_line = [r for r in team_roles_util.team_roles(role.team_organization_id) if (r.line or '') == (role.line or '')]
    i = same_line.index(role)
    j = i + (-1 if request.form.get('direction') == 'up' else 1)
    if 0 <= j < len(same_line):
        same_line[i], same_line[j] = same_line[j], same_line[i]
        for n, r in enumerate(same_line, start=1):
            r.sort_order = n
        db.session.commit()
    return back(f'role-{role.id}')


@bp.route('/<int:role_id>/delete', methods=['POST'])
@login_required
@coach_required
def delete_role(role_id):
    role = role_or_404(role_id)
    PlayAssignment.query.filter_by(position_id=role.id).delete()
    name = role.name
    db.session.delete(role)
    db.session.commit()
    flash(f'"{name}" deleted, with what it did in each play.', 'success')
    return back()


# ── Who holds them ─────────────────────────────────────────────────────────

@bp.route('/<int:role_id>/assign', methods=['POST'])
@login_required
@coach_required
def assign(role_id):
    role = role_or_404(role_id)
    team_id = role.team_organization_id
    season = roles_season(team_id)
    player = Player.query.filter_by(id=request.form.get('player_id', type=int), team_organization_id=team_id).first()
    if season is None or player is None:
        abort(404)
    roster = roster_entry(player, season)
    if roster is None:
        flash(f'{player.name} isn’t on the {season.name} roster.', 'warning')
        return back(f'role-{role.id}')
    team_roles_util.assign(roster, role)
    db.session.commit()
    return back(f'role-{role.id}')


@bp.route('/holder/<int:row_id>/<string:action>', methods=['POST'])
@login_required
@coach_required
def holder(row_id, action):
    row = row_or_404(row_id)
    role_id = row.role_id
    if action == 'remove':
        team_roles_util.unassign(row)
    elif action in ('up', 'down'):
        team_roles_util.move(row, -1 if action == 'up' else 1)
    elif action == 'main':
        team_roles_util.make_main(row)
    else:
        abort(404)
    db.session.commit()
    return back(f'role-{role_id}')


# ── One player's roles (from their profile) ────────────────────────────────

@bp.route('/player/<int:player_id>', methods=['POST'])
@login_required
def player(player_id):
    """Coaches and captains set the player's roles; players say which ones
    they'd like."""
    team_id = get_current_team_id()
    player = Player.query.filter_by(id=player_id, team_organization_id=team_id).first_or_404()
    kind = request.form.get('kind')
    if kind == PlayerRole.ASSIGNED and not current_user.is_coach:
        abort(403)
    if kind == PlayerRole.PREFERRED and not (current_user.is_coach or player.user_id == current_user.id):
        abort(403)
    if kind not in (PlayerRole.ASSIGNED, PlayerRole.PREFERRED):
        abort(400)
    season = roles_season(team_id)
    if season is None:
        abort(404)
    wanted = set(request.form.getlist('role_id', type=int))
    chosen = [r for r in team_roles_util.team_roles(team_id) if r.id in wanted]
    roster = roster_entry(player, season)
    if roster is None:
        flash(f'{player.name} isn’t on the {season.name} roster, so they have no roles this season.', 'warning')
        return redirect(url_for('team.player_detail', player_id=player.id) + '#roles')
    team_roles_util.set_roles(roster, chosen, kind, main_role_id=request.form.get('main_role_id', type=int))
    db.session.commit()
    flash('Roles saved.' if kind == PlayerRole.ASSIGNED else 'Thanks: your coaches can see which roles you’d like.',
          'success')
    return redirect(url_for('team.player_detail', player_id=player.id) + '#roles')
