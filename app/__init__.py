from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_caching import Cache
from config import Config
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_moment import Moment
from markupsafe import Markup
import os
import json
import markdown

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = 'Please log in to access this page.'
csrf = CSRFProtect()
moment = Moment()
cache = Cache()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    csrf.init_app(app)
    moment.init_app(app)
    cache.init_app(app)

    # Ensure the SECRET_KEY is set
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = os.urandom(24)

    # Lightweight auto-migration: ensure newer columns exist
    # (covers local runs that bypass the deploy-time migration scripts)
    with app.app_context():
        try:
            from sqlalchemy import inspect as sa_inspect, text as sa_text
            inspector = sa_inspect(db.engine)
            if inspector.has_table('play'):
                play_cols = [c['name'] for c in inspector.get_columns('play')]
                wanted = {
                    'image_url': 'VARCHAR(255)',
                    'sort_order': 'INTEGER',
                }
                for col, ddl in wanted.items():
                    if col not in play_cols:
                        with db.engine.begin() as conn:
                            conn.execute(sa_text(f'ALTER TABLE play ADD COLUMN {col} {ddl}'))
                        app.logger.info(f'Auto-migration: added play.{col} column')
        except Exception as e:
            app.logger.warning(f'Auto-migration check failed (play columns): {e}')

    # Configure S3: warn if not configured, expose s3_bucket_url in templates
    with app.app_context():
        from app.utils.s3_utils import check_s3_configuration
        if not check_s3_configuration():
            app.logger.warning("S3 storage is not properly configured!")

        @app.context_processor
        def inject_s3_url():
            return {
                's3_bucket_url': f"https://{app.config['AWS_BUCKET_NAME']}.s3.amazonaws.com"
                if app.config.get('AWS_BUCKET_NAME')
                else None
            }

    # Configure static file serving
    app.static_folder = 'static'
    app.static_url_path = '/static'

    # Register custom CLI commands
    from commands import register_commands
    register_commands(app)

    # Template filters
    @app.template_filter('initials')
    def initials_filter(name):
        """Convert a name to initials."""
        words = name.split() if name else []
        return ''.join(word[0].upper() for word in words if word)

    @app.template_filter('nl2br')
    def nl2br_filter(s):
        if s is None:
            return ''
        return s.replace('\n', '<br>')

    @app.template_filter('tojsonfilter')
    def tojsonfilter(obj):
        return json.dumps(obj)

    @app.template_filter('markdown')
    def markdown_filter(text):
        if text is None:
            return ''
        md_html = markdown.markdown(
            text,
            extensions=[
                'markdown.extensions.fenced_code',
                'markdown.extensions.tables',
                'markdown.extensions.nl2br',
                'markdown.extensions.sane_lists',
                # attr_list: control image size etc. in markdown, e.g.
                # ![diagram](https://...png){: width="300" }
                'markdown.extensions.attr_list'
            ]
        )
        return Markup(md_html)

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

    from app.routes.stats import bp as stats_dashboard_bp
    app.register_blueprint(stats_dashboard_bp)

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

    from app.routes.gameday import bp as gameday_bp
    app.register_blueprint(gameday_bp)

    from app.routes.team_organization import bp as team_organization_bp
    app.register_blueprint(team_organization_bp)

    # IMPORTANT: Register off_season blueprint
    from app.routes.off_season import bp as off_season_bp
    app.register_blueprint(off_season_bp)

    # Coach feedback blueprint
    from app.routes.feedback import bp as feedback_bp
    app.register_blueprint(feedback_bp)

    # Import the models package so ALL models are registered.
    # This ensures all models are loaded into SQLAlchemy's metadata
    from app import models as app_models  # noqa: F401

    # Create upload directory structure
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
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

    # App context: register context processors
    with app.app_context():
        from app.context_processors import team_info_processor
        app.context_processor(team_info_processor)

        # Only run create_all if explicitly enabled (e.g., local dev).
        # In production and during migrations, rely on Alembic.
        if app.config.get('RUN_CREATE_ALL', False):
            db.create_all()

    # Conditionally enable Discord integration (default False)
    # Set DISCORD_ENABLED=True in env or config to turn it on.
    discord_enabled = str(app.config.get('DISCORD_ENABLED', os.getenv('DISCORD_ENABLED', 'False'))).lower() == 'true'
    if discord_enabled:
        try:
            # Patch the bot class
            from app.discord import fix_bot_class
            fix_bot_class()

            # Register Discord blueprint
            from app.discord.routes import discord_bp
            app.register_blueprint(discord_bp)

            # Initialize Discord integration
            from app.discord_integration import init_discord_integration
            init_discord_integration(app)
        except Exception as e:
            app.logger.error(f"Failed to initialize Discord integration: {e}")
            # Don't crash the app if Discord fails
            pass

    # ── Guest read-only enforcement ───────────────────────────────
    @app.before_request
    def block_guest_writes():
        """
        Guests (role='guest') may browse the site but cannot mutate any data.
        Any non-GET request from a guest is blocked here, before it reaches a route.
        JSON/AJAX callers receive a 403 JSON response; regular form posts get a
        flash message and a redirect back to where they came from.
        """
        from flask_login import current_user
        from flask import request as req, redirect, url_for, flash, jsonify as _jsonify

        if not current_user.is_authenticated:
            return None
        if getattr(current_user, 'role', None) != 'guest':
            return None
        if req.method in ('GET', 'HEAD', 'OPTIONS'):
            return None
        # Allow the logout POST (CSRF-protected form submit)
        if req.endpoint in ('auth.logout', 'auth.login'):
            return None

        # AJAX / JSON callers
        is_ajax = (
            req.is_json
            or req.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in req.headers.get('Accept', '')
        )
        if is_ajax:
            return _jsonify({'success': False, 'message': 'Guest accounts are read-only.'}), 403

        # Regular form submissions
        flash('You are viewing in guest/demo mode — changes cannot be saved.', 'warning')
        return redirect(req.referrer or url_for('main.index'))

    # Register central error handlers last
    from app.error_handlers import register_error_handlers
    register_error_handlers(app)

    return app


# Optional: keep these imports available at module level if elsewhere relies on them
from app.models import User, Player, TeamOrganization  # noqa: E402,F401