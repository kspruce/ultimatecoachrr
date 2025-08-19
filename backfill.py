# backfill.py
import sys
import inspect
import importlib
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.exc import IntegrityError, OperationalError
from app import create_app, db
from app.models.user import TeamOrganization

app = create_app()

def discover_models():
    """
    Automatically discover all SQLAlchemy models in the application.
    Returns a dictionary mapping model names to model classes.
    """
    models = {}
    
    # Import all modules that might contain models
    modules_to_check = [
        'app.models.user',
        'app.models.game',
        'app.models.player',
        'app.models.point',
        'app.models.event',
        'app.models.throws',
        'app.models.stats',
        'app.models.clip',
        'app.models.annotation',
        'app.models.game_player',
        'app.models.cutting_skill',
        'app.models.playbook',
        'app.models.theory',
        'app.models.discord_user',
        'app.models.fitness',
        'app.models.drill',
        'app.models.gameday',
        'app.models.tournament',
        'app.models.session',
        'app.models.export',
        'app.models.tournament_rsvp',
        'app.models.scouting',
        
        # Add any other modules that might contain models
    ]
    
    for module_name in modules_to_check:
        try:
            module = importlib.import_module(module_name)
            # Find all classes in the module that are SQLAlchemy models
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and hasattr(obj, '__tablename__'):
                    models[name] = obj
        except ImportError as e:
            print(f"Warning: Could not import module {module_name}: {e}")
    
    return models

def check_model_has_team_column(model):
    """
    Check if a model has a team_organization_id column.
    Returns True if it does, False otherwise.
    """
    try:
        columns = sqlalchemy_inspect(model).columns
        return 'team_organization_id' in columns
    except Exception as e:
        print(f"Error inspecting model {model.__name__}: {e}")
        return False

def get_valid_team_id():
    """Get a valid team_organization_id from the database."""
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

def find_parent_relationship(model):
    """
    Find potential parent relationships for a model.
    Returns a list of (relationship_name, related_model) tuples.
    """
    relationships = []
    
    # Check all attributes of the model
    for attr_name in dir(model):
        if attr_name.startswith('_'):
            continue
            
        try:
            attr = getattr(model, attr_name)
            # Check if this is a relationship property
            if hasattr(attr, 'prop') and hasattr(attr.prop, 'mapper'):
                related_model = attr.prop.mapper.class_
                # Only consider relationships to models that have team_organization_id
                if check_model_has_team_column(related_model):
                    relationships.append((attr_name, related_model))
        except Exception:
            pass
    
    return relationships

def backfill_model_with_default(model, default_team_id):
    """Backfill a model with a default team ID."""
    try:
        items_to_update = model.query.filter(model.team_organization_id.is_(None)).all()
        if not items_to_update:
            print(f"  No {model.__name__} records need updating.")
            return 0
        
        print(f"  Found {len(items_to_update)} {model.__name__} records to update...")
        updated_count = 0
        
        for item in items_to_update:
            item.team_organization_id = default_team_id
            updated_count += 1
        
        db.session.commit()
        print(f"  Updated {updated_count} {model.__name__} records with team ID {default_team_id}.")
        return updated_count
    except IntegrityError as e:
        db.session.rollback()
        print(f"  ERROR updating {model.__name__}: {str(e)}")
        return 0
    except OperationalError as e:
        db.session.rollback()
        print(f"  ERROR: Database operation failed for {model.__name__}: {str(e)}")
        return 0
    except Exception as e:
        db.session.rollback()
        print(f"  ERROR: Unexpected error updating {model.__name__}: {str(e)}")
        return 0

def backfill_model_from_parent(model, parent_model, relationship_attr):
    """Backfill a model from its parent."""
    try:
        items_to_update = model.query.filter(model.team_organization_id.is_(None)).all()
        if not items_to_update:
            print(f"  No {model.__name__} records need updating.")
            return 0
        
        print(f"  Found {len(items_to_update)} {model.__name__} records to update...")
        updated_count = 0
        
        for item in items_to_update:
            try:
                parent = getattr(item, relationship_attr)
                if parent and parent.team_organization_id:
                    item.team_organization_id = parent.team_organization_id
                    updated_count += 1
            except Exception as e:
                print(f"  Warning: Error processing {model.__name__} {getattr(item, 'id', 'unknown')}: {e}")
        
        db.session.commit()
        print(f"  Updated {updated_count} of {len(items_to_update)} {model.__name__} records.")
        return updated_count
    except IntegrityError as e:
        db.session.rollback()
        print(f"  ERROR updating {model.__name__}: {str(e)}")
        return 0
    except OperationalError as e:
        db.session.rollback()
        print(f"  ERROR: Database operation failed for {model.__name__}: {str(e)}")
        return 0
    except Exception as e:
        db.session.rollback()
        print(f"  ERROR: Unexpected error updating {model.__name__}: {str(e)}")
        return 0

