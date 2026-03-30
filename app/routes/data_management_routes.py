"""
Enhanced data management routes for Flask Application
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_login import login_required, current_user
from app.utils.utils import admin_required
from app.utils.enhanced_data_manager import EnhancedDataManager
import os
import json
import shutil
from werkzeug.utils import secure_filename
import tempfile
import zipfile
import logging
from datetime import datetime
import math
from flask import current_app
# New imports for Season Reset
from app.models.player import Player
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.tournament import Tournament
from app.models.clip import Clip, ClipTag
from app.models.annotation import ClipAnnotation
from app.models.event import Event, Pull

# Optional, only if present
try:
    from app.models.throws import Throw
except Exception:
    Throw = None

from sqlalchemy import and_, or_


from sqlalchemy import and_, or_

# Optional relationship models (import if present)
try:
    from app.models.game_player import GamePlayer
except Exception:
    GamePlayer = None

try:
    from app.models.tournament_rsvp import TournamentRSVP
except Exception:
    TournamentRSVP = None

# Stats model - your file is app/models/stats.py. The class is likely "Stat".
# If it's named differently (e.g., "Stats"), rename here accordingly.
try:
    from app.models.stats import Stat as StatModel
except Exception:
    StatModel = None



# Helpers (single set)
def _column_names(model):
    return {c.name for c in model.__table__.columns}

def _get_ids(query):
    # returns flat list of ids from a query for Model.id
    return [row[0] for row in query]

def _safe_delete(func, desc, counters=None, counter_key=None):
    """
    Run a delete operation safely in a nested transaction so that a failure
    doesn't abort the whole transaction. If it fails, rollback savepoint and continue.
    """
    from app import db  # single, app-bound instance
    try:
        with db.session.begin_nested():  # savepoint
            cnt = func()
            if counters is not None and counter_key is not None:
                counters[counter_key] = counters.get(counter_key, 0) + (cnt or 0)
            return cnt or 0, None
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning(f"[Season Reset] {desc} failed: {e}")
        return 0, e


def _delete_by_id_column(manager, column_name, id_list, exclude_models=None, counters=None, counter_key=None):
    """
    For every model that has <column_name>, delete rows where <column_name> IN (id_list).
    Skips models in exclude_models set.
    Runs each table delete inside its own savepoint.
    """
    if not id_list:
        return 0
    total = 0
    exclude_models = exclude_models or set()
    for table_name, model in manager.models.items():
        if model in exclude_models:
            continue
        cols = _column_names(model)
        if column_name in cols:
            cnt, _ = _safe_delete(
                lambda m=model: m.query.filter(getattr(m, column_name).in_(id_list)).delete(synchronize_session=False),
                f"DELETE {table_name} WHERE {column_name} IN (...)",
                counters, counter_key
            )
            total += cnt
    return total



def _get_admin_player_id():
    """Return current admin's Player.id if linked, else None."""
    try:
        admin_player = Player.query.filter_by(user_id=current_user.id).first()
        return admin_player.id if admin_player else None
    except Exception:
        return None

def _delete_records_by_player_ids(player_ids):
    """
    Generic cleaner: for any model that has a 'player_id' column,
    delete rows where player_id is in the provided set.
    """
    if not player_ids:
        return 0
    
    manager = get_manager()
    deleted_total = 0
    
    for table_name, model in manager.models.items():
        # Skip Player table itself here; handled separately
        if model is Player:
            continue
        
        # Only act if the model has 'player_id' column
        if 'player_id' in model.__table__.columns:
            try:
                count = model.query.filter(model.player_id.in_(player_ids)).delete(synchronize_session=False)
                if count:
                    logger.info(f"[Season Reset] Deleted {count} records from {table_name} by player_id")
                    deleted_total += count
            except Exception as e:
                logger.warning(f"[Season Reset] Skipped {table_name} cleanup by player_id due to: {e}")
    
    return deleted_total


# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='[%(asctime)s] %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# Create blueprint
bp = Blueprint('data_management', __name__, url_prefix='/admin')

# Initialize data manager
manager = None

def get_manager():
    global manager
    if manager is None:
        # Always use /tmp directory which should be writable
        export_dir = '/tmp/data_exports'
        manager = EnhancedDataManager(export_dir=export_dir)
    return manager

# Add near the top with your other imports
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError
from sqlalchemy import text

# Helper to resolve the target team to reset
def _resolve_target_team_id():
    """
    Determine which TeamOrganization to reset.
    - Admins: allow explicit form selection; fallback to session or admin's own team.
    - Non-admins: force use of their own team.
    """
    from flask import session
    from app.models.team_organization import TeamOrganization

    team_id = None
    if getattr(current_user, 'is_admin', False):
        # Admins can choose; fallback to current session team or their own
        raw = request.form.get('team_id', '').strip()
        team_id = int(raw) if raw.isdigit() else None
        if not team_id:
            team_id = session.get('current_team_id') or getattr(current_user, 'team_organization_id', None)
    else:
        # Non-admins: always use their team
        team_id = getattr(current_user, 'team_organization_id', None)

    if not team_id:
        flash('❌ No team selected or associated with your account.', 'error')
        return None, None

    team = TeamOrganization.query.get(team_id)
    if not team:
        flash('❌ Selected team does not exist.', 'error')
        return None, None

    return team_id, team


