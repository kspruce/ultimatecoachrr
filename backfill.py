# backfill.py
import sys
from app import create_app, db
from app.models import (
    Clip, ClipAnnotation, Event, Point, Game, GamePlayer, Throw, Pull, CuttingSkill, LineUp,
    PlayTag, Formation, Play, PlayerPosition, PlayAssignment,
    TheorySection, TheoryTopic, TheoryVideo, TheoryTag
)

app = create_app()

def backfill_with_default(model_class, default_team_id=3):
    """Backfills models that don't have a direct parent by setting a default team_id."""
    updated_count = model_class.query.filter(model_class.team_organization_id.is_(None)).update({
        'team_organization_id': default_team_id
    })
    print(f"Updated {updated_count} {model_class.__name__} records with default team ID {default_team_id}.")

def backfill_child_from_parent(child_model, parent_model, child_fk_attr):
    """
    Efficiently backfills child models from their direct parent.
    This avoids the N+1 query problem by fetching all parents in one go.
    """
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
            
    print(f"Successfully prepared {updated_count} of {len(items_to_update)} {child_model.__name__} records for update.")

def run_backfill():
    """
    Runs the entire backfill process in the correct, dependency-aware order.
    """
    print("--- Step 1: Backfilling top-level models with default ID ---")
    # These models don't have a team-aware parent, so we assign the default.
    backfill_with_default(Clip)
    backfill_with_default(ClipTag)
    backfill_with_default(PlayTag)
    backfill_with_default(Formation)
    backfill_with_default(Play)
    backfill_with_default(PlayerPosition)
    backfill_with_default(TheorySection)
    backfill_with_default(TheoryTag)
    db.session.commit() # Commit after this group

    print("\n--- Step 2: Backfilling child models from their parents (Level 1) ---")
    # These models depend on the models from Step 1.
    backfill_child_from_parent(ClipAnnotation, Clip, 'clip_id')
    backfill_child_from_parent(PlayAssignment, Play, 'play_id')
    backfill_child_from_parent(TheoryTopic, TheorySection, 'section_id')
    db.session.commit()

    print("\n--- Step 3: Backfilling child models from their parents (Level 2) ---")
    # This model depends on TheoryTopic from Step 2.
    backfill_child_from_parent(TheoryVideo, TheoryTopic, 'topic_id')
    db.session.commit()

    print("\n--- Step 4: Backfilling game-related data (must be in order) ---")
    # Point depends on Game (which should already have a team_id)
    print("Backfilling Points from Games...")
    backfill_child_from_parent(Point, Game, 'game_id')
    db.session.commit()

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
    db.session.commit()

    # This model depends directly on Game.
    print("Backfilling GamePlayers from Games...")
    backfill_child_from_parent(GamePlayer, Game, 'game_id')
    db.session.commit()

    print("\nBackfill process complete.")

if __name__ == '__main__':
    with app.app_context():
        run_backfill()
