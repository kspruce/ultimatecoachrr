# app/__init__.py
from app_factory import db, migrate, login, csrf, moment, create_app

# Import models to ensure they're registered with SQLAlchemy
from app.models import (
   User, Player, Tournament, Game, Point, LineUp,
   Event, Pull, Clip, ClipTag, ClipAnnotation,
   SessionPlan, SessionComponent, SavedDrill, Attendance, CuttingSkill,
   FitnessMetric, FitnessRecord, 
   LineTemplate, LineTemplatePlayer, GameDayEvent, GameDayPlayerStats
)
