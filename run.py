from app import create_app, db
from app.models import User, Player, Tournament, Game, Point, LineUp, Event, Pull
from app.models import Clip, ClipTag, ClipTagRelation, ClipPlayer, ClipAnnotation
from app.models import ScoutingReport, SessionPlan, SessionComponent, Attendance, SavedDrill
from app.models import PlayerPointStats, ExportLog
import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app()

@app.route('/debug-info')
def debug_info():
    try:
        return {
            'port': os.environ.get('PORT'),
            'database_url': app.config.get('SQLALCHEMY_DATABASE_URI', 'not set').replace('://:@', '://****:****@'),
            'environment': os.environ.get('FLASK_ENV', 'not set'),
            'debug': os.environ.get('FLASK_DEBUG', 'not set'),
            'python_path': sys.executable,
            'working_directory': os.getcwd(),
            'upload_folder': app.config.get('UPLOAD_FOLDER', 'not set')
        }
    except Exception as e:
        logger.error(f"Error in debug-info: {str(e)}")
        return {'error': str(e)}

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db, 
        'User': User, 
        'Player': Player,
        'Tournament': Tournament,
        'Game': Game,
        'Point': Point,
        'LineUp': LineUp,
        'Event': Event,
        'Pull': Pull,
        'Clip': Clip,
        'ClipTag': ClipTag,
        'ClipTagRelation': ClipTagRelation,
        'ClipPlayer': ClipPlayer,
        'ClipAnnotation': ClipAnnotation,
        'ScoutingReport': ScoutingReport,
        'SessionPlan': SessionPlan,
        'SessionComponent': SessionComponent,
        'Attendance': Attendance,
        'SavedDrill': SavedDrill,
        'PlayerPointStats': PlayerPointStats,
        'ExportLog': ExportLog
    }

def create_app_instance():
    """Function to create app instance with error handling"""
    try:
        return app
    except Exception as e:
        logger.error(f"Error creating app: {str(e)}")
        raise

# This helps Gunicorn find the app
application = create_app_instance()

if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 5000))
        debug = os.environ.get("FLASK_DEBUG", "0") == "1"
        app.run(host="0.0.0.0", port=port, debug=debug)
    except Exception as e:
        logger.error(f"Error starting app: {str(e)}")
        raise
