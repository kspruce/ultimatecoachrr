# app/error_handlers.py
from flask import render_template
from sqlalchemy.exc import SQLAlchemyError
from app import db

def register_error_handlers(app):
    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(error):
        db.session.rollback()
        app.logger.error(f"Database error: {str(error)}", exc_info=True)
        return render_template('error.html', error_message="A database error occurred. Please try again later."), 500
    
    @app.teardown_request
    def teardown_request(exception=None):
        # A failed request leaves nothing half-done. Flask-SQLAlchemy removes
        # the session itself when the app context ends; removing it here too
        # threw away unsaved work in code that briefly opens a request context.
        if exception is not None:
            try:
                db.session.rollback()
            except Exception:
                pass
