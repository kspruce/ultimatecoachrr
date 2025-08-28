#!/usr/bin/env python3

import os
import importlib
import inspect
import sys
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError

from app import db, create_app

def discover_models():
    """Discover all SQLAlchemy models in the application."""
    models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'models')
    model_modules = []
    model_classes = []
    
    # Get all Python files in the models directory
    for filename in os.listdir(models_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]  # Remove .py extension
            model_modules.append(module_name)
    
    print(f"Found {len(model_modules)} model modules: {', '.join(model_modules)}")
    
    # Import each module and find model classes
    for module_name in model_modules:
        try:
            module = importlib.import_module(f"app.models.{module_name}")
            
            # Find all classes in the module that are SQLAlchemy models
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if hasattr(obj, '__tablename__') and issubclass(obj, db.Model):
                    model_classes.append(obj)
                    print(f"  - Found model: {obj.__name__} (table: {obj.__tablename__})")
        except ImportError as e:
            print(f"  ⚠️ Could not import module app.models.{module_name}: {e}")
        except Exception as e:
            print(f"  ⚠️ Error processing module app.models.{module_name}: {e}")
    
    return model_classes

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
                exists = conn.execute(text(
                    f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
                )).scalar()
                
                if not exists:
                    print(f"⚠️ Table {table_name} does not exist, skipping.")
                    return False
                
                # Get the max ID
                max_id = conn.execute(text(
                    f"SELECT COALESCE(MAX({pk_column}), 0) + 1 FROM {table_name}"
                )).scalar()
                
                # Reset the sequence
                conn.execute(text(
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
        models = discover_models()
        print(f"\nFound {len(models)} models to process")
        
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
        models = discover_models()
        model = next((m for m in models if m.__tablename__ == table_name), None)
        
        if not model:
            print(f"❌ No model found for table {table_name}")
            
            # Try direct SQL approach as fallback
            try:
                with db.engine.connect() as conn:
                    with conn.begin():
                        # Check if table exists
                        exists = conn.execute(text(
                            f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
                        )).scalar()
                        
                        if not exists:
                            print(f"⚠️ Table {table_name} does not exist")
                            return
                        
                        # Assume 'id' is the primary key column
                        max_id = conn.execute(text(
                            f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table_name}"
                        )).scalar()
                        
                        # Reset the sequence
                        conn.execute(text(
                            f"ALTER SEQUENCE {table_name}_id_seq RESTART WITH {max_id}"
                        ))
                        print(f"✅ Successfully reset sequence for {table_name} to {max_id} (direct SQL)")
            except Exception as e:
                print(f"❌ Failed to reset sequence for {table_name} using direct SQL: {str(e)}")
            return
        
        print(f"Resetting sequence for {model.__name__} (table: {table_name})")
        reset_sequence_for_model(model)

def direct_sql_reset():
    """Reset sequences using direct SQL queries without model discovery."""
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            # Get all tables with ID columns
            tables = conn.execute(text("""
                SELECT 
                    t.table_name 
                FROM 
                    information_schema.tables t
                JOIN 
                    information_schema.columns c ON t.table_name = c.table_name
                WHERE 
                    t.table_schema = 'public' AND 
                    c.column_name = 'id'
            """)).fetchall()
            
            success_count = 0
            failure_count = 0
            
            for table in tables:
                table_name = table[0]
                try:
                    # Use a separate transaction for each table
                    with conn.begin():
                        # Get the max ID
                        max_id = conn.execute(text(
                            f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table_name}"
                        )).scalar()
                        
                        # Reset the sequence
                        conn.execute(text(
                            f"ALTER SEQUENCE {table_name}_id_seq RESTART WITH {max_id}"
                        ))
                        print(f"✅ Successfully reset sequence for {table_name} to {max_id}")
                        success_count += 1
                except Exception as e:
                    print(f"❌ Failed to reset sequence for {table_name}: {str(e)}")
                    failure_count += 1
            
            print(f"\n=== Summary ===")
            print(f"Successfully reset sequences for {success_count} tables")
            print(f"Failed to reset sequences for {failure_count} tables")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--direct-sql":
            print("Using direct SQL approach to reset all sequences")
            direct_sql_reset()
        else:
            # Reset a specific table
            reset_specific_table(sys.argv[1])
    else:
        # Reset all tables
        reset_all_sequences()