def run_comprehensive_backfill():
    """Run a comprehensive backfill of all models."""
    # Get all models
    print("Discovering models...")
    all_models = discover_models()
    print(f"Found {len(all_models)} models.")
    
    # Check which models have team_organization_id
    models_with_team_column = {}
    models_missing_team_column = []
    
    print("\nChecking models for team_organization_id column...")
    for name, model in all_models.items():
        if check_model_has_team_column(model):
            models_with_team_column[name] = model
            print(f"  ✓ {name} has team_organization_id column")
        else:
            models_missing_team_column.append(name)
            print(f"  ✗ {name} is missing team_organization_id column")
    
    if not models_with_team_column:
        print("No models found with team_organization_id column. Nothing to backfill.")
        return
    
    # Get a valid team ID
    default_team_id = get_valid_team_id()
    
    # First pass: backfill models that don't need a parent
    print("\n--- STEP 1: Backfilling top-level models ---")
    backfilled_models = set()
    
    for name, model in models_with_team_column.items():
        try:
            # Check if this is a top-level model (no foreign keys to other models with team_id)
            if name == 'TeamOrganization':
                print(f"  Skipping {name} (this is the teams table itself)")
                continue
                
            print(f"Backfilling {name}...")
            updated = backfill_model_with_default(model, default_team_id)
            if updated > 0:
                backfilled_models.add(name)
        except Exception as e:
            print(f"  ERROR processing {name}: {str(e)}")
    
    # Second pass: try to backfill models from their parents
    print("\n--- STEP 2: Backfilling models from their parents ---")
    
    # Keep track of models we've tried to backfill from parents
    attempted_parent_backfill = set()
    
    # We'll keep trying until we can't backfill any more models
    while True:
        newly_backfilled = 0
        
        for name, model in models_with_team_column.items():
            if name in attempted_parent_backfill or name == 'TeamOrganization':
                continue
                
            # Find potential parent relationships
            relationships = find_parent_relationship(model)
            if not relationships:
                print(f"  No parent relationships found for {name}")
                attempted_parent_backfill.add(name)
                continue
            
            print(f"Trying to backfill {name} from its parents...")
            for rel_name, parent_model in relationships:
                print(f"  Attempting to use relationship {rel_name} to {parent_model.__name__}")
                updated = backfill_model_from_parent(model, parent_model, rel_name)
                if updated > 0:
                    newly_backfilled += updated
                    backfilled_models.add(name)
                    break
            
            attempted_parent_backfill.add(name)
        
        # If we didn't backfill any new models in this iteration, we're done
        if newly_backfilled == 0:
            break
    
    # Final report
    print("\n=== BACKFILL SUMMARY ===")
    print(f"Total models found: {len(all_models)}")
    print(f"Models with team_organization_id column: {len(models_with_team_column)}")
    print(f"Models missing team_organization_id column: {len(models_missing_team_column)}")
    print(f"Models successfully backfilled: {len(backfilled_models)}")
    
    if models_missing_team_column:
        print("\nThe following models are missing the team_organization_id column:")
        for name in models_missing_team_column:
            print(f"  - {name}")
        print("\nYou may need to add the team_organization_id column to these models and run migrations.")
    
    not_backfilled = set(models_with_team_column.keys()) - backfilled_models - {'TeamOrganization'}
    if not_backfilled:
        print("\nThe following models have the team_organization_id column but could not be backfilled:")
        for name in not_backfilled:
            print(f"  - {name}")
        print("\nYou may need to manually backfill these models or add specific logic to this script.")

if __name__ == '__main__':
    with app.app_context():
        run_comprehensive_backfill()
