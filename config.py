import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    # No built-in fallback: a key that's in the source code lets anyone forge
    # login cookies. create_app() uses a random key (and logs an error) if unset.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
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

    # Login cookies: https only (set SESSION_COOKIE_SECURE=0 to log in over
    # plain http locally), hidden from scripts, left off other sites' posts
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0' if DEBUG else '1') == '1'
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SESSION_COOKIE_HTTPONLY = REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = REMEMBER_COOKIE_SAMESITE = 'Lax'
    # "Remember me" keeps you logged in for 30 days (Flask-Login's default is a year)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    # Form tokens last as long as the login, not Flask-WTF's default hour, so
    # a page left open at a tournament can still save
    WTF_CSRF_TIME_LIMIT = None

    # Shown on the privacy policy (/privacy): who runs the site, how to reach
    # them about personal data, and how long database backups are kept
    SITE_OPERATOR = os.environ.get('SITE_OPERATOR')
    PRIVACY_CONTACT_EMAIL = os.environ.get('PRIVACY_CONTACT_EMAIL') or os.environ.get('ADMIN_EMAIL')
    BACKUP_RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS') or 30)

    # Error reports to Sentry (optional): set SENTRY_DSN from your Sentry project
    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    
    # Application URL
    BASE_URL = os.environ.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')

    # The site's Discord application (one for every team; see app/discord/api.py)
    DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
    DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET')
    DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
    DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY')

    # Reminders, training dates and weekly posts run in the web process
    # (app/scheduler.py); set to 0 to run `flask training-jobs` from cron instead
    SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', '1') != '0'

    # Team sign-up is invite-link only unless a superadmin opens it to
    # everyone (Manage Teams -> Team sign-ups); that switch lives in the DB.

    # Rate limits on login, sign-up and password reset. Limits are counted in
    # memory per server process; set RATELIMIT_STORAGE_URI (e.g. redis://...)
    # to share them between processes.
    RATELIMIT_ENABLED = os.environ.get('RATELIMIT_ENABLED', '1') != '0'
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True

    # How many proxies sit in front of the app (Railway: 1). Needed so rate
    # limits see each visitor's own IP and links in emails use https.
    # Set to 0 when the app is reached directly.
    PROXY_COUNT = int(os.environ.get('PROXY_COUNT', '1'))
    
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
    
    # Mail settings. Email is optional: without it the site
    # still works, and coaches hand out reset links instead. See docs/EMAIL_SETUP.md.
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('1', 'true', 'yes')
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ('1', 'true', 'yes')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    # Or send through an email API over HTTPS (use this when the host blocks
    # SMTP, as Railway does below its Pro plan). Takes priority over SMTP.
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
    # The "From" address, e.g. "Ultimate Coach <coach@yourdomain.com>".
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME')
    # Gets an email when a new team registers (if email is set up)
    ADMINS = [os.environ['ADMIN_EMAIL']] if os.environ.get('ADMIN_EMAIL') else []

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
