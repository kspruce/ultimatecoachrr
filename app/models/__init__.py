# app/models/__init__.py

# Core models
from app.models.team_organization import TeamOrganization
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
from app.models.throws import Throw
from app.models.game_player import GamePlayer

# Fitness models (import first; off_season imports FitnessMetric)
from app.models.fitness import FitnessMetric, FitnessRecord

# Video and Analysis models
from app.models.clip import Clip, ClipTag, ClipPointSegment  # include ClipPointSegment
from app.models.annotation import ClipAnnotation, AnnotationTag  # include AnnotationTag
from app.models.scouting import ScoutingReport
from app.models.cutting_skill import CuttingSkill

# Statistics and Export models
from app.models.stats import PlayerPointStats
from app.models.export import ExportLog
from app.models.team_settings import TeamSettings

# Gameday Stats
from app.models.gameday import LineTemplate, LineTemplatePlayer, GameDayEvent, GameDayPlayerStats

# Off-season models (PhaseMetric is defined here)
from app.models.off_season import (
    TrackWorkoutWeek,
    TrainingLevel,
    TrainingCategory,
    ScheduleType,
    OffSeasonPhase,
    PhaseMetric,            # important for FitnessMetric.phase_metrics relationship
    PhaseSchedule,
    ScheduleSession,
    WorkoutPlan,
    UserSessionCompletion,
    SMARTGoal,
    UserSchedulePreference
)

__all__ = [
    # Core
    'TeamOrganization', 'User', 'Player',

    # Drills / Sessions / Playbook / Theory
    'SavedDrill', 'SessionPlan', 'SessionComponent', 'Attendance', 'SessionRSVP',
    'Play', 'Formation', 'PlayTag',
    'TheorySection', 'TheoryTopic', 'TheoryVideo',

    # Games
    'Tournament', 'Game', 'Point', 'LineUp',
    'Event', 'Pull', 'Throw', 'GamePlayer',

    # Video / Annotation
    'Clip', 'ClipTag', 'ClipPointSegment', 'ClipAnnotation', 'AnnotationTag', 'ScoutingReport',
    'CuttingSkill',

    # Stats / Export / Settings
    'PlayerPointStats', 'ExportLog', 'TeamSettings',

    # Fitness (and RELATED off-season link)
    'FitnessMetric', 'FitnessRecord',

    # Gameday
    'LineTemplate', 'LineTemplatePlayer', 'GameDayEvent', 'GameDayPlayerStats',

    # Off-season
    'TrackWorkoutWeek',
    'TrainingLevel', 'TrainingCategory', 'ScheduleType',
    'OffSeasonPhase', 'PhaseMetric', 'PhaseSchedule', 'ScheduleSession', 'WorkoutPlan',
    'UserSessionCompletion', 'SMARTGoal', 'UserSchedulePreference',
]
