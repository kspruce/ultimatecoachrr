from app import create_app, db
from app.models import User, Player, Tournament, Game, Point, LineUp, Event, Pull
from app.models import Clip, ClipTag, ClipTagRelation, ClipPlayer, ClipAnnotation
from app.models import ScoutingReport, SessionPlan, SessionComponent, Attendance, SavedDrill
from app.models import PlayerPointStats, ExportLog
import os 

app = create_app()

@app.route('/debug-info')
def debug_info():
    return {
        'port': os.environ.get('PORT'),
        'database_url': os.environ.get('DATABASE_URL', 'not set'),
        'environment': os.environ.get('FLASK_ENV', 'not set'),
        'debug': os.environ.get('FLASK_DEBUG', 'not set')
    }

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
else:
    # This helps Gunicorn find the app
    application = app
