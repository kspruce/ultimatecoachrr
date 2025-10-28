"""
Database migration script for enhanced clip and annotation features
This adds the new tables and columns needed for the improved system
"""

from flask_migrate import upgrade
from app import db

def upgrade_database():
    """
    Upgrade database schema to support enhanced clip and annotation features
    Run this after updating your models
    """
    
    # Create new tables
    print("Creating new tables...")
    
    # AnnotationTag table
    db.engine.execute("""
        CREATE TABLE IF NOT EXISTS annotation_tag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50),
            parent_tag_id INTEGER,
            color VARCHAR(7) DEFAULT '#3F51B5',
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            team_organization_id INTEGER,
            FOREIGN KEY (parent_tag_id) REFERENCES annotation_tag(id),
            FOREIGN KEY (team_organization_id) REFERENCES team_organization(id)
        )
    """)
    
    # Annotation-Tag association table
    db.engine.execute("""
        CREATE TABLE IF NOT EXISTS annotation_tag_relation (
            annotation_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (annotation_id, tag_id),
            FOREIGN KEY (annotation_id) REFERENCES clip_annotation(id),
            FOREIGN KEY (tag_id) REFERENCES annotation_tag(id)
        )
    """)
    
    # Annotation-Player association table
    db.engine.execute("""
        CREATE TABLE IF NOT EXISTS annotation_player (
            annotation_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (annotation_id, player_id),
            FOREIGN KEY (annotation_id) REFERENCES clip_annotation(id),
            FOREIGN KEY (player_id) REFERENCES player(id)
        )
    """)
    
    print("Adding new columns to existing tables...")
    
    # Add new columns to clip_annotation table
    try:
        db.engine.execute("ALTER TABLE clip_annotation ADD COLUMN user_id INTEGER")
        db.engine.execute("ALTER TABLE clip_annotation ADD COLUMN title VARCHAR(200)")
        db.engine.execute("ALTER TABLE clip_annotation ADD COLUMN is_key_moment BOOLEAN DEFAULT FALSE")
        db.engine.execute("ALTER TABLE clip_annotation ADD COLUMN visibility VARCHAR(20) DEFAULT 'team'")
        print("✓ Added new columns to clip_annotation")
    except Exception as e:
        print(f"Note: Some columns may already exist - {e}")
    
    # Add new columns to clip table
    try:
        db.engine.execute("ALTER TABLE clip ADD COLUMN created_by_id INTEGER")
        db.engine.execute("ALTER TABLE clip ADD COLUMN is_featured BOOLEAN DEFAULT FALSE")
        db.engine.execute("ALTER TABLE clip ADD COLUMN view_count INTEGER DEFAULT 0")
        print("✓ Added new columns to clip")
    except Exception as e:
        print(f"Note: Some columns may already exist - {e}")
    
    # Update clip_tag table to support hierarchy
    try:
        db.engine.execute("ALTER TABLE clip_tag ADD COLUMN parent_tag_id INTEGER")
        db.engine.execute("ALTER TABLE clip_tag ADD COLUMN color VARCHAR(7) DEFAULT '#3F51B5'")
        db.engine.execute("ALTER TABLE clip_tag ADD COLUMN description TEXT")
        db.engine.execute("ALTER TABLE clip_tag ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
        print("✓ Updated clip_tag table")
    except Exception as e:
        print(f"Note: Some columns may already exist - {e}")
    
    print("\n✓ Database migration completed successfully!")
    print("\nNext steps:")
    print("1. Run: flask populate-tags")
    print("2. Update your models/__init__.py to import AnnotationTag")
    print("3. Restart your Flask application")


def downgrade_database():
    """
    Rollback the database changes (use with caution!)
    """
    print("Rolling back database changes...")
    
    # Drop new tables
    db.engine.execute("DROP TABLE IF EXISTS annotation_player")
    db.engine.execute("DROP TABLE IF EXISTS annotation_tag_relation")
    db.engine.execute("DROP TABLE IF EXISTS annotation_tag")
    
    # Note: SQLite doesn't support DROP COLUMN, so columns remain but will be unused
    print("✓ Rollback completed")


if __name__ == '__main__':
    print("This script should be run through Flask-Migrate or imported into your app")
    print("Usage:")
    print("  flask db migrate -m 'Add enhanced clip and annotation features'")
    print("  flask db upgrade")
