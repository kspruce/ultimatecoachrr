import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    def get_database_url():
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            # Handle Heroku-style DATABASE_URL
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            return database_url
        return 'sqlite:///' + os.path.join(basedir, 'app.db')
    
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Debug configuration
    DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'
    
    # Application URL
    BASE_URL = os.environ.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')

    # Team self-registration: set TEAM_REGISTRATION_CODE in env to require a
    # code when new clubs sign up. Leave blank (default) for open registration.
    TEAM_REGISTRATION_CODE = os.environ.get('TEAM_REGISTRATION_CODE', '')
    
    # S3 Configuration
    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_KEY')
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME')
    
    # Flask-Caching configuration
    CACHE_TYPE = "SimpleCache"  # In-memory cache
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes
    
    # Celery configuration using SQLAlchemy as broker
    CELERY_BROKER_URL = f"sqla+{os.environ.get('DATABASE_URL', 'sqlite:///app.db')}"
    CELERY_RESULT_BACKEND = f"db+{os.environ.get('DATABASE_URL', 'sqlite:///app.db')}"
    
    # File Upload Settings
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {
        'image': {'png', 'jpg', 'jpeg', 'gif'},
        'document': {'pdf'},
        'video': {'mp4', 'mov', 'avi'}
    }
    
    # Temporary upload folder for processing
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or '/tmp/uploads'
    # Directory for data exports (can be overridden by environment variable)
    DATA_EXPORT_DIR = os.environ.get('DATA_EXPORT_DIR', '/tmp/data_exports')
    
    # Fallback to temporary directory if DATA_EXPORT_DIR is not writable
    TEMP_EXPORT_DIR = os.environ.get('TEMP_EXPORT_DIR', '/tmp/data_exports')
    
    # Mail settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    ADMINS = [os.environ.get('ADMIN_EMAIL', 'your-email@example.com')]

    @staticmethod
    def init_app(app):
        # Create upload folder and subdirectories
        try:
            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
            for subdir in ['drills', 'playbook', 'theory', 'temp']:
                os.makedirs(os.path.join(Config.UPLOAD_FOLDER, subdir), exist_ok=True)
        except Exception as e:
            app.logger.warning(f"Could not create upload directories: {e}")

        # Validate S3 configuration
        if not all([Config.AWS_ACCESS_KEY, Config.AWS_SECRET_KEY, Config.AWS_BUCKET_NAME]):
            app.logger.warning("S3 configuration incomplete. Some features may not work properly.")
    
    @staticmethod
    def validate_file_type(filename, allowed_types):
        """Validate file extension against allowed types"""
        if '.' not in filename:
            return False
        ext = filename.rsplit('.', 1)[1].lower()
        return ext in Config.ALLOWED_EXTENSIONS.get(allowed_types, set())
    
    @staticmethod
    def get_s3_url(key):
        """Generate S3 URL for a given key"""
        if not all([Config.AWS_BUCKET_NAME, key]):
            return None
        return f"https://{Config.AWS_BUCKET_NAME}.s3.amazonaws.com/{key}"