def _get_admin_player_id():
    from app.models.player import Player
    try:
        return Player.query.filter_by(user_id=current_user.id).with_entities(Player.id).scalar()
    except Exception:
        return None

@bp.route('/season-reset', methods=['POST'])
@login_required
@admin_required
def season_reset():
    """
    Team-scoped Season Reset.
    Deletes in-season data ONLY for the selected team_organization_id, in FK-safe order, with per-step savepoints.

    Removes (for selected team):
      - Game/Point chain: GamePlayer, Points (LineUp, Event, Pull, Throw, CuttingSkill, GameDayEvent, PlayerPointStats), Games
      - Tournaments and TournamentRSVP
      - Clips linked to those Games/Points (ClipAnnotation + clip_tag_relation + clip_player)
      - Player-linked rows for players being removed (Attendance, SessionRSVP, FitnessRecord, GameDay*, Stats, CuttingSkill, Pull, Throw)
      - Players (except admin player in that team)
      - Optionally: non-admin Users in that team

    Preserves:
      - Admin user and admin player (for the selected team)
      - Session plans, drills, playbook, theory, scouting, off-season content
      - Clip library not linked to a game/point for this team
    """
    from app import db
    from sqlalchemy import or_

    # Core models
    from app.models.user import User
    from app.models.player import Player
    from app.models.team_organization import TeamOrganization
    from app.models.game import Game
    from app.models.point import Point, LineUp
    from app.models.tournament import Tournament
    from app.models.tournament_rsvp import TournamentRSVP
    from app.models.event import Event, Pull
    from app.models.throws import Throw
    from app.models.clip import Clip, ClipTag, clip_tag_relation, clip_player
    from app.models.annotation import ClipAnnotation

    # Player/point/game-linked models
    from app.models.stats import PlayerPointStats
    from app.models.cutting_skill import CuttingSkill
    from app.models.game_player import GamePlayer
    from app.models.gameday import GameDayEvent, GameDayPlayerStats, LineTemplatePlayer
    from app.models.session import Attendance, SessionRSVP
    from app.models.fitness import FitnessRecord

    confirm_text = request.form.get('confirm_text', '').strip()
    also_delete_non_admin_users = request.form.get('delete_non_admin_users') == 'on'
    reset_sequences_after = request.form.get('reset_sequences_after') == 'on'

    if confirm_text != 'RESET SEASON':
        flash('❌ Please type "RESET SEASON" exactly to confirm.', 'error')
        return redirect(url_for('data_management.data_management'))

    # Resolve target team (admins can choose, users use their team)
    team_id, team = _resolve_target_team_id()
    if not team_id:
        return redirect(url_for('data_management.data_management'))

    # Savepoint helper using the single app-bound db instance
    def _safe_delete(func, desc, counters=None, counter_key=None):
        try:
            with db.session.begin_nested():  # savepoint
                cnt = func()
                if counters is not None and counter_key is not None:
                    counters[counter_key] = counters.get(counter_key, 0) + (cnt or 0)
                return cnt or 0
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.warning(f"[Season Reset] {desc} failed: {e}")
            return 0

    def _ids(query):
        return [row[0] for row in query]

    deleted = {
        'clip_children': 0,
        'game_clips': 0,
        'by_point_id': 0,
        'by_game_id': 0,
        'by_player_id': 0,
        'stats': 0,
        'game_players': 0,
        'points': 0,
        'games': 0,
        'tournament_rsvps': 0,
        'tournaments': 0,
        'players': 0,
        'users': 0,
    }

    try:
        db.session.rollback()  # clear pending state
        logger.info(f"[Season Reset] Starting for team_id={team_id} ({team.name})")

        # Identify admin player in this team to keep
        admin_user_id = current_user.id
        admin_player_id = Player.query.filter_by(user_id=admin_user_id, team_organization_id=team_id)\
                                      .with_entities(Player.id).scalar()

        # Collect IDs scoped to team
        game_ids = _ids(db.session.query(Game.id).filter(Game.team_organization_id == team_id))
        point_ids = _ids(db.session.query(Point.id).filter(Point.team_organization_id == team_id))
        event_ids = _ids(db.session.query(Event.id).filter(Event.point_id.in_(point_ids))) if point_ids else []

        # Clips linked to those games/points (team-scoped implicitly by game/point)
        clip_ids_game = _ids(db.session.query(Clip.id).filter(Clip.game_id.in_(game_ids)))
        clip_ids_point = _ids(db.session.query(Clip.id).filter(Clip.point_id.in_(point_ids))) if point_ids else []
        clip_ids_all = list(set(clip_ids_game + clip_ids_point))

        # Players in this team to delete (exclude admin player for this team)
        if admin_player_id:
            players_to_delete = _ids(db.session.query(Player.id)
                                     .filter(Player.team_organization_id == team_id,
                                             Player.id != admin_player_id))
        else:
            players_to_delete = _ids(db.session.query(Player.id)
                                     .filter(Player.team_organization_id == team_id))

        # --- 1) Clip children/associations for team’s game/point clips ---
        if clip_ids_all:
            deleted['clip_children'] += _safe_delete(
                lambda: ClipAnnotation.query.filter(ClipAnnotation.clip_id.in_(clip_ids_all)).delete(synchronize_session=False),
                "DELETE ClipAnnotation by clip_id"
            )
            deleted['clip_children'] += _safe_delete(
                lambda: db.session.execute(clip_tag_relation.delete().where(clip_tag_relation.c.clip_id.in_(clip_ids_all))).rowcount,
                "DELETE clip_tag_relation by clip_id"
            )
            deleted['clip_children'] += _safe_delete(
                lambda: db.session.execute(clip_player.delete().where(clip_player.c.clip_id.in_(clip_ids_all))).rowcount,
                "DELETE clip_player by clip_id"
            )

        # --- 2) Point chain children (team-scoped) ---
        if point_ids:
            deleted['by_point_id'] += _safe_delete(
                lambda: CuttingSkill.query.filter(CuttingSkill.point_id.in_(point_ids)).delete(synchronize_session=False),
                "DELETE CuttingSkill by point_id"
            )
            deleted['by_point_id'] += _safe_delete(
                lambda: GameDayEvent.query.filter(GameDayEvent.point_id.in_(point_ids)).delete(synchronize_session=False),
                "DELETE GameDayEvent by point_id"
            )
            deleted['by_point_id'] += _safe_delete(
                lambda: PlayerPointStats.query.filter(PlayerPointStats.point_id.in_(point_ids)).delete(synchronize_session=False),
                "DELETE PlayerPointStats by point_id"
            )
            if event_ids:
                # Throw rows referencing Events (throwing/receiving_event_id)
                throw_event_pred = None
                for col in ['throwing_event_id', 'receiving_event_id']:
                    cond = getattr(Throw, col).in_(event_ids)
                    throw_event_pred = cond if throw_event_pred is None else or_(throw_event_pred, cond)
                deleted['by_point_id'] += _safe_delete(
                    lambda: Throw.query.filter(throw_event_pred).delete(synchronize_session=False),
                    "DELETE Throw by *_event_id"
                )

            deleted['by_point_id'] += _safe_delete(
                lambda: Throw.query.filter(Throw.point_id.in_(point_ids)).delete(synchronize_session=False),
                "DELETE Throw by point_id"
            )
            deleted['by_point_id'] += _safe_delete(
                lambda: Pull.query.filter(Pull.point_id.in_(point_ids)).delete(synchronize_session=False),
                "DELETE Pull by point_id"
            )
            deleted['by_point_id'] += _safe_delete(
                lambda: LineUp.query.filter(LineUp.point_id.in_(point_ids)).delete(synchronize_session=False),
                "DELETE LineUp by point_id"
            )
            if event_ids:
                deleted['by_point_id'] += _safe_delete(
                    lambda: Event.query.filter(Event.id.in_(event_ids)).delete(synchronize_session=False),
                    "DELETE Event by ids"
                )

        # --- 3) Delete team’s game/point-linked Clips themselves ---
        if clip_ids_all:
            deleted['game_clips'] += _safe_delete(
                lambda: Clip.query.filter(Clip.id.in_(clip_ids_all)).delete(synchronize_session=False),
                "DELETE Clips linked to games/points"
            )

        # --- 4) Points (team only) ---
        deleted['points'] += _safe_delete(
            lambda: Point.query.filter(Point.team_organization_id == team_id).delete(synchronize_session=False),
            "DELETE Points (team)"
        )

        # --- 5) Game-level children and Games (team only) ---
        deleted['game_players'] += _safe_delete(
            lambda: GamePlayer.query.filter(GamePlayer.game_id.in_(game_ids)).delete(synchronize_session=False),
            "DELETE GamePlayer (team)"
        )
        deleted['by_game_id'] += _safe_delete(
            lambda: GameDayPlayerStats.query.filter(GameDayPlayerStats.game_id.in_(game_ids)).delete(synchronize_session=False),
            "DELETE GameDayPlayerStats (team)"
        )
        deleted['games'] += _safe_delete(
            lambda: Game.query.filter(Game.team_organization_id == team_id).delete(synchronize_session=False),
            "DELETE Games (team)"
        )

        # --- 6) Tournaments chain (team only) ---
        deleted['tournament_rsvps'] += _safe_delete(
            lambda: TournamentRSVP.query.filter(TournamentRSVP.team_organization_id == team_id).delete(synchronize_session=False),
            "DELETE TournamentRSVP (team)"
        )
        deleted['tournaments'] += _safe_delete(
            lambda: Tournament.query.filter(Tournament.team_organization_id == team_id).delete(synchronize_session=False),
            "DELETE Tournaments (team)"
        )

        # --- 7) Player-linked rows for players being removed (team only) ---
        if players_to_delete:
            deleted['by_player_id'] += _safe_delete(
                lambda: db.session.execute(clip_player.delete().where(clip_player.c.player_id.in_(players_to_delete))).rowcount,
                "DELETE clip_player by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: Attendance.query.filter(Attendance.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE Attendance by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: SessionRSVP.query.filter(SessionRSVP.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE SessionRSVP by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: FitnessRecord.query.filter(FitnessRecord.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE FitnessRecord by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: LineTemplatePlayer.query.filter(LineTemplatePlayer.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE LineTemplatePlayer by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: GameDayEvent.query.filter(GameDayEvent.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE GameDayEvent by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: GameDayPlayerStats.query.filter(GameDayPlayerStats.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE GameDayPlayerStats by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: PlayerPointStats.query.filter(PlayerPointStats.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE PlayerPointStats by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: CuttingSkill.query.filter(CuttingSkill.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE CuttingSkill by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: Pull.query.filter(Pull.player_id.in_(players_to_delete)).delete(synchronize_session=False),
                "DELETE Pull by player_id"
            )
            deleted['by_player_id'] += _safe_delete(
                lambda: Throw.query.filter(or_(Throw.thrower_id.in_(players_to_delete),
                                               Throw.receiver_id.in_(players_to_delete))).delete(synchronize_session=False),
                "DELETE Throw by thrower/receiver player_id"
            )

        # --- 8) Players (team only; preserve admin's player on this team) ---
        if admin_player_id:
            deleted['players'] += _safe_delete(
                lambda: Player.query.filter(Player.team_organization_id == team_id,
                                            Player.id != admin_player_id).delete(synchronize_session=False),
                "DELETE Players (team, excluding admin)"
            )
        else:
            deleted['players'] += _safe_delete(
                lambda: Player.query.filter(Player.team_organization_id == team_id).delete(synchronize_session=False),
                "DELETE Players (team)"
            )

        # --- 9) Optionally delete non-admin Users in this team only ---
        if also_delete_non_admin_users:
            deleted['users'] += _safe_delete(
                lambda: User.query.filter(User.team_organization_id == team_id,
                                          User.id != admin_user_id).delete(synchronize_session=False),
                "DELETE non-admin Users (team)"
            )

        db.session.commit()
        logger.info("[Season Reset] Committed database changes")

        # Optional sequence reset (affects whole DB; safe but global)
        if reset_sequences_after:
            try:
                results = get_manager().reset_sequences()
                success_count = sum(1 for result in results.values()
                                    if not str(result).startswith("Error") and not str(result).startswith("Skipped"))
                flash(f"✅ Database sequences reset for {success_count} tables.", "success")
            except Exception as e:
                logger.warning(f"[Season Reset] Failed to reset sequences: {e}")
                flash(f"⚠️ Season reset complete, but failed to reset sequences: {e}", "warning")

        # Summary
        summary_lines = [
            f"✅ Season reset completed for team: {team.name}.",
            f"- Players deleted (excluding admin): {deleted['players']}",
            f"- Games deleted: {deleted['games']}",
            f"- Tournaments deleted: {deleted['tournaments']}",
            f"- Tournament RSVPs deleted: {deleted['tournament_rsvps']}",
            f"- Points deleted: {deleted['points']}",
            f"- Game/Point clips deleted: {deleted['game_clips']}",
            f"- Clip child rows deleted (annotations/tags/associations): {deleted['clip_children']}",
            f"- Game-player links deleted: {deleted['game_players']}",
            f"- Point-related child rows deleted: {deleted['by_point_id']}",
            f"- Player-related child rows deleted: {deleted['by_player_id']}",
        ]
        if also_delete_non_admin_users:
            summary_lines.append(f"- Non-admin users deleted (team): {deleted['users']}")
        summary_lines.append("")
        summary_lines.append("Preserved: admin account, session plans, non-game clip library, scouting reports, theory, playbook, drills, off-season content.")

        flash("<br>".join(summary_lines), "success")
        return redirect(url_for('data_management.data_management'))

    except Exception as e:
        logger.error(f"[Season Reset] Error: {e}", exc_info=True)
        db.session.rollback()
        flash(f"❌ Season reset failed: {e}", "error")
        return redirect(url_for('data_management.data_management'))


