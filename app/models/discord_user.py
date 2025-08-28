from app import db

def add_discord_fields_to_user(app=None):
    """
    Add Discord-related fields to the User model.
    This function should be called during application initialization.
    
    Parameters:
    -----------
    app: Flask
        The Flask application
    """
    from sqlalchemy import Column, String
    from app.models.user import User
    
    # Check if discord_id column already exists
    if not hasattr(User, 'discord_id'):
        # Add discord_id column to User model
        User.discord_id = Column(String(64), nullable=True, unique=True)
        
        # Create or update the column in the database
        if app:
            with app.app_context():
                try:
                    with db.engine.connect() as conn:
                        conn.execute('ALTER TABLE user ADD COLUMN discord_id VARCHAR(64) UNIQUE')
                        db.session.commit()
                except Exception as e:
                    # Column might already exist
                    db.session.rollback()
