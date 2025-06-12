from app import create_app, db
from app.models import (
    User, Player, Tournament, Game, Point, LineUp, Event, Pull,
    Clip, ClipTag, ClipTagRelation, ClipPlayer, ClipAnnotation,
    ScoutingReport, SessionPlan, SessionComponent, Attendance, SavedDrill,
    PlayerPointStats, ExportLog
)
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import boto3
from botocore.exceptions import ClientError

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add file handler for persistent logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/ultimate_coach.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)

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

@app.route('/debug-info')
def debug_info():
    """Endpoint for debugging deployment issues"""
    try:
        # Check upload directory permissions
        upload_folder = app.config['UPLOAD_FOLDER']
        can_write = os.access(upload_folder, os.W_OK)
        
        # Check S3 configuration
        s3_configured = check_aws_credentials()
        
        # Get directory sizes
        def get_dir_size(path):
            total = 0
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total += os.path.getsize(fp)
            return total / (1024 * 1024)  # Convert to MB
        
        return {
            # System information
            'port': os.environ.get('PORT'),
            'database_url': app.config.get('SQLALCHEMY_DATABASE_URI', 'not set').replace('://:@', '://****:****@'),
            'environment': os.environ.get('FLASK_ENV', 'not set'),
            'debug': os.environ.get('FLASK_DEBUG', 'not set'),
            'python_path': sys.executable,
            'working_directory': os.getcwd(),
            
            # Storage information
            'upload_folder': upload_folder,
            'upload_folder_exists': os.path.exists(upload_folder),
            'upload_folder_writable': can_write,
            'upload_folder_size_mb': get_dir_size(upload_folder) if os.path.exists(upload_folder) else 0,
            
            # S3 configuration
            's3_configured': s3_configured,
            's3_bucket': app.config.get('AWS_BUCKET_NAME', 'not set'),
            's3_region': app.config.get('AWS_REGION', 'not set'),
            
            # Application configuration
            'max_file_size_mb': app.config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024),
            'allowed_extensions': app.config.get('ALLOWED_EXTENSIONS', {}),
            
            # Directory structure
            'upload_subdirs': [
                {
                    'name': d,
                    'exists': os.path.exists(os.path.join(upload_folder, d)),
                    'writable': os.access(os.path.join(upload_folder, d), os.W_OK) if os.path.exists(os.path.join(upload_folder, d)) else False
                }
                for d in ['drills', 'playbook', 'theory', 'temp']
            ]
        }
    except Exception as e:
        logger.error(f"Error in debug-info: {str(e)}")
        return {'error': str(e)}

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
        'ClipTagRelation': ClipTagRelation,
        'ClipPlayer': ClipPlayer,
        'ClipAnnotation': ClipAnnotation,
        'ScoutingReport': ScoutingReport,
        'SessionPlan': SessionPlan,
        'SessionComponent': SessionComponent,
        'Attendance': Attendance,
        'SavedDrill': SavedDrill,
        'PlayerPointStats': PlayerPointStats,
        'ExportLog': ExportLog
    }

def create_app_instance():
    """Function to create app instance with error handling"""
    try:
        # Verify storage configuration
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            logger.error(f"Upload folder does not exist: {app.config['UPLOAD_FOLDER']}")
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            logger.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")
        
        # Verify S3 configuration if enabled
        if app.config.get('AWS_ACCESS_KEY'):
            if not check_aws_credentials():
                logger.warning("AWS credentials verification failed")
        
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
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                logger.error(f"Upload folder does not exist: {app.config['UPLOAD_FOLDER']}")
                raise RuntimeError("Upload folder not found")
            
            # Check S3 if configured
            if app.config.get('AWS_ACCESS_KEY'):
                if not check_aws_credentials():
                    logger.warning("AWS credentials verification failed")
        
        app.run(host="0.0.0.0", port=port, debug=debug)
    except Exception as e:
        logger.error(f"Error starting app: {str(e)}")
        raise