@bp.route('/enhanced-data-management')
@login_required
@admin_required
def data_management():
    """Enhanced data management interface."""
    try:
        # Ensure any previous failed transaction is rolled back
        from app import db
        db.session.rollback()
        
        manager = get_manager()  # Get the manager instance
        
        try:
            model_info = manager.get_model_info()
        except Exception as e:
            logger.error(f"Error getting model info: {e}", exc_info=True)
            # Create a minimal model_info to allow the page to load
            model_info = {
                'models': {},
                'total_models': 0,
                'dependency_order': []
            }
        
        # Get available exports with details
        try:
            exports = manager.get_available_exports()
        except Exception as e:
            logger.error(f"Error getting exports: {e}", exc_info=True)
            exports = []
        
        # Calculate total records safely
        try:
            total_records = sum(model['record_count'] for model in model_info['models'].values())
        except Exception as e:
            logger.error(f"Error calculating total records: {e}", exc_info=True)
            total_records = 0
        
        # Get last export date safely
        last_export = exports[0]['date'] if exports else None
        
        return render_template('admin/enhanced_data_management.html', 
                             model_info=model_info, 
                             exports=exports,
                             total_records=total_records,
                             last_export=last_export,
                             export_dir=manager.export_dir)
    except Exception as e:
        # Log the error
        logger.error(f"Error in data management page: {e}", exc_info=True)
        
        # Roll back the session to clear any aborted transaction
        from app import db
        db.session.rollback()
        
        # Show an error message
        flash(f"An error occurred while loading the data management page: {str(e)}", "error")
        
        # Return the error page with details
        from flask import current_app
        debug_info = None
        if current_app.debug:  # Only show technical details in debug mode
            import traceback
            debug_info = traceback.format_exc()
            
        return render_template('admin/error.html', 
                             error_message="Database error occurred. The transaction has been rolled back.",
                             back_url=url_for('main.index'),
                             debug_info=debug_info)




