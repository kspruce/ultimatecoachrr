# db_manager.py
import os
# Disable Discord integration for database operations
os.environ['DISCORD_ENABLED'] = 'False'

# Import from app_factory instead of app
from app_factory import create_app, db

# Import models directly
from app.models.user import User
from app.models.player import Player
from app.models.tournament import Tournament
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event, Pull
from app.models.clip import Clip, ClipTag
from app.models.session import SessionPlan, SessionComponent, Attendance
from app.models.cutting_skill import CuttingSkill
from app.models.theory import TheorySection
from app.models.fitness import FitnessMetric, FitnessRecord
from app.models.gameday import LineTemplate, LineTemplatePlayer, GameDayEvent, GameDayPlayerStats
from app.models.team_organization import TeamOrganization
from app.models.drill import SavedDrill

from datetime import datetime
import sys
from sqlalchemy import text, inspect
import argparse

# Create app with Discord disabled
app = create_app()

# Rest of your db_manager.py code remains the same
