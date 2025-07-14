# app/models/__init__.py

# Core models
from app.models.user import User
from app.models.player import Player

# Drill and Session models
from app.models.drill import SavedDrill
from app.models.session import (
    SessionPlan,
    SessionComponent,
    Attendance,
    SessionRSVP
)
from app.models.playbook import Play, Formation, PlayTag
from app.models.theory import TheorySection, TheoryTopic, TheoryVideo

# Game and Tournament models
from app.models.tournament import Tournament
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event, Pull

# Video and Analysis models
from app.models.clip import Clip, ClipTag, ClipTagRelation, ClipPlayer
from app.models.annotation import ClipAnnotation
from app.models.scouting import ScoutingReport

# Statistics and Export models
from app.models.stats import PlayerPointStats
from app.models.export import ExportLog

# Define which models should be available when importing from models
__all__ = [
    # Core models
    'User',
    'Player',
    
    # Drill and Session models
    'SavedDrill',
    'SessionPlan',
    'SessionComponent',
    'Attendance',
    'SessionRSVP',
    'Play',
    'Formation',
    'PlayTag',
    'TheorySection',
    'TheoryTopic',
    'TheoryVideo',
    
    # Game and Tournament models
    'Tournament',
    'Game',
    'Point',
    'LineUp',
    'Event',
    'Pull',
    
    # Video and Analysis models
    'Clip',
    'ClipTag',
    'ClipTagRelation',
    'ClipPlayer',
    'ClipAnnotation',
    'ScoutingReport',
    
    # Statistics and Export models
    'PlayerPointStats',
    'ExportLog'
]
