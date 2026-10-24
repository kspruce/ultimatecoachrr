# app/models/__init__.py

# Core models
from app.models.team_organization import TeamOrganization
from app.models.user import User
from app.models.player import Player
from app.models.season import Season, Squad, SeasonRoster

# Drill and Session models
from app.models.drill import SavedDrill, Drill, DrillFrame, DrillDiagram
from app.models.session import (
    SessionPlan,
    SessionComponent,
    Attendance,
    SessionRSVP
)
from app.models.schedule import TrainingSchedule, ScheduleAvailability, SessionTemplate, SessionReminder
from app.models.playbook import Play, Formation, PlayTag, PlayerPosition, PlayAssignment
from app.models.theory import TheorySection, TheoryTopic, TheoryVideo, TheoryTag
from app.models.season_plan import (
    SeasonPlan, SeasonPhase, SeasonWeek, SeasonPage, SeasonMilestone,
    ClassroomSession, ClassroomResource,
)
from app.models.handbook import HandbookPage

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
from app.models.clip_playlist import ClipPlaylist, ClipPlaylistItem
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
from app.models.team_signup_invite import TeamSignupInvite

# Site-wide settings
from app.models.site_settings import SiteSettings

# Coach feedback
from app.models.feedback import PlayerFeedback

# Training programmes (any club's off-season plans, built on the website)
from app.models.programme import (
    Programme, ProgrammeVersion, ProgrammeTrack, ProgrammeWeek, ProgrammeSession, ProgrammeExercise,
    PerformanceTest, ProgrammeMilestone, ProgrammeEnrolment, SessionLog, TestResult,
)

# Getting-started guide
from app.models.onboarding import UserOnboarding

__all__ = [
    # Core
    'TeamOrganization', 'User', 'Player', 'Season', 'Squad', 'SeasonRoster',
    # Drills & Sessions
    'SavedDrill', 'Drill', 'DrillFrame', 'DrillDiagram', 'SessionPlan', 'SessionComponent', 
    'Attendance', 'SessionRSVP',
    'TrainingSchedule', 'ScheduleAvailability', 'SessionTemplate', 'SessionReminder',
    # Season plan
    'SeasonPlan', 'SeasonPhase', 'SeasonWeek', 'SeasonPage', 'SeasonMilestone',
    'ClassroomSession', 'ClassroomResource',
    'HandbookPage',
    # Playbook
    'Play', 'Formation', 'PlayTag', 'PlayerPosition', 'PlayAssignment',
    # Theory
    'TheorySection', 'TheoryTopic', 'TheoryVideo', 'TheoryTag',
    # Tournaments & Games
    'Tournament', 'TournamentRSVP', 'Game', 'Point', 'LineUp',
    # Events & Actions
    'Event', 'Pull', 'Throw', 'GamePlayer',
    # Video & Clips
    'Clip', 'ClipTag', 'ClipPointSegment', 'ClipAnnotation', 'AnnotationTag', 'ClipPlaylist', 'ClipPlaylistItem',
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
    'InviteToken', 'TeamSignupInvite',
    # Site settings
    'SiteSettings',
    # Coach feedback
    'PlayerFeedback',
    # Training programmes
    'Programme', 'ProgrammeVersion', 'ProgrammeTrack', 'ProgrammeWeek', 'ProgrammeSession',
    'ProgrammeExercise', 'PerformanceTest', 'ProgrammeMilestone', 'ProgrammeEnrolment', 'SessionLog',
    'TestResult',
    # Getting-started guide
    'UserOnboarding',
]