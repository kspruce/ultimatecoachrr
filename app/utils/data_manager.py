import os
import json
import importlib
import inspect
import logging
from datetime import datetime
from typing import Dict, List, Any, Set
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import class_mapper
from sqlalchemy.exc import IntegrityError
from app import db

class DataManager:
    """
    Comprehensive data export and import manager for Flask SQLAlchemy models.
    Handles relationships, foreign keys, and maintains data integrity.
    """
    
    def __init__(self, export_dir: str = "data_exports"):
        self.export_dir = export_dir
        self.models = {}
        self.dependency_order = []
        self._discover_models()
        self._calculate_dependency_order()
    
    def _discover_models(self):
        """Automatically discover all SQLAlchemy models in the app/models directory."""
        models_path = os.path.join(os.path.dirname(__file__), '..', 'models')
        
        # Get all Python files in the models directory
        model_files = [f[:-3] for f in os.listdir(models_path) 
                      if f.endswith('.py') and f != '__init__.py']
        
        for model_file in model_files:
            try:
                # Import the module
                module = importlib.import_module(f'app.models.{model_file}')
                
                # Find all classes that inherit from db.Model
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        hasattr(obj, '__tablename__') and 
                        issubclass(obj, db.Model)):
                        self.models[obj.__tablename__] = obj
                        
            except ImportError as e:
                logging.warning(f"Could not import model file {model_file}: {e}")
    
    def _calculate_dependency_order(self):
        """Calculate the order in which models should be processed based on foreign key dependencies."""
        dependencies = {}
        
        for table_name, model in self.models.items():
            dependencies[table_name] = set()
            
            # Get foreign key dependencies
            mapper = class_mapper(model)
            for column in mapper.columns:
                if column.foreign_keys:
                    for fk in column.foreign_keys:
                        referenced_table = fk.column.table.name
                        if referenced_table in self.models and referenced_table != table_name:
                            dependencies[table_name].add(referenced_table)
        
        # Topological sort to determine processing order
        self.dependency_order = self._topological_sort(dependencies)
    
    def _topological_sort(self, dependencies: Dict[str, Set[str]]) -> List[str]:
        """Perform topological sort to determine processing order."""
        result = []
        visited = set()
        temp_visited = set()
        
        def visit(node):
            if node in temp_visited:
                # Circular dependency detected, add to result anyway
                return
            if node in visited:
                return
                
            temp_visited.add(node)
            for dependency in dependencies.get(node, set()):
                if dependency in dependencies:  # Only process if it's in our models
                    visit(dependency)
            temp_visited.remove(node)
            visited.add(node)
            result.append(node)
        
        for table_name in dependencies:
            if table_name not in visited:
                visit(table_name)
        
        return result
    
    def export_all_data(self, timestamp: bool = True) -> str:
        """
        Export all data from all models to JSON files.
        
        Args:
            timestamp: Whether to include timestamp in export directory name
            
        Returns:
            Path to the export directory
        """
        # Create export directory
        if timestamp:
            export_path = f"{self.export_dir}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        else:
            export_path = self.export_dir
            
        os.makedirs(export_path, exist_ok=True)
        
        # Export metadata
        metadata = {
            'export_timestamp': datetime.now().isoformat(),
            'models_exported': list(self.models.keys()),
            'dependency_order': self.dependency_order,
            'total_models': len(self.models)
        }
        
        with open(os.path.join(export_path, 'metadata.json'), 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Export each model's data
        export_summary = {}
        
        for table_name in self.models:
            try:
                model = self.models[table_name]
                data = self._export_model_data(model)
                
                # Save to JSON file
                filename = f"{table_name}.json"
                filepath = os.path.join(export_path, filename)
                
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                
                export_summary[table_name] = {
                    'records_exported': len(data),
                    'file': filename
                }
                
                logging.info(f"Exported {len(data)} records from {table_name}")
                
            except Exception as e:
                logging.error(f"Error exporting {table_name}: {e}")
                export_summary[table_name] = {
                    'error': str(e),
                    'records_exported': 0
                }
        
        # Save export summary
        with open(os.path.join(export_path, 'export_summary.json'), 'w') as f:
            json.dump(export_summary, f, indent=2)
        
        logging.info(f"Data export completed. Files saved to: {export_path}")
        return export_path
    
    def _export_model_data(self, model) -> List[Dict[str, Any]]:
        """Export data from a single model."""
        records = model.query.all()
        data = []
        
        for record in records:
            record_dict = {}
            
            # Get all columns
            mapper = sqlalchemy_inspect(model)
            for column in mapper.columns:
                value = getattr(record, column.name)
                # Convert datetime objects to ISO format strings
                if isinstance(value, datetime):
                    value = value.isoformat()
                record_dict[column.name] = value
            
            data.append(record_dict)
        
        return data
    
    def import_all_data(self, import_path: str, clear_existing: bool = False) -> Dict[str, Any]:
        """
        Import data from JSON files into all models.
        
        Args:
            import_path: Path to the directory containing export files
            clear_existing: Whether to clear existing data before import
            
        Returns:
            Dictionary containing import summary
        """
        if not os.path.exists(import_path):
            raise FileNotFoundError(f"Import path does not exist: {import_path}")
        
        # Load metadata
        metadata_path = os.path.join(import_path, 'metadata.json')
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            logging.info(f"Importing data from export created at: {metadata.get('export_timestamp')}")
        
        import_summary = {
            'started_at': datetime.now().isoformat(),
            'clear_existing': clear_existing,
            'results': {}
        }
        
        try:
            # Clear existing data if requested (in reverse dependency order)
            if clear_existing:
                self._clear_all_data()
            
            # Import data in dependency order
            for table_name in self.dependency_order:
                if table_name in self.models:
                    try:
                        result = self._import_model_data(table_name, import_path)
                        import_summary['results'][table_name] = result
                        logging.info(f"Imported {result['records_imported']} records to {table_name}")
                    except Exception as e:
                        logging.error(f"Error importing {table_name}: {e}")
                        import_summary['results'][table_name] = {
                            'error': str(e),
                            'records_imported': 0
                        }
            
            # Commit all changes
            db.session.commit()
            import_summary['status'] = 'completed'
            
        except Exception as e:
            db.session.rollback()
            import_summary['status'] = 'failed'
            import_summary['error'] = str(e)
            logging.error(f"Import failed: {e}")
            raise
        
        import_summary['completed_at'] = datetime.now().isoformat()
        return import_summary
    
    def _import_model_data(self, table_name: str, import_path: str) -> Dict[str, Any]:
        """Import data for a single model."""
        filename = f"{table_name}.json"
        filepath = os.path.join(import_path, filename)
        
        if not os.path.exists(filepath):
            return {'records_imported': 0, 'skipped': 'File not found'}
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        model = self.models[table_name]
        records_imported = 0
        errors = []
        
        for record_data in data:
            try:
                # Convert string dates back to datetime objects
                processed_data = self._process_import_data(model, record_data)
                
                # Create new record
                record = model(**processed_data)
                db.session.add(record)
                records_imported += 1
                
            except Exception as e:
                errors.append(f"Record {record_data.get('id', 'unknown')}: {str(e)}")
        
        # Flush to catch any database errors before final commit
        try:
            db.session.flush()
        except IntegrityError as e:
            db.session.rollback()
            raise Exception(f"Database integrity error: {e}")
        
        result = {'records_imported': records_imported}
        if errors:
            result['errors'] = errors
        
        return result
    
    def _process_import_data(self, model, record_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process and validate data before importing."""
        processed_data = {}
        mapper = sqlalchemy_inspect(model)
        
        for column in mapper.columns:
            column_name = column.name
            if column_name in record_data:
                value = record_data[column_name]
                
                # Handle datetime conversion
                if value and hasattr(column.type, 'python_type'):
                    if column.type.python_type == datetime and isinstance(value, str):
                        try:
                            value = datetime.fromisoformat(value)
                        except ValueError:
                            # Try other common datetime formats
                            from dateutil import parser
                            value = parser.parse(value)
                
                processed_data[column_name] = value
        
        return processed_data
    
    def _clear_all_data(self):
        """Clear all data from all models in reverse dependency order."""
        logging.info("Clearing existing data...")
        
        # Clear in reverse dependency order to avoid foreign key constraints
        for table_name in reversed(self.dependency_order):
            if table_name in self.models:
                model = self.models[table_name]
                try:
                    db.session.query(model).delete()
                    logging.info(f"Cleared data from {table_name}")
                except Exception as e:
                    logging.error(f"Error clearing {table_name}: {e}")
                    raise
        
        db.session.flush()
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about discovered models and their relationships."""
        info = {
            'total_models': len(self.models),
            'models': {},
            'dependency_order': self.dependency_order
        }
        
        for table_name, model in self.models.items():
            mapper = sqlalchemy_inspect(model)
            
            # Get column information
            columns = []
            foreign_keys = []
            
            for column in mapper.columns:
                col_info = {
                    'name': column.name,
                    'type': str(column.type),
                    'nullable': column.nullable,
                    'primary_key': column.primary_key
                }
                columns.append(col_info)
                
                # Check for foreign keys
                if column.foreign_keys:
                    for fk in column.foreign_keys:
                        foreign_keys.append({
                            'column': column.name,
                            'references': f"{fk.column.table.name}.{fk.column.name}"
                        })
            
            info['models'][table_name] = {
                'class_name': model.__name__,
                'columns': columns,
                'foreign_keys': foreign_keys,
                'record_count': model.query.count()
            }
        
        return info
