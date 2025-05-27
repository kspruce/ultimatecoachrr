from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config
from flask_wtf.csrf import CSRFProtect
import os

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = 'Please log in to access this page.'
csrf = CSRFProtect()




def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    csrf.init_app(app)  # Initialize CSRF protection
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # Configure static file serving for uploads
    app.static_folder = 'static'
    app.static_url_path = '/static'
    
    def init_filters(app):
        @app.template_filter('initials')
        def initials_filter(name):
            """Convert a name to initials."""
            words = name.split()
            return ''.join(word[0].upper() for word in words if word)
    
    init_filters(app)
    
    # Add custom Jinja2 filters
    @app.template_filter('nl2br')
    def nl2br_filter(s):
        if s is None:
            return ''
        return s.replace('\n', '<br>')

    # Register blueprints
    from app.routes.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    from app.routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.routes.team import bp as team_bp
    app.register_blueprint(team_bp)
    
    from app.routes.tournament import bp as tournament_bp
    app.register_blueprint(tournament_bp)
    
    from app.routes.game import bp as game_bp
    app.register_blueprint(game_bp)
    
    from app.routes.point import bp as point_bp
    app.register_blueprint(point_bp)
    
    from app.routes.stat import bp as stat_bp
    app.register_blueprint(stat_bp)
    
    from app.routes.stats import bp as stats_dashboard_bp
    app.register_blueprint(stats_dashboard_bp)
    
    from app.routes.clip import bp as clip_bp
    app.register_blueprint(clip_bp)
    
    from app.routes.session import bp as session_bp
    app.register_blueprint(session_bp)
    
    from app.routes.scouting import bp as scouting_bp
    app.register_blueprint(scouting_bp)

    from app.routes.drill_routes import drill_bp
    app.register_blueprint(drill_bp)
    
    # Import all models to ensure they're registered with SQLAlchemy
    from app.models.user import User
    from app.models.player import Player
    from app.models.tournament import Tournament
    from app.models.game import Game
    from app.models.point import Point, LineUp
    from app.models.event import Event, Pull
    from app.models.clip import Clip, ClipTag, ClipTagRelation, ClipPlayer
    from app.models.annotation import ClipAnnotation
    from app.models.session import SessionPlan, SessionComponent, SavedDrill, Attendance
    
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
    
    return app

