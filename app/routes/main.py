from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user
from app_factory import db
from app.models.player import Player
from app.models.game import Game
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from datetime import datetime, timedelta
from flask import request, flash, jsonify
from app.utils.data_manager import DataManager
import os
from flask_login import login_required
from app.utils.utils import admin_required
from flask import send_file
import json
import shutil
from werkzeug.utils import secure_filename
import logging
import math
from sqlalchemy import inspect as sqlalchemy_inspect
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


bp = Blueprint('main', __name__)

@bp.route('/')
@bp.route('/index')
def index():
    # Initialize stats and activities
    stats = {
        'active_players_count': 0,
        'games_count': 0,
        'win_rate': 0,
        'next_game_date': None
    }
    
    recent_activities = []
    upcoming_events = []

    if current_user.is_authenticated:
        try:
            logger.debug("Starting to gather dashboard data")

            # Debug database records
            logger.debug("Debugging database records:")
            
            # Check for games with NULL dates
            null_date_games = db.session.query(Game).filter(Game.date.is_(None)).all()
            logger.debug(f"Found {len(null_date_games)} games with NULL dates")
            for game in null_date_games:
                logger.debug(f"Game ID {game.id} vs {game.opponent} has NULL date")
            
            # Check for sessions with NULL dates
            null_date_sessions = db.session.query(SessionPlan).filter(SessionPlan.date.is_(None)).all()
            logger.debug(f"Found {len(null_date_sessions)} sessions with NULL dates")
            for session in null_date_sessions:
                logger.debug(f"Session ID {session.id}: {session.title} has NULL date")
            
            # Check for tournaments with NULL dates
            null_date_tournaments = db.session.query(Tournament).filter(Tournament.start_date.is_(None)).all()
            logger.debug(f"Found {len(null_date_tournaments)} tournaments with NULL dates")
            for tournament in null_date_tournaments:
                logger.debug(f"Tournament ID {tournament.id}: {tournament.name} has NULL start_date")


            # Calculate Quick Stats
            # Active Players Count
            stats['active_players_count'] = Player.query.filter_by(active=True).count()

            # Check if we have any future events in the database
            future_games_count = Game.query.filter(Game.date >= datetime.now()).count()
            future_sessions_count = SessionPlan.query.filter(SessionPlan.date >= datetime.now().date()).count()
            future_tournaments_count = Tournament.query.filter(Tournament.start_date >= datetime.now().date()).count()
            
            logger.debug(f"Database counts - Games: {future_games_count}, Sessions: {future_sessions_count}, Tournaments: {future_tournaments_count}")

            # Games Statistics
            current_year = datetime.now().year
            games = Game.query.filter(
                db.extract('year', Game.date) == current_year
            ).all()
            
            stats['active_players_count'] = Player.query.filter_by(active=True).count()
            current_year = datetime.now().year
            games = Game.query.filter(db.extract('year', Game.date) == current_year).all()
            stats['games_count'] = len(games)
            if games:
                wins = sum(1 for game in games if game.is_win)
                stats['win_rate'] = round((wins / len(games)) * 100) if len(games) > 0 else 0
            next_game = Game.query.filter(Game.date >= datetime.now()).order_by(Game.date.asc()).first()
            if next_game:
                stats['next_game_date'] = next_game.date.strftime('%b %d')

            # Recent Activities
            recent_games = Game.query.order_by(Game.date.desc()).limit(3).all()
            for game in recent_games:
                recent_activities.append({
                    'type': 'game', 'icon': 'bi-trophy', 'title': f'Game vs {game.opponent}',
                    'timestamp': game.date.strftime('%b %d, %Y'), 'link': url_for('game.detail', game_id=game.id)
                })
            recent_sessions = SessionPlan.query.order_by(SessionPlan.date.desc()).limit(3).all()
            for session in recent_sessions:
                recent_activities.append({
                    'type': 'practice', 'icon': 'bi-calendar-check', 'title': f'Practice: {session.title}',
                    'timestamp': session.date.strftime('%b %d, %Y'), 'link': url_for('session.detail', session_id=session.id)
                })
            recent_tournaments = Tournament.query.order_by(Tournament.start_date.desc()).limit(2).all()
            for tournament in recent_tournaments:
                recent_activities.append({
                    'type': 'tournament', 'icon': 'bi-trophy-fill', 'title': f'Tournament: {tournament.name}',
                    'timestamp': tournament.start_date.strftime('%b %d, %Y'), 'link': url_for('tournament.detail', tournament_id=tournament.id)
                })
            recent_activities.sort(key=lambda x: datetime.strptime(x['timestamp'], '%b %d, %Y'), reverse=True)
            recent_activities = recent_activities[:5]

            # Upcoming Events
            # Future Games
            future_games = Game.query.filter(Game.date >= datetime.now()).order_by(Game.date.asc()).limit(3).all()
            logger.debug(f"Found {len(future_games)} future games")
            for game in future_games:
                try:
                    # Check if game.date is None before using strftime
                    if game.date is None:
                        logger.warning(f"Game ID {game.id} vs {game.opponent} has NULL date, skipping")
                        continue
                        
                    logger.debug(f"Processing game: {game.opponent} on {game.date}")
                    upcoming_events.append({
                        'type': 'game',
                        'title': f'vs {game.opponent}',
                        'date_time': game.date.strftime('%b %d, %Y - %I:%M %p'),
                        'sort_date': game.date,
                        'location': game.location if hasattr(game, 'location') and game.location else "No location",
                        'badge_color': 'danger',
                        'link': url_for('game.detail', game_id=game.id)
                    })
                except Exception as e:
                    logger.error(f"Error processing game {game.id}: {str(e)}")
            
            # Future Practice Sessions
            future_sessions = SessionPlan.query.filter(SessionPlan.date >= datetime.now().date()).order_by(SessionPlan.date.asc()).limit(3).all()
            logger.debug(f"Found {len(future_sessions)} future sessions")
            for session in future_sessions:
                try:
                    # Check if session.date is None
                    if session.date is None:
                        logger.warning(f"Session ID {session.id}: {session.title} has NULL date, skipping")
                        continue
                        
                    # Create a safe sort_datetime
                    if session.start_time:
                        sort_datetime = datetime.combine(session.date, session.start_time)
                    else:
                        sort_datetime = datetime.combine(session.date, datetime.min.time())
                    
                    # Create a safe formatted_time
                    formatted_time = session.formatted_time if hasattr(session, 'formatted_time') else "No time specified"
                    
                    logger.debug(f"Processing session: {session.title} on {session.date}, sort_datetime: {sort_datetime}")
                    
                    upcoming_events.append({
                        'type': 'practice',
                        'title': session.title,
                        'date_time': f"{session.date.strftime('%b %d, %Y')} - {formatted_time}",
                        'sort_date': sort_datetime,
                        'location': session.location if session.location else "No location",
                        'badge_color': 'success',
                        'link': url_for('session.detail', session_id=session.id)
                    })
                except Exception as e:
                    logger.error(f"Error processing session {session.id}: {str(e)}")
                
            # Future Tournaments
            future_tournaments = Tournament.query.filter(Tournament.start_date >= datetime.now().date()).order_by(Tournament.start_date.asc()).limit(2).all()
            logger.debug(f"Found {len(future_tournaments)} future tournaments")
            for tournament in future_tournaments:
                try:
                    # Check if tournament.start_date is None
                    if tournament.start_date is None:
                        logger.warning(f"Tournament ID {tournament.id}: {tournament.name} has NULL start_date, skipping")
                        continue
                        
                    sort_datetime = datetime.combine(tournament.start_date, datetime.min.time())
                    
                    # Check if formatted_date_range exists and is not None
                    formatted_date = tournament.formatted_date_range if hasattr(tournament, 'formatted_date_range') and tournament.formatted_date_range else tournament.start_date.strftime('%b %d, %Y')
                    
                    logger.debug(f"Processing tournament: {tournament.name} on {tournament.start_date}, sort_datetime: {sort_datetime}")
                    
                    upcoming_events.append({
                        'type': 'tournament',
                        'title': tournament.name,
                        'date_time': formatted_date,
                        'sort_date': sort_datetime,
                        'location': tournament.location if tournament.location else "No location",
                        'badge_color': 'warning',
                        'link': url_for('tournament.detail', tournament_id=tournament.id)
                    })
                except Exception as e:
                    logger.error(f"Error processing tournament {tournament.id}: {str(e)}")
            
            logger.debug(f"Total upcoming events before sorting: {len(upcoming_events)}")
            
            # Only try to sort if we have events
            if upcoming_events:
                # Debug each event's sort_date before sorting
                for i, event in enumerate(upcoming_events):
                    logger.debug(f"Event {i}: {event['title']} - sort_date: {event['sort_date']} - type: {type(event['sort_date'])}")
                
                # Sort upcoming events by the actual date object, not a string
                try:
                    upcoming_events.sort(key=lambda x: x['sort_date'])
                    logger.debug("Events sorted successfully")
                except Exception as e:
                    logger.error(f"Error sorting events: {str(e)}")
                    # Don't empty the list on error, just leave it unsorted
                
                upcoming_events = upcoming_events[:5]
                logger.debug(f"Final upcoming events count: {len(upcoming_events)}")
            else:
                logger.warning("No upcoming events to sort")
            



        except Exception as e:
            # Log any errors but don't crash the application
            logger.exception(f"Error generating dashboard data: {str(e)}")
            # Don't empty the upcoming_events list here


    return render_template('index.html',
                         title='Home',
                         stats=stats,
                         recent_activities=recent_activities,
                         upcoming_events=upcoming_events)