@bp.route('/fix-sequences', methods=['POST'])
@login_required
@admin_required
def fix_sequences():
    """Reset all PostgreSQL sequences to fix duplicate key (UniqueViolation) errors."""
    try:
        from app import db
        results = get_manager().reset_sequences()
        db.session.commit()

        success = {t: v for t, v in results.items()
                   if not str(v).startswith('Error') and not str(v).startswith('Skipped')}
        errors = {t: v for t, v in results.items() if str(v).startswith('Error')}
        skipped = {t: v for t, v in results.items() if str(v).startswith('Skipped')}

        return jsonify({
            'success': True,
            'message': f'Sequences reset for {len(success)} table(s). '
                       f'{len(errors)} error(s), {len(skipped)} skipped.',
            'results': {t: str(v) for t, v in results.items()},
            'counts': {
                'reset': len(success),
                'errors': len(errors),
                'skipped': len(skipped),
            }
        })
    except Exception as e:
        logger.error(f'[Fix Sequences] Error: {e}', exc_info=True)
        from app import db
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/export-data', methods=['POST'])
@login_required
@admin_required
def export_data_route():
    """Export data via web interface."""
    try:
        export_name = request.form.get('export_name', '').strip()
        include_metadata = request.form.get('include_metadata') == 'on'
        export_format = request.form.get('export_format', 'json')
        
        # Generate custom name if provided
        custom_name = None
        if export_name:
            safe_name = secure_filename(export_name)
            custom_name = f"data_exports_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Always generate in-memory export for direct download
        memory_file, filename = get_manager().export_all_data(
            timestamp=True if not custom_name else False,
            custom_name=custom_name,
            format=export_format,
            in_memory=True  # Always use in-memory for direct download
        )
        
        # Send file directly to browser
        return send_file(
            memory_file,
            as_attachment=True,
            download_name=filename,
            mimetype='application/zip'
        )
                
    except Exception as e:
        logger.error(f"Export failed: {e}")
        flash(f'❌ Export failed: {str(e)}', 'error')
        return redirect(url_for('data_management.data_management'))

