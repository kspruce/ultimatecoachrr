# app_factory.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_moment import Moment
from config import Config
import os
import logging

# Initialize extensions outside of create_app function
# These objects will be attached to the app later
db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = 'Please log in to access this page.'
csrf = CSRFProtect()
moment = Moment()

def create_app(config_class=Config):
    """Application factory function that creates and configures the Flask app"""
    # Create Flask app
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    csrf.init_app(app)
    moment.init_app(app)
    
    # Ensure the SECRET_KEY is set
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = os.urandom(24)
    
    # Configure static file serving
    app.static_folder = 'static'
    app.static_url_path = '/static'
    
    # Create upload directories
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        # Create subdirectories
        for subdir in ['drills', 'playbook', 'theory', 'temp']:
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], subdir), exist_ok=True)
        
        # Test write permissions
        test_file = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
    except Exception as e:
        app.logger.error(f"Storage initialization error: {str(e)}")
    
    # Register template filters
    @app.template_filter('initials')
    def initials_filter(name):
        """Convert a name to initials."""
        words = name.split()
        return ''.join(word[0].upper() for word in words if word)
    
    @app.template_filter('nl2br')
    def nl2br_filter(s):
        if s is None:
            return ''
        return s.replace('\n', '<br>')
    
    @app.template_filter('tojsonfilter')
    def tojsonfilter(obj):
        return json.dumps(obj)
    
    # Import and register blueprints inside the function to avoid circular imports
    with app.app_context():
        # Register blueprints
        from app.routes.main import bp as main_bp
        app.register_blueprint(main_bp)
        
        from app.routes.calendar_routes import calendar_bp
        app.register_blueprint(calendar_bp)
        
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
        
        from app.routes.clip import bp as clip_bp
        app.register_blueprint(clip_bp)
        
        from app.routes.session import bp as session_bp
        app.register_blueprint(session_bp)
        
        from app.routes.scouting import bp as scouting_bp
        app.register_blueprint(scouting_bp)
        
        from app.routes.playbook import bp as playbook_bp
        app.register_blueprint(playbook_bp)
        
        from app.routes.theory import bp as theory_bp
        app.register_blueprint(theory_bp)
        
        from app.routes.cutting_skill import bp as cutting_skill_bp
        app.register_blueprint(cutting_skill_bp)
        
        from app.routes.data_management_routes import bp as data_management_bp
        app.register_blueprint(data_management_bp)
        
        from app.routes.fitness import bp as fitness_bp
        app.register_blueprint(fitness_bp)
        
        from app.discord.routes import discord_bp
        app.register_blueprint(discord_bp)
        
        from app.routes.gameday import bp as gameday_bp
        app.register_blueprint(gameday_bp)
        
        from app.routes.team_organization import bp as team_organization_bp
        app.register_blueprint(team_organization_bp)
        
        from app.routes.stats_blueprint import stats_dashboard
        app.register_blueprint(stats_dashboard)
        
        # Configure S3
        from app.utils.s3_utils import check_s3_configuration
        if not check_s3_configuration():
            app.logger.warning("S3 storage is not properly configured!")
        
        # Add S3 URL to template context
        @app.context_processor
        def inject_s3_url():
            return {
                's3_bucket_url': f"https://{app.config['AWS_BUCKET_NAME']}.s3.amazonaws.com" if app.config['AWS_BUCKET_NAME'] else None
            }
        
        # Add team info to context
        from app.context_processors import team_info_processor
        app.context_processor(team_info_processor)
        
        # Create database tables
        db.create_all()
    
    # Initialize Discord integration if enabled
    if os.environ.get('DISCORD_ENABLED', 'True') == 'True':
        from app.discord_integration import init_discord_integration
        init_discord_integration(app)
    
    return app