@bp.route('/about')
def about():
    return render_template('about.html', title='About')

@bp.route('/how-to-use')
def how_to_use():
    """Display the How to Use guide page."""
    return render_template('how_to_use.html', title='How to Use Ultimate Coach')

@bp.route('/admin/data-management')
@login_required
@admin_required
def data_management():
    """Data management interface."""
    manager = DataManager()  # This will now use the Downloads directory by default
    model_info = manager.get_model_info()
    
    # Get available exports with details
    exports = []
    
    # Check if export directory exists
    if os.path.exists(manager.export_dir):
        # Get all directories in the export directory that look like exports
        export_dirs = [d for d in os.listdir(manager.export_dir) 
                      if os.path.isdir(os.path.join(manager.export_dir, d)) and 
                      d.startswith('data_exports')]
        
        for export_dir_name in sorted(export_dirs, reverse=True):  # Most recent first
            export_dir = os.path.join(manager.export_dir, export_dir_name)
            try:
                metadata_path = os.path.join(export_dir, 'metadata.json')
                summary_path = os.path.join(export_dir, 'export_summary.json')
                
                export_info = {
                    'path': export_dir,
                    'name': export_dir_name.replace('data_exports_', '').replace('_', ' '),
                    'date': 'Unknown',
                    'records': 0,
                    'size': get_directory_size(export_dir)
                }
                
                # Load metadata if available
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        export_info['date'] = datetime.fromisoformat(
                            metadata['export_timestamp']
                        ).strftime('%Y-%m-%d %H:%M')
                
                # Load summary if available
                if os.path.exists(summary_path):
                    with open(summary_path, 'r') as f:
                        summary = json.load(f)
                        export_info['records'] = sum(
                            info.get('records_exported', 0) 
                            for info in summary.values() 
                            if isinstance(info, dict)
                        )
                
                exports.append(export_info)
                
            except Exception as e:
                logging.error(f"Error processing export {export_dir}: {e}")
    
    # Calculate total records
    total_records = sum(model['record_count'] for model in model_info['models'].values())
    
    # Get last export date
    last_export = exports[0]['date'] if exports else None
    
    return render_template('admin/data_management.html', 
                         model_info=model_info, 
                         exports=exports,
                         total_records=total_records,
                         last_export=last_export,
                         export_dir=manager.export_dir)


