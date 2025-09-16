
# app/models/user.py
from app import db, login
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(20), default='player')
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    discord_id = db.Column(db.String(64), nullable=True, unique=True)
    
    # Add team organization relationship
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Define relationships
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
        # Use the column value directly instead of is_admin_flag
        return self.role == 'admin' or self._is_admin

    @is_admin.setter
    def is_admin(self, value):
        if value:
            self.role = 'admin'
            self._is_admin = True
        else:
            if self.role == 'admin':
                self.role = 'player'
            self._is_admin = False

    @property
    def is_coach(self):
        return self.role == 'coach' or self.is_admin
        
    @property
    def is_stat_taker(self):
        return self.role == 'stat_taker' or self.is_coach
        
    @property
    def is_player(self):
        return True  # Everyone has player privileges

    def __repr__(self):
        return f'<User {self.username}>'

@login.user_loader
def load_user(id):
    return User.query.get(int(id))