@bp.route('/export-excel-zip')
@login_required
@admin_required
def export_excel_zip_route():
    """Export all data to Excel files in a ZIP archive."""
    try:
        export_name = request.args.get('export_name', '').strip()
        
        # Generate custom name if provided
        custom_name = None
        if export_name:
            safe_name = secure_filename(export_name)
            custom_name = f"excel_export_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Generate in-memory export
        memory_file, filename = get_manager().export_all_to_excel_zip(
            timestamp=True if not custom_name else False,
            custom_name=custom_name
        )
        
        # Send file directly to browser
        return send_file(
            memory_file,
            as_attachment=True,
            download_name=filename,
            mimetype='application/zip'
        )
                
    except Exception as e:
        logger.error(f"Excel export failed: {e}")
        flash(f'❌ Excel export failed: {str(e)}', 'error')
        return redirect(url_for('data_management.data_management'))

@bp.route('/export-json-zip')
@login_required
@admin_required
def export_json_zip_route():
    """Export all data to JSON files in a ZIP archive."""
    try:
        export_name = request.args.get('export_name', '').strip()
        
        # Generate custom name if provided
        custom_name = None
        if export_name:
            safe_name = secure_filename(export_name)
            custom_name = f"json_export_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Generate in-memory export
        memory_file, filename = get_manager().export_all_to_json_zip(
            timestamp=True if not custom_name else False,
            custom_name=custom_name
        )
        
        # Send file directly to browser
        return send_file(
            memory_file,
            as_attachment=True,
            download_name=filename,
            mimetype='application/zip'
        )
                
    except Exception as e:
        logger.error(f"JSON export failed: {e}")
        flash(f'❌ JSON export failed: {str(e)}', 'error')
        return redirect(url_for('data_management.data_management'))




