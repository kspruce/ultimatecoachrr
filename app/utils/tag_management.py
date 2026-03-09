"""
Management command to populate default tags for clips and annotations
Run with: flask populate-tags
"""

from app import db
from flask import current_app
from app.models.clip import ClipTag
from app.models.annotation import AnnotationTag


# Video-level tags (for categorizing the footage itself)
VIDEO_TAGS_TREE = [
    {
        "name": "Video Type / Context", "color": "#3F51B5", "children": [
            {"name": "Full Game", "children": [
                {"name": "Our Team vs Opponent"},
                {"name": "Opponent vs Opponent (Scouting)"}
            ]},
            {"name": "Training Session", "children": [
                {"name": "Drills Only"},
                {"name": "Scrimmage"},
                {"name": "Theme-Based Practice"}
            ]},
            {"name": "Highlight / Tactic Showcase", "children": [
                {"name": "Set Plays Showcase"},
                {"name": "Tactical Review / Strategy"}
            ]},
            {"name": "Mixed Footage Compilation"},
            {"name": "Tournament / Competition Video"},
            {"name": "Friendly Game"},
            {"name": "Film Session"}
        ]
    }
]

# Annotation tags (for detailed tactical analysis)
ANNOTATION_TAGS_TREE = [
    {
        "name": "Offense", "color": "#2196F3", "children": [
            {"name": "Handler Movement", "children": [
                {"name": "Reset"},
                {"name": "Upline"},
                {"name": "Give-and-Go"},
            ]},
            {"name": "Cutting", "children": [
                {"name": "Under Cut"},
                {"name": "Deep Cut"},
                {"name": "Break Side Cut"},
            ]},
            {"name": "Throw Types", "children": [
                {"name": "Backhand"},
                {"name": "Forehand"},
                {"name": "Hammer"},
                {"name": "High Release"},
            ]},
            {"name": "Set Plays", "children": [
                {"name": "Horizontal Stack"},
                {"name": "Vertical Stack"},
                {"name": "Split Stack"},
                {"name": "Side Stack"},
            ]},
            {"name": "Endzone Offense"},
        ]
    },
    {
        "name": "Defense", "color": "#F44336", "children": [
            {"name": "Person Defense", "children": [
                {"name": "Force Forehand"},
                {"name": "Force Backhand"},
                {"name": "Straight Up"},
            ]},
            {"name": "Zone Defense", "children": [
                {"name": "3-3-1 Cup"},
                {"name": "Wall"},
                {"name": "Junk"},
            ]},
            {"name": "Help & Switches", "children": [
                {"name": "Poach"},
                {"name": "Flash Poach"},
                {"name": "Switch"},
            ]},
            {"name": "Marks", "children": [
                {"name": "No Break Mark"},
                {"name": "Break Allowed"},
            ]},
            {"name": "Turnovers (Defensive)", "children": [
                {"name": "Block"},
                {"name": "Handblock"},
                {"name": "Interception"},
            ]},
        ]
    },
    {
        "name": "Skills", "color": "#4CAF50", "children": [
            {"name": "Throwing Skills", "children": [
                {"name": "Inside-Out"},
                {"name": "Outside-In"},
                {"name": "Break Throw"},
                {"name": "Huck"},
            ]},
            {"name": "Catching Skills", "children": [
                {"name": "Layout Catch"},
                {"name": "Toe-in Catch"},
                {"name": "High Point"},
            ]},
        ]
    },
    {
        "name": "Situations", "color": "#9C27B0", "children": [
            {"name": "Pulling", "children": [
                {"name": "Pull Hangtime"},
                {"name": "OOB Pull"},
            ]},
            {"name": "Receiving Pull", "children": [
                {"name": "Centering Pass"},
                {"name": "Immediate Huck Receive"},
            ]},
            {"name": "Sideline", "children": [
                {"name": "Trap Sideline"},
                {"name": "Break Trap"},
            ]},
            {"name": "Wind Conditions", "children": [
                {"name": "Upwind"},
                {"name": "Downwind"},
                {"name": "Crosswind"},
            ]},
            {"name": "Weather", "children": [
                {"name": "Rain"},
                {"name": "Heat"},
            ]},
        ]
    },
    {
        "name": "Outcomes", "color": "#FFC107", "children": [
            {"name": "Hold"},
            {"name": "Break (Defensive Score)"},
            {"name": "Goal"},
            {"name": "Assist"},
            {"name": "Turnover (Offensive)"},
            {"name": "Callahan"},
        ]
    },
    {
        "name": "Field Zones", "color": "#009688", "children": [
            {"name": "Backfield"},
            {"name": "Midfield"},
            {"name": "Red Zone"},
            {"name": "End Zone"},
        ]
    },
    {
        "name": "Personnel", "color": "#FF9800", "children": [
            {"name": "O-Line"},
            {"name": "D-Line"},
            {"name": "Mixed Line"},
        ]
    },
    {
        "name": "Errors", "color": "#795548", "children": [
            {"name": "Drop"},
            {"name": "Throwaway"},
            {"name": "Miscommunication"},
            {"name": "Stall Out"},
            {"name": "Travel"},
            {"name": "Foul"},
        ]
    },
    {
        "name": "Tempo", "color": "#607D8B", "children": [
            {"name": "Fast Break"},
            {"name": "Slow It Down"},
            {"name": "Timeout Used"},
        ]
    },
    {
        "name": "Opponent Scouting", "color": "#FF5722", "children": [
            {"name": "Opponent Offense"},
            {"name": "Opponent Defense"},
            {"name": "Opponent Set Plays"},
        ]
    },
]


