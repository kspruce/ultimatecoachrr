from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config
from flask_wtf.csrf import CSRFProtect
import os
from flask_wtf.csrf import CSRFError
import json
import markdown
from flask_moment import Moment
from app.discord_integration import init_discord_integration

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = 'Please log in to access this page.'
csrf = CSRFProtect()
moment = Moment()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    csrf.init_app(app)
    moment.init_app(app)

    # Ensure the SECRET_KEY is set
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = os.urandom(24)
    
    # Configure S3
    with app.app_context():
        from app.utils.s3_utils import check_s3_configuration
        if not check_s3_configuration():
            app.logger.warning("S3 storage is not properly configured!")
            
        # Add S3 URL to template context
        @app.context_processor
        def inject_s3_url():
            return {
                's3_bucket_url': f"https://{app.config['AWS_BUCKET_NAME']}.s3.amazonaws.com" if app.config['AWS_BUCKET_NAME'] else None
            }
    
    # Configure static file serving
    app.static_folder = 'static'
    app.static_url_path = '/static'
    
    # Register custom commands
    from commands import register_commands
    register_commands(app)    
    
    
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
        # Error handlers
        
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        return jsonify({
            'success': False,
            'message': 'CSRF token missing or invalid'
        }), 400
    
    @app.errorhandler(413)
    def too_large(e):
        return jsonify({
            'success': False,
            'message': f'File too large. Maximum size is {app.config["MAX_CONTENT_LENGTH"] / (1024 * 1024)}MB'
        }), 413
    
    import markdown
    from markupsafe import Markup
    
    @app.template_filter('markdown')
    def markdown_filter(text):
        if text is None:
            return ''
        # Convert markdown to HTML with extensions
        md_html = markdown.markdown(
            text,
            extensions=[
                'markdown.extensions.fenced_code',
                'markdown.extensions.tables',
                'markdown.extensions.nl2br',
                'markdown.extensions.sane_lists'
            ]
        )
        # Return as safe HTML
        return Markup(md_html)


    def ensure_default_metrics_exist(app):
        with app.app_context():
            from app.models.fitness import FitnessMetric, DEFAULT_METRICS
            
            # Check if we have any metrics
            if db.session.query(FitnessMetric).count() == 0:
                # Add default metrics
                for metric_data in DEFAULT_METRICS:
                    metric = FitnessMetric(**metric_data)
                    db.session.add(metric)
                db.session.commit()
                print(f"Added {len(DEFAULT_METRICS)} default fitness metrics")
   
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
    
    #from app.routes.tournament_routes import bp as tournament_calendar_bp
    #app.register_blueprint(tournament_calendar_bp)
    
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

    #from app.routes.drill_routes import drill_bp
    #app.register_blueprint(drill_bp)

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
   
    from app.discord.routes import discord_bp as discord_bp
    app.register_blueprint(discord_bp)
    
    # Import models
    from app.models import (
       User, Player, Tournament, Game, Point, LineUp,
       Event, Pull, Clip, ClipTag, ClipAnnotation,
       SessionPlan, SessionComponent, SavedDrill, Attendance, CuttingSkill,
       FitnessMetric, FitnessRecord  # Add these new models
    )


    # Create upload directory in /tmp
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
        raise
    
    # Create database tables
    with app.app_context():
        db.create_all()
        ensure_default_metrics_exist(app)
    
    init_discord_integration(app)
    
    return app