@bp.route('/admin/export-data', methods=['POST'])
@login_required
@admin_required
def export_data_route():
    """Export data via web interface."""
    try:
        export_name = request.form.get('export_name', '').strip()
        include_metadata = request.form.get('include_metadata') == 'on'
        
        manager = DataManager()  # Uses the Downloads directory
        
        # Create custom export directory name if provided
        if export_name:
            # Sanitize the export name
            safe_name = secure_filename(export_name)
            export_dir_name = f"data_exports_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            export_dir = os.path.join(manager.export_dir, export_dir_name)
            manager.export_dir = manager.export_dir  # Keep the base directory
            export_path = manager.export_all_data(timestamp=False, custom_name=export_dir_name)
        else:
            export_path = manager.export_all_data(timestamp=True)
        
        # Load export summary for flash message
        summary_path = os.path.join(export_path, 'export_summary.json')
        if os.path.exists(summary_path):
            with open(summary_path, 'r') as f:
                summary = json.load(f)
                total_records = sum(
                    info.get('records_exported', 0) 
                    for info in summary.values() 
                    if isinstance(info, dict)
                )
                flash(f'✅ Data exported successfully! {total_records} records exported to {export_path}', 'success')
        else:
            flash(f'✅ Data exported successfully to {export_path}', 'success')
            
    except Exception as e:
        logging.error(f"Export failed: {e}")
        flash(f'❌ Export failed: {str(e)}', 'error')
    
    return redirect(url_for('main.data_management'))




