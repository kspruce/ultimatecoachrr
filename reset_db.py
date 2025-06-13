from app import create_app, db
from sqlalchemy import text, event
from sqlalchemy.orm import configure_mappers, mapper
from sqlalchemy.exc import SQLAlchemyError
from app.models import *  # Import all models from __init__.py
import logging
from datetime import datetime
import os

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'db_reset_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flag to prevent multiple calls to configure_mappers
_configured_mappers = False

@event.listens_for(mapper, "after_configured")
def setup_mappers():
    global _configured_mappers
    if not _configured_mappers:
        configure_mappers()
        _configured_mappers = True

def create_app_context():
    """Create and return the application context"""
    app = create_app()
    return app.app_context()

def create_initial_sections():
    """Create initial theory sections"""
    try:
        if TheorySection.query.first():
            logger.info("Theory sections already exist, skipping creation.")
            return

        sections = [
            {'name': 'Defense', 'slug': 'defense', 
             'description': 'Master defensive techniques including footwork, positioning, forcing, and guarding resets.', 'order': 1},
            {'name': 'Throwing', 'slug': 'throwing', 
             'description': 'Perfect your throwing technique: release points, angles and tilts, give and go, break side throws.', 'order': 2},
            {'name': 'Cutting', 'slug': 'cutting', 
             'description': 'Learn cutting types, techniques, deep cutting, aerial contests, and triple threat positioning.', 'order': 3},
            {'name': 'Handler Offense', 'slug': 'handler-offense', 
             'description': 'Develop handler movement: dump swing, resets, moment of attack, give-go offense, dishy huck, three handler offense.', 'order': 4}
        ]

        for section_data in sections:
            section = TheorySection(**section_data)
            db.session.add(section)

        db.session.commit()
        logger.info("Successfully created initial theory sections!")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error creating theory sections: {str(e)}")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error creating theory sections: {str(e)}")
        raise

def create_test_users():
    """Create initial test users"""
    try:
        test_users = [
            {'username': 'admin', 'email': 'admin@example.com', 'password': 'password', 'is_admin': True},
            {'username': 'bonus', 'email': 'bonus@example.com', 'password': 'bonusboys', 'is_admin': False},
            {'username': 'coach', 'email': 'coach@example.com', 'password': 'coachpass', 'is_admin': False}
        ]

        for user_data in test_users:
            user = User(
                username=user_data['username'],
                email=user_data['email'],
                is_admin=user_data['is_admin']
            )
            user.set_password(user_data['password'])
            db.session.add(user)
            logger.info(f"Created user: {user_data['username']}")

        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error creating users: {str(e)}")
        raise

def create_test_players():
    """Create test players"""
    try:
        test_players = [
            {"name": "Alice", "jersey_number": "1", "position": "handler", "gender": "female", "gender_match": "female", "team": "team1"},
            {"name": "Bob", "jersey_number": "2", "position": "cutter", "gender": "male", "gender_match": "male", "team": "team1"},
            {"name": "Charlie", "jersey_number": "3", "position": "handler", "gender": "male", "gender_match": "male", "team": "team1"},
            {"name": "David", "jersey_number": "4", "position": "cutter", "gender": "male", "gender_match": "male", "team": "team1"},
            {"name": "Eve", "jersey_number": "5", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "team1"},
            {"name": "Jona", "jersey_number": "8", "position": "cutter", "gender": "female", "gender_match": "female", "team": "team1"},
            {"name": "Mallory", "jersey_number": "10", "position": "handler", "gender": "female", "gender_match": "female", "team": "team1"},
        ]

        for player_data in test_players:
            player = Player(**player_data)
            db.session.add(player)

        db.session.commit()
        logger.info(f"Added {len(test_players)} test players")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error creating players: {str(e)}")
        raise

def verify_database():
    """Verify database contents"""
    try:
        logger.info("\nVerifying database contents:")
        
        # Verify users
        users = User.query.all()
        logger.info("\nUsers:")
        for user in users:
            logger.info(f"- {user.username} (Admin: {user.is_admin})")

        # Verify players
        players = Player.query.all()
        logger.info("\nPlayers:")
        for player in players:
            logger.info(f"- {player.name} (#{player.jersey_number})")

        # Verify theory sections
        sections = TheorySection.query.all()
        logger.info("\nTheory Sections:")
        for section in sections:
            logger.info(f"- {section.name} (slug: {section.slug})")

        return True
    except SQLAlchemyError as e:
        logger.error(f"Database error during verification: {str(e)}")
        return False

def reset_database():
    """Main function to reset and initialize the database"""
    with create_app_context():
        try:
            logger.info("Starting database reset...")
            
            # Drop and recreate all tables
            db.drop_all()
            logger.info("Dropped all tables")
            
            db.create_all()
            logger.info("Created all tables")

            # Create initial data
            create_test_users()
            create_test_players()
            create_initial_sections()

            # Verify the database
            if verify_database():
                logger.info("Database reset completed successfully!")
            else:
                logger.error("Database verification failed!")

        except Exception as e:
            logger.error(f"Fatal error during database reset: {str(e)}")
            raise

if __name__ == "__main__":
    try:
        reset_database()
    except Exception as e:
        logger.error(f"Failed to reset database: {str(e)}")
        exit(1)
