#!/usr/bin/env python3

from app import db, create_app
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError, OperationalError
import inspect
import sys

def get_all_models():
    """Discover all SQLAlchemy models in the application."""
    from app import models  # Import all your models
    
    # This will hold all discovered models
    discovered_models = []
    
    # Inspect all modules in the models package
    for module_name in dir(models):
        module = getattr(models, module_name)
        
        # Look for classes in each module
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Check if it's a SQLAlchemy model
            if hasattr(obj, '__tablename__') and issubclass(obj, db.Model):
                discovered_models.append(obj)
    
    return discovered_models

def reset_sequence_for_model(model):
    """Reset the sequence for a specific model."""
    table_name = model.__tablename__
    
    # Check if the model has an auto-incrementing primary key
    has_autoincrement_pk = False
    pk_column = None
    
    for column in model.__table__.columns:
        if column.primary_key and column.autoincrement:
            has_autoincrement_pk = True
            pk_column = column.name
            break
    
    if not has_autoincrement_pk:
        print(f"⚠️ Table {table_name} does not have an auto-incrementing primary key, skipping.")
        return False
    
    try:
        # Use a dedicated connection for each reset
        with db.engine.connect() as conn:
            # Start a transaction
            with conn.begin():
                # Check if table exists
                exists = conn.execute(sa.text(
                    f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
                )).scalar()
                
                if not exists:
                    print(f"⚠️ Table {table_name} does not exist, skipping.")
                    return False
                
                # Get the max ID
                max_id = conn.execute(sa.text(
                    f"SELECT COALESCE(MAX({pk_column}), 0) + 1 FROM {table_name}"
                )).scalar()
                
                # Reset the sequence
                conn.execute(sa.text(
                    f"ALTER SEQUENCE {table_name}_{pk_column}_seq RESTART WITH {max_id}"
                ))
                print(f"✅ Successfully reset sequence for {table_name} to {max_id}")
                return True
    except Exception as e:
        print(f"❌ Failed to reset sequence for {table_name}: {str(e)}")
        return False

def reset_all_sequences():
    """Reset sequences for all models."""
    app = create_app()
    with app.app_context():
        models = get_all_models()
        print(f"Found {len(models)} models to process")
        
        success_count = 0
        failure_count = 0
        
        for model in models:
            print(f"\nProcessing {model.__name__} (table: {model.__tablename__})")
            try:
                if reset_sequence_for_model(model):
                    success_count += 1
                else:
                    failure_count += 1
            except Exception as e:
                print(f"❌ Error processing {model.__name__}: {str(e)}")
                failure_count += 1
        
        print(f"\n=== Summary ===")
        print(f"Successfully reset sequences for {success_count} tables")
        print(f"Failed to reset sequences for {failure_count} tables")

def reset_specific_table(table_name):
    """Reset sequence for a specific table by name."""
    app = create_app()
    with app.app_context():
        # Find the model for this table
        models = get_all_models()
        model = next((m for m in models if m.__tablename__ == table_name), None)
        
        if not model:
            print(f"❌ No model found for table {table_name}")
            return
        
        print(f"Resetting sequence for {model.__name__} (table: {table_name})")
        reset_sequence_for_model(model)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If a table name is provided as an argument, reset just that table
        reset_specific_table(sys.argv[1])
    else:
        # Otherwise reset all tables
        reset_all_sequences()
