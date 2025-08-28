# app/error_handlers.py
from flask import render_template
from sqlalchemy.exc import SQLAlchemyError
from app import db

def register_error_handlers(app):
    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(error):
        db.session.rollback()
        app.logger.error(f"Database error: {str(error)}", exc_info=True)
        return render_template('error.html', error="A database error occurred. Please try again later."), 500
    
    @app.before_request
    def before_request():
        # This ensures we have a fresh session at the start of each request
        pass
    
    @app.teardown_request
    def teardown_request(exception=None):
        if exception is not None:
            try:
                db.session.rollback()
            except:
                pass
        db.session.remove()
