from app import create_app, db
from app.models import (
    User, Player, Tournament, Game, Point, LineUp, Event, Pull,
    Clip, ClipTag, ClipAnnotation,
    ScoutingReport, SessionPlan, SessionComponent, Attendance, SavedDrill,
    PlayerPointStats, ExportLog
)
import os
import logging
from logging.handlers import RotatingFileHandler
import boto3
from botocore.exceptions import ClientError

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup file logging in /tmp
log_dir = '/tmp/logs'
try:
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'ultimate_coach.log'),
        maxBytes=10240,
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
except Exception as e:
    print(f"Could not set up file logging: {e}")
    # Continue without file logging

logger.info('Ultimate Coach startup')

app = create_app()
application = app  # for WSGI servers

def check_aws_credentials():
    """Verify AWS credentials are working"""
    try:
        if not all([
            app.config.get('AWS_ACCESS_KEY'),
            app.config.get('AWS_SECRET_KEY'),
            app.config.get('AWS_BUCKET_NAME')
        ]):
            logger.warning("AWS credentials not fully configured")
            return False

        s3 = boto3.client(
            's3',
            aws_access_key_id=app.config['AWS_ACCESS_KEY'],
            aws_secret_access_key=app.config['AWS_SECRET_KEY'],
            region_name=app.config['AWS_REGION']
        )
        
        # Try to list objects in bucket to verify credentials
        s3.list_objects_v2(Bucket=app.config['AWS_BUCKET_NAME'], MaxKeys=1)
        logger.info("AWS credentials verified successfully")
        return True
    except ClientError as e:
        logger.error(f"AWS credential verification failed: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking AWS credentials: {str(e)}")
        return False

def ensure_upload_directories():
    """Ensure all required upload directories exist"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        # Create subdirectories
        for subdir in ['drills', 'playbook', 'theory', 'temp']:
            subdir_path = os.path.join(upload_folder, subdir)
            os.makedirs(subdir_path, exist_ok=True)
            
        logger.info(f"Upload directories created successfully in {upload_folder}")
        return True
    except Exception as e:
        logger.error(f"Error creating upload directories: {str(e)}")
        return False

@app.shell_context_processor
def make_shell_context():
    """Make common objects available in Flask shell"""
    return {
        'db': db, 
        'User': User, 
        'Player': Player,
        'Tournament': Tournament,
        'Game': Game,
        'Point': Point,
        'LineUp': LineUp,
        'Event': Event,
        'Pull': Pull,
        'Clip': Clip,
        'ClipTag': ClipTag,
        'ClipAnnotation': ClipAnnotation,
        'ScoutingReport': ScoutingReport,
        'SessionPlan': SessionPlan,
        'SessionComponent': SessionComponent,
        'Attendance': Attendance,
        'SavedDrill': SavedDrill,
        'PlayerPointStats': PlayerPointStats,
        'ExportLog': ExportLog
    }

def initialize_database():
    """
    Handle database setup for both fresh and existing databases.
    - Fresh DB: use db.create_all() to build all tables, then stamp Alembic head
    - Existing DB: run flask db upgrade normally
    """
    with app.app_context():
        try:
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(db.engine)
            existing_tables = inspector.get_table_names()

            if not existing_tables:
                logger.info("Fresh database detected — running db.create_all()")
                db.create_all()
                from flask_migrate import stamp
                stamp()
                logger.info("Database initialised and stamped at migration head")
            else:
                logger.info("Existing database detected — running migrations")
                from flask_migrate import upgrade
                upgrade()
                logger.info("Database migrations complete")
        except Exception as e:
            logger.error(f"Database initialisation error: {str(e)}")
            raise


def import_users_from_json():
    """
    If user_import.json exists in the app root, import any missing users from it.
    Skips users whose email or username already exists. Runs once on startup.
    """
    import json as _json
    json_path = os.path.join(os.path.dirname(__file__), 'user_import.json')
    if not os.path.exists(json_path):
        return

    with app.app_context():
        try:
            from app.models.user import User
            with open(json_path, 'r') as f:
                users_data = _json.load(f)

            imported = 0
            skipped = 0
            for u in users_data:
                email = u.get('email')
                username = u.get('username')
                if not email or not username:
                    continue
                exists = User.query.filter(
                    (User.email == email) | (User.username == username)
                ).first()
                if exists:
                    skipped += 1
                    continue
                new_user = User(
                    username=username,
                    email=email,
                    password_hash=u.get('password_hash'),
                    role=u.get('role', 'player'),
                    is_superadmin=u.get('is_superadmin', False),
                    team_organization_id=u.get('team_organization_id'),
                )
                new_user.is_admin_flag = u.get('is_admin', False)
                db.session.add(new_user)
                imported += 1

            db.session.commit()
            logger.info(f"User import complete: {imported} imported, {skipped} skipped.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"User import failed: {str(e)}")


def ensure_admin_exists():
    """Create an admin user on first boot if ADMIN_EMAIL and ADMIN_PASSWORD
    are set in the environment and no user with that email exists yet."""
    email = os.environ.get('ADMIN_EMAIL')
    password = os.environ.get('ADMIN_PASSWORD')
    if not email or not password:
        return
    with app.app_context():
        try:
            from app.models.user import User
            existing = User.query.filter_by(email=email).first()
            if existing:
                logger.info("Admin user already exists, skipping creation.")
                return
            admin = User(
                username='admin',
                email=email,
                role='admin',
                is_admin_flag=True,
                is_superadmin=True
            )
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            logger.info("Admin user created successfully.")
        except Exception as e:
            logger.error(f"Error ensuring admin exists: {str(e)}")
            db.session.rollback()


def create_app_instance():
    """Function to create app instance with error handling"""
    try:
        # Ensure upload directories exist
        ensure_upload_directories()

        # Initialise database (create tables or run migrations)
        initialize_database()

        # Verify S3 configuration if enabled
        if app.config.get('AWS_ACCESS_KEY'):
            if not check_aws_credentials():
                logger.warning("AWS credentials verification failed")

        # Import users from user_import.json if present
        import_users_from_json()

        # Create admin user if not present
        ensure_admin_exists()

        return app
    except Exception as e:
        logger.error(f"Error creating app: {str(e)}")
        raise

# This helps Gunicorn find the app
application = create_app_instance()

if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 8000))
        debug = os.environ.get("FLASK_DEBUG", "0") == "1"
        
        # Additional startup checks
        with app.app_context():
            # Check database connection
            try:
                db.session.execute('SELECT 1')
                logger.info("Database connection verified")
            except Exception as e:
                logger.error(f"Database connection failed: {str(e)}")
                raise
            
            # Check storage configuration
            if not ensure_upload_directories():
                logger.error("Failed to create required directories")
                raise RuntimeError("Failed to create required directories")
            
            # Check S3 if configured
            if app.config.get('AWS_ACCESS_KEY'):
                if not check_aws_credentials():
                    logger.warning("AWS credentials verification failed")
        
        app.run(host="0.0.0.0", port=port, debug=debug)
    except Exception as e:
        logger.error(f"Error starting app: {str(e)}")
        raise