@bp.route('/import-data', methods=['POST'])
@login_required
@admin_required
def import_data_route():
    """Import data via web interface."""
    # Log all form data for debugging
    logger.info(f"Form data received: {request.form}")
    logger.info(f"Files received: {request.files.keys()}")
    
    import_type = request.form.get('import_type', '')
    logger.info(f"Import type detected: '{import_type}'")
    
    # If import_type is missing but we have a file, assume it's a file upload
    if not import_type and 'import_file' in request.files:
        import_type = 'file_upload'
        logger.info("No import_type specified but file found, assuming file_upload")
    
    if import_type == 'file_upload':
        logger.info("Processing file upload")
        # Check if file was uploaded
        if 'import_file' not in request.files:
            logger.error("No import_file in request.files")
            flash('❌ No file selected for upload', 'error')
            return redirect(url_for('data_management.data_management'))
            
        import_file = request.files['import_file']
        if not import_file.filename:
            logger.error("import_file has no filename")
            flash('❌ No file selected for upload', 'error')
            return redirect(url_for('data_management.data_management'))
            
        logger.info(f"File uploaded: {import_file.filename}")
        clear_existing = request.form.get('clear_existing') == 'on'
        
        try:
            # Save uploaded file to temporary location
            temp_dir = tempfile.mkdtemp()
            temp_file = os.path.join(temp_dir, secure_filename(import_file.filename))
            import_file.save(temp_file)
            logger.info(f"File saved to temporary location: {temp_file}")
            
            # Import from ZIP file
            logger.info("Starting import_from_zip")
            summary = get_manager().import_from_zip(temp_file, clear_existing=clear_existing)
            logger.info(f"Import completed with status: {summary['status']}")
            
            # Clean up
            shutil.rmtree(temp_dir)
            
            if summary['status'] == 'completed':
                total_records = sum(
                    info.get('records_imported', 0) 
                    for info in summary['results'].values() 
                    if isinstance(info, dict)
                )
                
                # Count errors
                total_errors = sum(
                    len(info.get('errors', [])) 
                    for info in summary['results'].values() 
                    if isinstance(info, dict)
                )
                
                if total_errors > 0:
                    flash(f'⚠️ Data imported with warnings! {total_records} records imported, {total_errors} errors occurred.', 'warning')
                else:
                    flash(f'✅ Data imported successfully! {total_records} records imported.', 'success')
            else:
                flash(f'❌ Import failed: {summary.get("error", "Unknown error")}', 'error')
                
        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            flash(f'❌ Import failed: {str(e)}', 'error')
        
        return redirect(url_for('data_management.data_management'))
            
    elif import_type == 'directory_import':
        # Directory import
        import_dir = request.form.get('import_dir')
        logger.info(f"Directory import requested for path: {import_dir}")
        
        clear_existing = request.form.get('clear_existing') == 'on'
        
        if not import_dir:
            flash('❌ Please specify an import directory', 'error')
            return redirect(url_for('data_management.data_management'))
        
        if not os.path.exists(import_dir):
            flash(f'❌ Import directory does not exist: {import_dir}', 'error')
            return redirect(url_for('data_management.data_management'))
        
        # Rest of your code...
    
    else:
        logger.error(f"Invalid import type: '{import_type}'")
        flash('❌ Invalid import type', 'error')
        return redirect(url_for('data_management.data_management'))



@bp.route('/export-details/<path:export_path>')
@login_required
@admin_required
def export_details(export_path):
    """Get detailed information about an export."""
    try:
        if not os.path.exists(export_path):
            return jsonify({'error': 'Export not found'}), 404
        
        details = {}
        
        # Load metadata
        metadata_path = os.path.join(export_path, 'metadata.json')
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                details['metadata'] = json.load(f)
        
        # Load summary
        summary_path = os.path.join(export_path, 'export_summary.json')
        if os.path.exists(summary_path):
            with open(summary_path, 'r') as f:
                details['summary'] = json.load(f)
        
        # Get file list
        files = []
        for filename in os.listdir(export_path):
            filepath = os.path.join(export_path, filename)
            if os.path.isfile(filepath):
                file_info = {
                    'name': filename,
                    'size': format_file_size(os.path.getsize(filepath)),
                    'modified': datetime.fromtimestamp(
                        os.path.getmtime(filepath)
                    ).strftime('%Y-%m-%d %H:%M:%S')
                }
                files.append(file_info)
        
        details['files'] = files
        details['total_size'] = get_directory_size(export_path)
        
        return jsonify(details)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/download-export')
