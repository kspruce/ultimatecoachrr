# In a Flask shell or script
from app import db
from app.models.stats_storage import IndexStats, TeamStats, GameStats, PlayerStats

# Check if tables exist
print(IndexStats.__table__.exists(db.engine))
print(TeamStats.__table__.exists(db.engine))
print(GameStats.__table__.exists(db.engine))
print(PlayerStats.__table__.exists(db.engine))
