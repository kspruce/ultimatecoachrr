from flask import request, flash, redirect, url_for, render_template
from sqlalchemy.exc import DBAPIError, InternalError
import logging

# Don't import db here - we'll get it from the app parameter
# from app import db  <- Remove this line

logger = logging.getLogger(__name__)

def handle_db_errors(app, db):
    """Register database error handlers for the Flask app."""
    
    @app.before_request
    def check_for_aborted_transaction():
        """Check if the current transaction is aborted and roll it back if needed."""
        try:
            # Try a simple query to check if the transaction is aborted
            db.session.execute("SELECT 1")
        except Exception as e:
            # If we get an error about aborted transaction, roll back
            if "current transaction is aborted" in str(e):
                logger.warning("Detected aborted transaction, rolling back session")
                db.session.rollback()
                
                # Only flash a message if this is not an API or asset request
                path = request.path.lower()
                if not path.startswith('/api/') and not path.startswith('/static/'):
                    flash("A database error occurred and has been automatically resolved. Please try again.", "warning")
    
    @app.errorhandler(DBAPIError)
    def handle_db_error(error):
        """Handle database API errors."""
        logger.error(f"Database error: {error}")
        db.session.rollback()
        
        # Check if this is an API request
        if request.path.startswith('/api/'):
            return {
                'error': 'Database error occurred',
                'message': str(error)
            }, 500
        
        # For regular requests, show an error page
        return render_template('admin/error.html',
                              error_message="A database error occurred. The transaction has been rolled back.",
                              back_url=url_for('admin.index')), 500
    
    @app.errorhandler(InternalError)
    def handle_internal_error(error):
        """Handle internal database errors, including aborted transactions."""
        logger.error(f"Internal database error: {error}")
        db.session.rollback()
        
        # Check if this is an API request
        if request.path.startswith('/api/'):
            return {
                'error': 'Database error occurred',
                'message': str(error)
            }, 500
        
        # For regular requests, show an error page
        return render_template('admin/error.html',
                              error_message="A database error occurred. The transaction has been rolled back.",
                              back_url=url_for('admin.index')), 500
