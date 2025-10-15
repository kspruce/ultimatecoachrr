# Re-export the single, app-bound extension instances created in app/__init__.py
from app import db, migrate, login, csrf, moment

# Optional: login configuration is already set in app/__init__.py; keep here only if you rely on base.py side-effects
# login.login_view = 'auth.login'
# login.login_message = 'Please log in to access this page.'

__all__ = ['db', 'migrate', 'login', 'csrf', 'moment']