def populate_clip_tags(team_organization_id=None):
    """Populate default clip (video) tags"""
    def create_tag_recursive(tag_data, parent=None, category=None):
        # Get category from parent or tag data
        tag_category = category or tag_data.get('name')
        
        # Check if tag already exists
        existing_tag = ClipTag.query.filter_by(
            name=tag_data['name'],
            team_organization_id=team_organization_id
        ).first()
        
        if existing_tag:
            return existing_tag
        
        # Create new tag
        tag = ClipTag(
            name=tag_data['name'],
            category=tag_category if not parent else parent.category,
            parent_tag_id=parent.id if parent else None,
            color=tag_data.get('color', '#3F51B5'),
            team_organization_id=team_organization_id,
            is_active=True
        )
        db.session.add(tag)
        db.session.flush()  # Get the ID
        
        # Process children
        if 'children' in tag_data:
            for child_data in tag_data['children']:
                create_tag_recursive(child_data, parent=tag, category=tag_category)
        
        return tag
    
    # Create all video tags
    for root_tag_data in VIDEO_TAGS_TREE:
        create_tag_recursive(root_tag_data)
    
    db.session.commit()
    current_app.logger.debug(f"Created {len(VIDEO_TAGS_TREE)} root clip tag categories")


def populate_annotation_tags(team_organization_id=None):
    """Populate default annotation tags"""
    def create_tag_recursive(tag_data, parent=None, category=None):
        # Get category from parent or tag data
        tag_category = category or tag_data.get('name')
        
        # Check if tag already exists
        existing_tag = AnnotationTag.query.filter_by(
            name=tag_data['name'],
            team_organization_id=team_organization_id
        ).first()
        
        if existing_tag:
            return existing_tag
        
        # Create new tag
        tag = AnnotationTag(
            name=tag_data['name'],
            category=tag_category if not parent else parent.category,
            parent_tag_id=parent.id if parent else None,
            color=tag_data.get('color', '#3F51B5'),
            team_organization_id=team_organization_id,
            is_active=True
        )
        db.session.add(tag)
        db.session.flush()  # Get the ID
        
        # Process children
        if 'children' in tag_data:
            for child_data in tag_data['children']:
                create_tag_recursive(child_data, parent=tag, category=tag_category)
        
        return tag
    
    # Create all annotation tags
    for root_tag_data in ANNOTATION_TAGS_TREE:
        create_tag_recursive(root_tag_data)
    
    db.session.commit()
    current_app.logger.debug(f"Created {len(ANNOTATION_TAGS_TREE)} root annotation tag categories")


def register_commands(app):
    """Register Flask CLI commands"""
    
    @app.cli.command('populate-tags')
    def populate_tags_command():
        """Populate default clip and annotation tags"""
        current_app.logger.debug("Populating clip tags...")
        populate_clip_tags()
        
        current_app.logger.debug("Populating annotation tags...")
        populate_annotation_tags()
        
        current_app.logger.debug("✓ All default tags created successfully!")
    
    @app.cli.command('clear-tags')
    def clear_tags_command():
        """Clear all tags (use with caution!)"""
        if input("Are you sure you want to delete all tags? (yes/no): ").lower() == 'yes':
            ClipTag.query.delete()
            AnnotationTag.query.delete()
            db.session.commit()
            current_app.logger.debug("✓ All tags cleared")
        else:
            current_app.logger.debug("Cancelled")
