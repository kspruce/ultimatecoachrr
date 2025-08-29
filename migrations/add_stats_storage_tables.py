"""
Migration script to add stats storage tables to the database
"""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from app import create_app, db
from app.models.stats_storage import IndexStats, TeamStats, GameStats, PlayerStats

def run_migration():
    """Run the migration to add stats storage tables"""
    app = create_app()
    with app.app_context():
        # Create the tables if they don't exist
        db.create_all()
        print("Stats storage tables created successfully")

if __name__ == "__main__":
    run_migration()