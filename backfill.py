# backfill.py
import sys
from app import create_app, db
from sqlalchemy.exc import IntegrityError

# Import models directly from their module files
from app.models.clip import Clip
from app.models.annotation import ClipAnnotation
from app.models.event import Event, Pull
from app.models.point import Point, LineUp
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.throws import Throw
from app.models.cutting_skill import CuttingSkill
from app.models.playbook import PlayTag, Formation, Play, PlayerPosition, PlayAssignment
from app.models.theory import TheorySection, TheoryTopic, TheoryVideo, TheoryTag
from app.models.user import TeamOrganization  # Import TeamOrganization to check valid IDs

app = create_app()

def get_valid_team_id():
    """Get a valid team_organization_id from the database."""
    with app.app_context():
        # Get all team IDs
        teams = TeamOrganization.query.all()
        if not teams:
            print("ERROR: No teams found in the database. Please create at least one team first.")
            sys.exit(1)
        
        # Print available teams
        print("Available teams:")
        for team in teams:
            print(f"  ID: {team.id}, Name: {team.name}")
        
        # Use the first team ID as default
        default_team_id = teams[0].id
        print(f"\nUsing team ID {default_team_id} as the default for backfilling.")
        return default_team_id

def backfill_with_default(model_class, default_team_id):
    """Backfills models that don't have a direct parent by setting a default team_id."""
    try:
        items_to_update = model_class.query.filter(model_class.team_organization_id.is_(None)).all()
        if not items_to_update:
            print(f"No {model_class.__name__} records to update.")
            return
        
        print(f"Found {len(items_to_update)} {model_class.__name__} records to update...")
        updated_count = 0
        
        for item in items_to_update:
            item.team_organization_id = default_team_id
            updated_count += 1
        
        db.session.commit()
        print(f"Updated {updated_count} {model_class.__name__} records with team ID {default_team_id}.")
    except IntegrityError as e:
        db.session.rollback()
        print(f"ERROR updating {model_class.__name__}: {str(e)}")
        print("This might be caused by a foreign key constraint violation.")
        return

def backfill_child_from_parent(child_model, parent_model, child_fk_attr):
    """
    Efficiently backfills child models from their direct parent.
    This avoids the N+1 query problem by fetching all parents in one go.
    """
    try:
        items_to_update = child_model.query.filter(child_model.team_organization_id.is_(None)).all()
        
        if not items_to_update:
            print(f"No {child_model.__name__} records to update.")
            return

        print(f"Found {len(items_to_update)} {child_model.__name__} records to update...")
        
        # Get all unique parent IDs needed
        parent_ids = {getattr(item, child_fk_attr) for item in items_to_update if getattr(item, child_fk_attr) is not None}
        
        if not parent_ids:
            print(f"Warning: No valid parent IDs found for {child_model.__name__} records.")
            return

        # Fetch all required parents in a single query
        parents = parent_model.query.filter(parent_model.id.in_(parent_ids)).all()
        parent_map = {parent.id: parent for parent in parents}

        updated_count = 0
        for item in items_to_update:
            parent_id = getattr(item, child_fk_attr)
            parent = parent_map.get(parent_id)
            
            if parent and parent.team_organization_id:
                item.team_organization_id = parent.team_organization_id
                updated_count += 1
            else:
                print(f"Warning: Could not find a parent or team ID for {child_model.__name__} {item.id}", file=sys.stderr)
        
        db.session.commit()        
        print(f"Successfully updated {updated_count} of {len(items_to_update)} {child_model.__name__} records.")
    except IntegrityError as e:
        db.session.rollback()
        print(f"ERROR updating {child_model.__name__}: {str(e)}")
        print("This might be caused by a foreign key constraint violation.")
        return

def run_backfill():
    """
    Runs the entire backfill process in the correct, dependency-aware order.
    """
    # Get a valid team ID to use for default backfilling
    default_team_id = get_valid_team_id()
    
    print("\n--- Step 1: Backfilling top-level models with default ID ---")
    # These models don't have a team-aware parent, so we assign the default.
    try:
        # Check if ClipTag exists
        try:
            from app.models.clip import ClipTag
            backfill_with_default(ClipTag, default_team_id)
        except ImportError:
            print("ClipTag model not found, skipping...")
        
        backfill_with_default(Clip, default_team_id)
        backfill_with_default(PlayTag, default_team_id)
        backfill_with_default(Formation, default_team_id)
        backfill_with_default(Play, default_team_id)
        backfill_with_default(PlayerPosition, default_team_id)
        backfill_with_default(TheorySection, default_team_id)
        backfill_with_default(TheoryTag, default_team_id)
    except Exception as e:
        print(f"Error in Step 1: {str(e)}")
        return

    print("\n--- Step 2: Backfilling child models from their parents (Level 1) ---")
    # These models depend on the models from Step 1.
    try:
        backfill_child_from_parent(ClipAnnotation, Clip, 'clip_id')
        backfill_child_from_parent(PlayAssignment, Play, 'play_id')
        backfill_child_from_parent(TheoryTopic, TheorySection, 'section_id')
    except Exception as e:
        print(f"Error in Step 2: {str(e)}")
        return

    print("\n--- Step 3: Backfilling child models from their parents (Level 2) ---")
    # This model depends on TheoryTopic from Step 2.
    try:
        backfill_child_from_parent(TheoryVideo, TheoryTopic, 'topic_id')
    except Exception as e:
        print(f"Error in Step 3: {str(e)}")
        return

    print("\n--- Step 4: Backfilling game-related data (must be in order) ---")
    try:
        # Point depends on Game (which should already have a team_id)
        print("Backfilling Points from Games...")
        backfill_child_from_parent(Point, Game, 'game_id')

        # These models all depend on Point, which we just backfilled.
        print("Backfilling LineUps from Points...")
        backfill_child_from_parent(LineUp, Point, 'point_id')
        print("Backfilling Events from Points...")
        backfill_child_from_parent(Event, Point, 'point_id')
        print("Backfilling Pulls from Points...")
        backfill_child_from_parent(Pull, Point, 'point_id')
        print("Backfilling Throws from Points...")
        backfill_child_from_parent(Throw, Point, 'point_id')
        print("Backfilling CuttingSkills from Points...")
        backfill_child_from_parent(CuttingSkill, Point, 'point_id')

        # This model depends directly on Game.
        print("Backfilling GamePlayers from Games...")
        backfill_child_from_parent(GamePlayer, Game, 'game_id')
    except Exception as e:
        print(f"Error in Step 4: {str(e)}")
        return

    print("\nBackfill process complete.")

if __name__ == '__main__':
    with app.app_context():
        run_backfill()
