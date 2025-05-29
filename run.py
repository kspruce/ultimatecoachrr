from app import create_app, db
from app.models import User, Player, Tournament, Game, Point, LineUp, Event, Pull
from app.models import Clip, ClipTag, ClipTagRelation, ClipPlayer, ClipAnnotation
from app.models import ScoutingReport, SessionPlan, SessionComponent, Attendance, SavedDrill
from app.models import PlayerPointStats, ExportLog
from flask import jsonify
import os 
import re

app = create_app()

def fix_postgres_url(url):
    """Fix PostgreSQL URL for SQLAlchemy 1.4+"""
    if url and url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url

# In create_app or where you set up the database
app.config['SQLALCHEMY_DATABASE_URI'] = fix_postgres_url(
    os.environ.get('DATABASE_URL')
)

@app.route('/debug-info')
def debug_info():
    return {
        'port': os.environ.get('PORT'),
        'database_url': app.config['SQLALCHEMY_DATABASE_URI'],
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
    app.run(host="0.0.0.0", port=port, debug=True)
else:
    # This helps Gunicorn find the app
    application = app
    

@app.route('/db-test')
def db_test():
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        return jsonify({
            'database': 'connected',
            'db_uri': app.config['SQLALCHEMY_DATABASE_URI'].split('@')[1] if '@' in app.config['SQLALCHEMY_DATABASE_URI'] else 'sqlite',
            'tables': [str(table) for table in db.metadata.tables.keys()]
        })
    except Exception as e:
        return jsonify({
            'database': 'error',
            'error': str(e),
            'db_uri': app.config['SQLALCHEMY_DATABASE_URI'].split('@')[1] if '@' in app.config['SQLALCHEMY_DATABASE_URI'] else 'sqlite'
        })
