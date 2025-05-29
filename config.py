import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    
    @staticmethod
    def get_database_url():
        database_url = os.environ.get('DATABASE_URL')
        if database_url and database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url or 'sqlite:///' + os.path.join(basedir, 'app.db')
    
    # Use the property decorator instead of staticmethod for this case
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return self.get_database_url()
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Mail settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    ADMINS = ['your-email@example.com']
    
    # Base directory of the application
    basedir = os.path.abspath(os.path.dirname(__file__))
    
    # Set specific path for drill images
    UPLOAD_FOLDER = os.path.join('C:', os.sep, 'Users', 'kspruce', 'ultimate_coach', 'app', 'static', 'images', 'drills')
    
    # Maximum file size (5MB)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    @staticmethod
    def init_app(app):
        # Create upload folders if they don't exist
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

class DevelopmentConfig(Config):
    DEBUG = True
    # Additional development settings...
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')

class ProductionConfig(Config):
    # For production (e.g., Apptikku), use environment variable
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or Config.UPLOAD_FOLDER
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        database_url = os.environ.get('DATABASE_URL')
        if database_url and database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
