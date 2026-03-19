# app/models/__init__.py

# Core models
from app.models.team_organization import TeamOrganization
from app.models.user import User
from app.models.player import Player

# Drill and Session models
from app.models.drill import SavedDrill, Drill, DrillFrame
from app.models.session import (
    SessionPlan,
    SessionComponent,
    Attendance,
    SessionRSVP
)
from app.models.playbook import Play, Formation, PlayTag, PlayerPosition, PlayAssignment
from app.models.theory import TheorySection, TheoryTopic, TheoryVideo, TheoryTag

# Game and Tournament models
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event, Pull
from app.models.throws import Throw 
from app.models.game_player import GamePlayer
from app.models.fitness import FitnessMetric, FitnessRecord

# Video and Analysis models
from app.models.clip import Clip, ClipTag, ClipPointSegment
from app.models.annotation import ClipAnnotation, AnnotationTag
from app.models.scouting import ScoutingReport, OpponentPlayer, ScoutingClip
from app.models.cutting_skill import CuttingSkill

# Statistics and Export models
from app.models.stats import PlayerPointStats
from app.models.export import ExportLog
from app.models.team_settings import TeamSettings

# Gameday Stats
from app.models.gameday import LineTemplate, LineTemplatePlayer, GameDayEvent, GameDayPlayerStats

# Invite tokens
from app.models.invite_token import InviteToken

# Coach feedback
from app.models.feedback import PlayerFeedback

# Off-Season Training
from app.models.off_season import (
    TrackWorkoutWeek,
    OffSeasonPhase,
    PhaseMetric,
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
    # Drills & Sessions
    'SavedDrill', 'Drill', 'DrillFrame', 'SessionPlan', 'SessionComponent', 
    'Attendance', 'SessionRSVP',
    # Playbook
    'Play', 'Formation', 'PlayTag', 'PlayerPosition', 'PlayAssignment',
    # Theory
    'TheorySection', 'TheoryTopic', 'TheoryVideo', 'TheoryTag',
    # Tournaments & Games
    'Tournament', 'TournamentRSVP', 'Game', 'Point', 'LineUp',
    # Events & Actions
    'Event', 'Pull', 'Throw', 'GamePlayer',
    # Video & Clips
    'Clip', 'ClipTag', 'ClipPointSegment', 'ClipAnnotation', 'AnnotationTag',
    # Scouting
    'ScoutingReport', 'OpponentPlayer', 'ScoutingClip',
    # Stats
    'PlayerPointStats', 'CuttingSkill',
    # Fitness
    'FitnessMetric', 'FitnessRecord', 
    # Game Day
    'LineTemplate', 'LineTemplatePlayer', 'GameDayEvent', 'GameDayPlayerStats', 
    # Settings & Export
    'TeamSettings', 'ExportLog',
    # Invites
    'InviteToken',
    # Coach feedback
    'PlayerFeedback',
    # Off-Season
    'TrackWorkoutWeek', 'OffSeasonPhase', 'PhaseMetric', 'PhaseSchedule',
    'ScheduleSession', 'WorkoutPlan', 'UserSessionCompletion', 'SMARTGoal',
    'UserSchedulePreference'
]