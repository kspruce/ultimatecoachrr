from app import create_app, db
from app.models import User, Player, Tournament, Game, Point, LineUp, Event, Pull
from app.models import Clip, ClipTag, ClipTagRelation, ClipPlayer, ClipAnnotation
from app.models import ScoutingReport, SessionPlan, SessionComponent, Attendance, SavedDrill
from app.models import PlayerPointStats, ExportLog

app = create_app()

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

if __name__ == '__main__':
    app.run(debug=True)