@login_required
@admin_required
def download_export():
    """Download an export as a ZIP file."""
    export_path = request.args.get('path')
    
    if not export_path or not os.path.exists(export_path):
        flash('❌ Export not found', 'error')
        return redirect(url_for('data_management.data_management'))
    
    try:
        # Check if ZIP already exists
        zip_path = export_path + '.zip'
        if not os.path.exists(zip_path):
            # Create a ZIP file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(export_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, export_path)
                        zipf.write(file_path, arcname)
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=os.path.basename(zip_path),
            mimetype='application/zip'
        )
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        flash(f'❌ Download failed: {str(e)}', 'error')
        return redirect(url_for('data_management.data_management'))

@bp.route('/download-excel')
@login_required
@admin_required
def download_excel():
    """Download data as Excel file."""
    table_name = request.args.get('table')
    manager = get_manager()  # Get the manager instance
    model_info = manager.get_model_info()
    
    try:
        output, filename = manager.export_to_excel(table_name)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        logger.error(f"Excel export failed: {e}")
        flash(f'❌ Excel export failed: {str(e)}', 'error')
        return redirect(url_for('data_management.data_management'))

@bp.route('/delete-export', methods=['POST'])
@login_required
@admin_required
def delete_export():
    """Delete an export directory."""
    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            export_path = data.get('path')
        else:
            export_path = request.form.get('path')
        
        if not export_path or not os.path.exists(export_path):
            if request.is_json:
                return jsonify({'error': 'Export not found'}), 404
            else:
                flash('❌ Export not found', 'error')
                return redirect(url_for('data_management.data_management'))
        
        # Delete the directory
        shutil.rmtree(export_path)
        
        # Delete ZIP file if it exists
        zip_path = export_path + '.zip'
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        if request.is_json:
            return jsonify({'success': True, 'message': f'Export {export_path} deleted successfully'})
        else:
            flash(f'✅ Export {os.path.basename(export_path)} deleted successfully', 'success')
            return redirect(url_for('data_management.data_management'))
        
    except Exception as e:
        logger.error(f"Delete export failed: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'❌ Delete failed: {str(e)}', 'error')
            return redirect(url_for('data_management.data_management'))


@bp.route('/model-details/<table_name>')
@login_required
@admin_required
def model_details_api(table_name):
    """Get detailed information about a specific model."""
    manager = get_manager()  # Get the manager instance
    model_info = manager.get_model_info()
    try:
        if table_name not in manager.models:
            return jsonify({'error': 'Model not found'}), 404
        
        model = manager.models[table_name]
        
        # Get sample data (first 5 records)
        sample_records = []
        try:
            records = model.query.limit(5).all()
            for record in records:
                record_dict = {}
                for column in model.__table__.columns:
                    value = getattr(record, column.name)
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    record_dict[column.name] = value
                sample_records.append(record_dict)
        except Exception as e:
            logger.warning(f"Could not fetch sample data for {table_name}: {e}")
        
        # Get model info
        info = manager.get_model_info()
        model_info = info['models'][table_name]
        model_info['sample_data'] = sample_records
        
        return jsonify(model_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_directory_size(path):
    """Get the total size of a directory in bytes, formatted as human-readable string."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return format_file_size(total_size)

def format_file_size(size_bytes):
    """Format file size in bytes as human-readable string."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


@bp.route('/debug-zip', methods=['POST'])
@login_required
@admin_required
def debug_zip():
    """Debug route for ZIP file issues."""
    if 'import_file' not in request.files:
        return jsonify({'error': 'No file uploaded'})
        
    import_file = request.files['import_file']
    if not import_file.filename:
        return jsonify({'error': 'Empty filename'})
    
    # Save the file to a temporary location
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, secure_filename(import_file.filename))
    import_file.save(temp_file)
    
    try:
        # Check if it's a valid ZIP file
        if not zipfile.is_zipfile(temp_file):
            return jsonify({'error': 'Not a valid ZIP file'})
        
        # Extract the contents
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir)
        
        with zipfile.ZipFile(temp_file, 'r') as zipf:
            zipf.extractall(extract_dir)
        
        # List all files
        all_files = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, extract_dir)
                file_size = os.path.getsize(file_path)
                all_files.append({
                    'path': rel_path,
                    'size': file_size,
                    'is_json': file.endswith('.json')
                })
        
        return jsonify({
            'success': True,
            'filename': import_file.filename,
            'file_count': len(all_files),
            'files': all_files
        })
    
    except Exception as e:
        return jsonify({'error': str(e)})
    
    finally:
        shutil.rmtree(temp_dir)


