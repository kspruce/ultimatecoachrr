# app/routes/team_organization.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, g, current_app
from flask_login import login_required, current_user
from app import db
from app.models.team_organization import TeamOrganization
from app.forms.team_organization import TeamOrganizationForm
import logging
import os
import uuid
from werkzeug.utils import secure_filename
from sqlalchemy import or_

logger = logging.getLogger(__name__)

bp = Blueprint('team_organization', __name__, url_prefix='/teams')

LOGO_UPLOAD_FOLDER = os.path.join('uploads', 'team_logos')
ALLOWED_LOGO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'}

def _save_logo(file_storage):
    """Save an uploaded logo file and return the relative path for static serving."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        return None
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.static_folder, LOGO_UPLOAD_FOLDER)
    os.makedirs(upload_dir, exist_ok=True)
    file_storage.save(os.path.join(upload_dir, filename))
    return f"{LOGO_UPLOAD_FOLDER}/{filename}"

@bp.route('/')
@login_required
def index():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    teams = TeamOrganization.query.all()
    return render_template('team_organization/index.html', teams=teams)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    form = TeamOrganizationForm()
    if form.validate_on_submit():
        logo_path = _save_logo(form.logo.data)
        team = TeamOrganization(
            name=form.name.data,
            slug=form.slug.data,
            description=form.description.data,
            division=form.division.data,
            logo=logo_path
        )

        db.session.add(team)
        db.session.commit()
        flash(f'Team {team.name} has been created!', 'success')
        return redirect(url_for('team_organization.index'))
    return render_template('team_organization/form.html', form=form, title='Add Team')


@bp.route('/edit/<int:team_id>', methods=['GET', 'POST'])
@login_required
def edit(team_id):
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    team = TeamOrganization.query.get_or_404(team_id)
    form = TeamOrganizationForm(obj=team, team_id=team_id)  # Pass team_id here
    if form.validate_on_submit():
        team.name = form.name.data
        team.slug = form.slug.data
        team.description = form.description.data
        team.division = form.division.data
        # Handle logo upload (only replace if a new file was provided)
        new_logo = _save_logo(form.logo.data)
        if new_logo:
            # Delete old logo file if it exists
            if team.logo:
                old_path = os.path.join(current_app.static_folder, team.logo)
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass
            team.logo = new_logo
        db.session.commit()
        flash(f'Team {team.name} has been updated!', 'success')
        return redirect(url_for('team_organization.index'))
    return render_template('team_organization/form.html', form=form, team=team, title='Edit Team')


@bp.route('/switch/<int:team_id>')
@login_required
def switch(team_id):
    if not current_user.is_admin:
        flash('Only administrators can switch teams.', 'danger')
        return redirect(url_for('main.index'))

    team = TeamOrganization.query.get_or_404(team_id)
    session['current_team_id'] = team.id
    flash(f'Switched to team: {team.name}', 'success')
    return redirect(request.referrer or url_for('main.index'))


@bp.route('/delete/<int:team_id>', methods=['POST'])
@login_required
def delete(team_id):
    """Hard delete a team and ALL related data. Superadmin only."""
    if not current_user.is_superadmin:
        flash('Only site superadmins can delete teams.', 'danger')
        return redirect(url_for('team_organization.index'))

    team = TeamOrganization.query.get_or_404(team_id)
    team_name = team.name

    # Safety: require typing the team name to confirm
    confirm = request.form.get('confirm_name', '').strip()
    if confirm != team_name:
        flash(f'Confirmation name did not match. Type exactly: {team_name}', 'danger')
        return redirect(url_for('team_organization.index'))

    try:
        _delete_team_data(team_id)
        db.session.delete(team)
        db.session.commit()
        # Clear session if we just deleted the active team
        if session.get('current_team_id') == team_id:
            session.pop('current_team_id', None)
        flash(f'Team "{team_name}" and all its data have been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error deleting team {team_id}: {e}', exc_info=True)
        flash(f'Error deleting team: {str(e)}', 'danger')

    return redirect(url_for('team_organization.index'))


def _delete_team_data(team_id):
    """Delete all data for a team in FK-safe order."""
    # Import all needed models inline to avoid circular imports
    from app.models.user import User
    from app.models.player import Player
    from app.models.game import Game
    from app.models.point import Point, LineUp
    from app.models.tournament import Tournament
    from app.models.event import Event, Pull
    from app.models.clip import Clip, clip_tag_relation, clip_player
    from app.models.annotation import ClipAnnotation
    from app.models.session import Attendance, SessionRSVP
    from app.models.fitness import FitnessRecord

    try:
        from app.models.throws import Throw
    except Exception:
        Throw = None
    try:
        from app.models.stats import PlayerPointStats
    except Exception:
        PlayerPointStats = None
    try:
        from app.models.cutting_skill import CuttingSkill
    except Exception:
        CuttingSkill = None
    try:
        from app.models.game_player import GamePlayer
    except Exception:
        GamePlayer = None
    try:
        from app.models.gameday import GameDayEvent, GameDayPlayerStats, LineTemplatePlayer, LineTemplate
    except Exception:
        GameDayEvent = GameDayPlayerStats = LineTemplatePlayer = LineTemplate = None
    try:
        from app.models.tournament_rsvp import TournamentRSVP
    except Exception:
        TournamentRSVP = None
    try:
        from app.models.team_settings import TeamSettings
    except Exception:
        TeamSettings = None
    try:
        from app.models.session import SessionPlan, SessionComponent
    except Exception:
        SessionPlan = SessionComponent = None
    try:
        from app.models.session import SessionRSVP
    except Exception:
        SessionRSVP = None
    try:
        from app.models.playbook import PlaybookPlay
    except Exception:
        PlaybookPlay = None
    try:
        from app.models.scouting import ScoutingReport, OpponentPlayer, ScoutingClip
    except Exception:
        ScoutingReport = OpponentPlayer = ScoutingClip = None
    try:
        from app.models.invite_token import InviteToken
    except Exception:
        InviteToken = None
    try:
        from app.models.clip import ClipTag
    except Exception:
        ClipTag = None
    try:
        from app.models.export_log import ExportLog
    except Exception:
        ExportLog = None

    def safe(fn, desc):
        try:
            with db.session.begin_nested():
                fn()
        except Exception as e:
            logger.warning(f'[TeamDelete] {desc} skipped: {e}')

    # Collect IDs
    game_ids   = [r[0] for r in db.session.query(Game.id).filter(Game.team_organization_id == team_id)]
    point_ids  = [r[0] for r in db.session.query(Point.id).filter(Point.team_organization_id == team_id)]
    event_ids  = [r[0] for r in db.session.query(Event.id).filter(Event.point_id.in_(point_ids))] if point_ids else []
    clip_ids   = [r[0] for r in db.session.query(Clip.id).filter(Clip.team_organization_id == team_id)]
    player_ids = [r[0] for r in db.session.query(Player.id).filter(Player.team_organization_id == team_id)]

    # 1. Clip associations
    if clip_ids:
        safe(lambda: ClipAnnotation.query.filter(ClipAnnotation.clip_id.in_(clip_ids)).delete(synchronize_session=False), 'ClipAnnotation')
        safe(lambda: db.session.execute(clip_tag_relation.delete().where(clip_tag_relation.c.clip_id.in_(clip_ids))), 'clip_tag_relation')
        safe(lambda: db.session.execute(clip_player.delete().where(clip_player.c.clip_id.in_(clip_ids))), 'clip_player')

    # 2. Point chain
    if point_ids:
        if CuttingSkill:  safe(lambda: CuttingSkill.query.filter(CuttingSkill.point_id.in_(point_ids)).delete(synchronize_session=False), 'CuttingSkill by point')
        if GameDayEvent:  safe(lambda: GameDayEvent.query.filter(GameDayEvent.point_id.in_(point_ids)).delete(synchronize_session=False), 'GameDayEvent by point')
        if PlayerPointStats: safe(lambda: PlayerPointStats.query.filter(PlayerPointStats.point_id.in_(point_ids)).delete(synchronize_session=False), 'PlayerPointStats by point')
        if Throw and event_ids:
            pred = or_(Throw.throwing_event_id.in_(event_ids), Throw.receiving_event_id.in_(event_ids))
            safe(lambda: Throw.query.filter(pred).delete(synchronize_session=False), 'Throw by event')
        if Throw: safe(lambda: Throw.query.filter(Throw.point_id.in_(point_ids)).delete(synchronize_session=False), 'Throw by point')
        safe(lambda: Pull.query.filter(Pull.point_id.in_(point_ids)).delete(synchronize_session=False), 'Pull')
        safe(lambda: LineUp.query.filter(LineUp.point_id.in_(point_ids)).delete(synchronize_session=False), 'LineUp')
        if event_ids:
            safe(lambda: Event.query.filter(Event.id.in_(event_ids)).delete(synchronize_session=False), 'Event')

    # 3. Clips themselves
    if clip_ids:
        safe(lambda: Clip.query.filter(Clip.id.in_(clip_ids)).delete(synchronize_session=False), 'Clips')

    # 4. Points
    safe(lambda: Point.query.filter(Point.team_organization_id == team_id).delete(synchronize_session=False), 'Points')

    # 5. Games
    if game_ids:
        if GamePlayer:       safe(lambda: GamePlayer.query.filter(GamePlayer.game_id.in_(game_ids)).delete(synchronize_session=False), 'GamePlayer')
        if GameDayPlayerStats: safe(lambda: GameDayPlayerStats.query.filter(GameDayPlayerStats.game_id.in_(game_ids)).delete(synchronize_session=False), 'GameDayPlayerStats by game')
    safe(lambda: Game.query.filter(Game.team_organization_id == team_id).delete(synchronize_session=False), 'Games')

    # 6. Tournaments
    if TournamentRSVP: safe(lambda: TournamentRSVP.query.filter(TournamentRSVP.team_organization_id == team_id).delete(synchronize_session=False), 'TournamentRSVP')
    safe(lambda: Tournament.query.filter(Tournament.team_organization_id == team_id).delete(synchronize_session=False), 'Tournaments')

    # 7. Player-linked rows
    if player_ids:
        safe(lambda: db.session.execute(clip_player.delete().where(clip_player.c.player_id.in_(player_ids))), 'clip_player by player')
        safe(lambda: Attendance.query.filter(Attendance.player_id.in_(player_ids)).delete(synchronize_session=False), 'Attendance')
        if SessionRSVP: safe(lambda: SessionRSVP.query.filter(SessionRSVP.player_id.in_(player_ids)).delete(synchronize_session=False), 'SessionRSVP')
        safe(lambda: FitnessRecord.query.filter(FitnessRecord.player_id.in_(player_ids)).delete(synchronize_session=False), 'FitnessRecord')
        if LineTemplatePlayer: safe(lambda: LineTemplatePlayer.query.filter(LineTemplatePlayer.player_id.in_(player_ids)).delete(synchronize_session=False), 'LineTemplatePlayer')
        if GameDayEvent: safe(lambda: GameDayEvent.query.filter(GameDayEvent.player_id.in_(player_ids)).delete(synchronize_session=False), 'GameDayEvent by player')
        if GameDayPlayerStats: safe(lambda: GameDayPlayerStats.query.filter(GameDayPlayerStats.player_id.in_(player_ids)).delete(synchronize_session=False), 'GameDayPlayerStats by player')
        if PlayerPointStats: safe(lambda: PlayerPointStats.query.filter(PlayerPointStats.player_id.in_(player_ids)).delete(synchronize_session=False), 'PlayerPointStats by player')
        if CuttingSkill: safe(lambda: CuttingSkill.query.filter(CuttingSkill.player_id.in_(player_ids)).delete(synchronize_session=False), 'CuttingSkill by player')
        safe(lambda: Pull.query.filter(Pull.player_id.in_(player_ids)).delete(synchronize_session=False), 'Pull by player')
        if Throw: safe(lambda: Throw.query.filter(or_(Throw.thrower_id.in_(player_ids), Throw.receiver_id.in_(player_ids))).delete(synchronize_session=False), 'Throw by player')

    # 8. Sessions / plans / components
    if SessionPlan:
        plan_ids = [r[0] for r in db.session.query(SessionPlan.id).filter(SessionPlan.team_organization_id == team_id)]
        if plan_ids and SessionComponent:
            safe(lambda: SessionComponent.query.filter(SessionComponent.session_id.in_(plan_ids)).delete(synchronize_session=False), 'SessionComponent')
        safe(lambda: SessionPlan.query.filter(SessionPlan.team_organization_id == team_id).delete(synchronize_session=False), 'SessionPlan')

    # 9. Scouting
    if ScoutingReport:
        report_ids = [r[0] for r in db.session.query(ScoutingReport.id).filter(ScoutingReport.team_organization_id == team_id)]
        if report_ids:
            if OpponentPlayer: safe(lambda: OpponentPlayer.query.filter(OpponentPlayer.report_id.in_(report_ids)).delete(synchronize_session=False), 'OpponentPlayer')
            if ScoutingClip:   safe(lambda: ScoutingClip.query.filter(ScoutingClip.report_id.in_(report_ids)).delete(synchronize_session=False), 'ScoutingClip')
        safe(lambda: ScoutingReport.query.filter(ScoutingReport.team_organization_id == team_id).delete(synchronize_session=False), 'ScoutingReport')

    # 10. Invite tokens
    if InviteToken: safe(lambda: InviteToken.query.filter(InviteToken.team_organization_id == team_id).delete(synchronize_session=False), 'InviteToken')

    # 11. Clip tags
    if ClipTag: safe(lambda: ClipTag.query.filter(ClipTag.team_organization_id == team_id).delete(synchronize_session=False), 'ClipTag')

    # 12. Line templates
    if LineTemplate: safe(lambda: LineTemplate.query.filter(LineTemplate.team_organization_id == team_id).delete(synchronize_session=False), 'LineTemplate')

    # 13. Playbook
    if PlaybookPlay: safe(lambda: PlaybookPlay.query.filter(PlaybookPlay.team_organization_id == team_id).delete(synchronize_session=False), 'PlaybookPlay')

    # 14. Export logs
    if ExportLog: safe(lambda: ExportLog.query.filter(ExportLog.team_organization_id == team_id).delete(synchronize_session=False), 'ExportLog')

    # 15. Players & Users
    safe(lambda: Player.query.filter(Player.team_organization_id == team_id).delete(synchronize_session=False), 'Players')
    safe(lambda: User.query.filter(User.team_organization_id == team_id).delete(synchronize_session=False), 'Users')

    # 16. Team settings
    if TeamSettings: safe(lambda: TeamSettings.query.filter(TeamSettings.team_id == team_id).delete(synchronize_session=False), 'TeamSettings')

    logger.info(f'[TeamDelete] All data for team {team_id} deleted successfully')
