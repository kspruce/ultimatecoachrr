from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(20), default='player')  # Changed default from 'user' to 'player'
    is_admin = db.Column(db.Boolean, default=False)  # Keep for backward compatibility
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player_profile = db.relationship('Player', back_populates='user_account', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def player(self):
        return self.player_profile
        
    # Add role-based properties
    @property
    def is_admin(self):
        return self.role == 'admin' or self.is_admin  # Support both new and old way
        
    @property
    def is_coach(self):
        return self.role == 'coach' or self.is_admin  # Admins have coach privileges
        
    @property
    def is_stat_taker(self):
        return self.role == 'stat_taker' or self.role == 'coach' or self.is_admin  # Stat takers, coaches, and admins can take stats
        
    @property
    def is_player(self):
        return self.role == 'player' or True  # Everyone has player privileges

    def __repr__(self):
        return f'<User {self.username}>'

@login.user_loader
def load_user(id):
    return User.query.get(int(id))