@bp.route('/import-zip-file', methods=['POST'])
@login_required
@admin_required
def import_zip_file_route():
    """Direct route for importing ZIP files."""
    logger.info("ZIP file import route called")
    
    # Check if file was uploaded
    if 'import_file' not in request.files:
        logger.error("No import_file in request.files")
        flash('❌ No file selected for upload', 'error')
        return redirect(url_for('data_management.data_management'))
        
    import_file = request.files['import_file']
    if not import_file.filename:
        logger.error("import_file has no filename")
        flash('❌ No file selected for upload', 'error')
        return redirect(url_for('data_management.data_management'))
    
    # Validate file format - only accept .zip files
    if not import_file.filename.lower().endswith('.zip'):
        logger.error(f"Invalid file format: {import_file.filename}")
        flash('❌ Invalid file format. Only ZIP files are accepted for import.', 'error')
        return redirect(url_for('data_management.data_management'))
        
    logger.info(f"File uploaded: {import_file.filename}")
    clear_existing = request.form.get('clear_existing') == 'on'
    
    try:
        # Save uploaded file to temporary location
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, secure_filename(import_file.filename))
        import_file.save(temp_file)
        logger.info(f"File saved to temporary location: {temp_file}")
        
        # Verify the ZIP contains JSON files (not Excel)
        with zipfile.ZipFile(temp_file, 'r') as zipf:
            file_list = zipf.namelist()
            json_files = [f for f in file_list if f.endswith('.json')]
            excel_files = [f for f in file_list if f.endswith('.xlsx') or f.endswith('.xls')]
            
            if not json_files:
                logger.error("No JSON files found in the uploaded ZIP")
                flash('❌ No JSON files found in the uploaded ZIP. Please upload a JSON format backup.', 'error')
                shutil.rmtree(temp_dir)
                return redirect(url_for('data_management.data_management'))
            
            if excel_files and not json_files:
                logger.error("Excel files found but no JSON files - this appears to be an Excel export")
                flash('❌ This appears to be an Excel format backup. Only JSON format backups can be imported.', 'error')
                shutil.rmtree(temp_dir)
                return redirect(url_for('data_management.data_management'))
        
        # Import from ZIP file
        logger.info("Starting import_from_zip")
        summary = get_manager().import_from_zip(temp_file, clear_existing=clear_existing)
        logger.info(f"Import completed with status: {summary['status']}")
        
        # Clean up
        shutil.rmtree(temp_dir)
        
        if summary['status'] == 'completed':
            total_records = sum(
                info.get('records_imported', 0) 
                for info in summary['results'].values() 
                if isinstance(info, dict)
            )
            
            # Count errors
            total_errors = sum(
                len(info.get('errors', [])) 
                for info in summary['results'].values() 
                if isinstance(info, dict)
            )
            
            if total_errors > 0:
                flash(f'⚠️ Data imported with warnings! {total_records} records imported, {total_errors} errors occurred.', 'warning')
            else:
                flash(f'✅ Data imported successfully! {total_records} records imported.', 'success')
        else:
            flash(f'❌ Import failed: {summary.get("error", "Unknown error")}', 'error')
            
    except zipfile.BadZipFile:
        logger.error("Bad ZIP file uploaded")
        flash('❌ The uploaded file is not a valid ZIP archive.', 'error')
        shutil.rmtree(temp_dir)
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        flash(f'❌ Import failed: {str(e)}', 'error')
        # Clean up temp directory if it exists
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    # Add this to the end of your import_zip_file_route function
    if summary['status'] == 'completed':
        try:
            logger.info("Automatically resetting sequences after successful import...")
            sequence_results = get_manager().reset_sequences()
            logger.info(f"Auto-reset sequences after import: {sequence_results}")
            
            # Count successful resets
            success_count = sum(1 for result in sequence_results.values() 
                               if not result.startswith("Error") and not result.startswith("Skipped"))
            
            flash(f"✅ Database sequences automatically reset for {success_count} tables.", 'success')
        except Exception as e:
            logger.warning(f"Failed to auto-reset sequences: {e}")
            flash(f"⚠️ Import successful, but failed to reset sequences: {str(e)}. Use the 'Reset Database Sequences' button.", 'warning')
    
        
    return redirect(url_for('data_management.data_management'))


@bp.route('/reset-sequences', methods=['POST'])
@login_required
@admin_required
def reset_sequences():
    """Reset database sequences for all models after an import."""
    try:
        manager = get_manager()
        results = manager.reset_sequences()
        
        # Count successful resets
        success_count = sum(1 for result in results.values() if not result.startswith("Error") and not result.startswith("Skipped"))
        
        # Log the results
        logger.info(f"Sequence reset results: {results}")
        
        # Create a success message
        message = f"✅ Database sequences reset successfully for {success_count} tables."
        flash(message, 'success')
        
        # Add detailed log entry
        addLogEntry = request.form.get('addLogEntry', 'true') == 'true'
        if addLogEntry:
            for table, result in results.items():
                if result.startswith("Error"):
                    flash(f"❌ Failed to reset sequence for {table}: {result}", 'error')
        
    except Exception as e:
        logger.error(f"Failed to reset sequences: {e}", exc_info=True)
        flash(f'❌ Failed to reset sequences: {str(e)}', 'error')
    
    return redirect(url_for('data_management.data_management'))