@bp.route('/admin/import-data', methods=['POST'])
@login_required
@admin_required
def import_data_route():
    """Import data via web interface."""
    import_dir = request.form.get('import_dir')
    clear_existing = request.form.get('clear_existing') == 'on'
    
    if not import_dir:
        flash('❌ Please specify an import directory', 'error')
        return redirect(url_for('main.data_management'))
    
    if not os.path.exists(import_dir):
        flash(f'❌ Import directory does not exist: {import_dir}', 'error')
        return redirect(url_for('main.data_management'))
    
    try:
        manager = DataManager()
        summary = manager.import_all_data(import_dir, clear_existing=clear_existing)
        
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
        logging.error(f"Import failed: {e}")
        flash(f'❌ Import failed: {str(e)}', 'error')
    
    return redirect(url_for('main.data_management'))

@bp.route('/admin/export-details/<path:export_path>')
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
            if filename.endswith('.json'):
                filepath = os.path.join(export_path, filename)
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

@bp.route('/admin/download-export')
@login_required
@admin_required
def download_export():
    """Download an export as a ZIP file."""
    export_path = request.args.get('path')
    
    if not export_path or not os.path.exists(export_path):
        flash('❌ Export not found', 'error')
        return redirect(url_for('main.data_management'))
    
    try:
        # Create a temporary ZIP file
        import tempfile
        import zipfile
        
        temp_dir = tempfile.mkdtemp()
        zip_filename = f"{export_path}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(export_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, export_path)
                    zipf.write(file_path, arcname)
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        logging.error(f"Download failed: {e}")
        flash(f'❌ Download failed: {str(e)}', 'error')
        return redirect(url_for('main.data_management'))

@bp.route('/admin/delete-export', methods=['POST'])
@login_required
@admin_required
def delete_export():
    """Delete an export directory."""
    try:
        data = request.get_json()
        export_path = data.get('path')
        
        if not export_path or not os.path.exists(export_path):
            return jsonify({'error': 'Export not found'}), 404
        
        # Security check - ensure path is within expected directory
        if not export_path.startswith('data_exports'):
            return jsonify({'error': 'Invalid export path'}), 400
        
        # Delete the directory
        shutil.rmtree(export_path)
        
        return jsonify({'success': True, 'message': f'Export {export_path} deleted successfully'})
        
    except Exception as e:
        logging.error(f"Delete export failed: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/admin/model-details/<table_name>')
@login_required
@admin_required
def model_details_api(table_name):
    """Get detailed information about a specific model."""
    try:
        manager = DataManager()
        
        if table_name not in manager.models:
            return jsonify({'error': 'Model not found'}), 404
        
        model = manager.models[table_name]
        
        # Get sample data (first 5 records)
        sample_records = []
        try:
            records = model.query.limit(5).all()
            for record in records:
                record_dict = {}
                mapper = sqlalchemy_inspect(model)
                for column in mapper.columns:
                    value = getattr(record, column.name)
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    record_dict[column.name] = value
                sample_records.append(record_dict)
        except Exception as e:
            logging.warning(f"Could not fetch sample data for {table_name}: {e}")
        
        # Get model info
        info = manager.get_model_info()
        model_info = info['models'][table_name]
        model_info['sample_data'] = sample_records
        
        return jsonify(model_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/admin/system-status')
@login_required
@admin_required
def system_status():
    """Get system status for the data management interface."""
    try:
        manager = DataManager()
        
        # Database connection test
        try:
            db.session.execute('SELECT 1')
            db_status = 'connected'
        except Exception as e:
            db_status = f'error: {str(e)}'
        
        # Disk space check
        import shutil
        total, used, free = shutil.disk_usage('.')
        
        status = {
            'database': db_status,
            'models_discovered': len(manager.models),
            'disk_space': {
                'total': format_file_size(total),
                'used': format_file_size(used),
                'free': format_file_size(free),
                'usage_percent': round((used / total) * 100, 1)
            },
            'exports_available': len([d for d in os.listdir('.') if d.startswith('data_exports') and os.path.isdir(d)]),
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(status)
        
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

