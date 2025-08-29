# Create a script called create_missing_tables.py
from app import create_app
from app.models.base import db
from sqlalchemy import inspect, Table, Column, Integer, String, Boolean, ForeignKey

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()
    
    print(f"Existing tables: {existing_tables}")
    
    # Check if team_organization exists
    if 'team_organization' not in existing_tables:
        print("Creating team_organization table...")
        # Create the team_organization table first
        team_org_table = Table(
            'team_organization',
            db.metadata,
            Column('id', Integer, primary_key=True),
            Column('name', String(255), nullable=False),
            Column('description', String(1000)),
            # Add other columns as needed
        )
        team_org_table.create(db.engine)
        print("team_organization table created successfully")
    
    # Check if team_settings exists
    if 'team_settings' not in existing_tables:
        print("Creating team_settings table...")
        # Now create the team_settings table with the foreign key
        team_settings_table = Table(
            'team_settings',
            db.metadata,
            Column('id', Integer, primary_key=True),
            Column('team_id', Integer, ForeignKey('team_organization.id')),
            Column('discord_enabled', Boolean, default=False),
            Column('discord_webhook_url', String(255)),
            Column('discord_bot_token', String(255)),
            Column('discord_guild_id', String(255)),
            Column('discord_calendar_channel_id', String(255)),
            Column('discord_notification_channel_id', String(255)),
            Column('discord_sync_calendar', Boolean, default=False),
            Column('discord_notify_new_events', Boolean, default=False),
            Column('discord_notify_upcoming_events', Boolean, default=False),
            Column('discord_notify_new_items', Boolean, default=False),
        )
        team_settings_table.create(db.engine)
        print("team_settings table created successfully")
    
    print("Database update complete")
