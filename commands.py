# app/commands.py
import os
import click
from flask.cli import with_appcontext
from app import db
from app.models.user import User
from app.utils.data_manager import DataManager
from app.utils.tag_management import register_commands as register_tag_commands
import json

@click.command('create-admin')
@click.option('--email', default=lambda: os.environ.get('ADMIN_EMAIL', ''), prompt='Admin email', help='Admin user email address')
@click.option('--username', default='admin', prompt='Admin username', help='Admin username')
@click.password_option(help='Admin password')
@with_appcontext
def create_admin(email, username, password):
    """Create an admin user (reads ADMIN_EMAIL from env if set)"""
    if not email:
        raise click.UsageError('Email is required. Pass --email or set ADMIN_EMAIL env var.')

    existing = User.query.filter_by(email=email).first()
    if existing:
        click.echo(f'A user with email {email} already exists.')
        return

    admin = User(
        username=username,
        email=email,
        role='admin',
        is_admin=True
    )
    admin.set_password(password)

    db.session.add(admin)
    db.session.commit()

    click.echo(f'Admin user "{username}" ({email}) created successfully.')

@click.command()
@click.option('--output-dir', default='data_exports', help='Directory to save exported data')
@click.option('--timestamp/--no-timestamp', default=True, help='Include timestamp in directory name')
@with_appcontext
def export_data(output_dir, timestamp):
    """Export all model data to JSON files."""
    click.echo("Starting data export...")
    
    manager = DataManager(export_dir=output_dir)
    
    try:
        export_path = manager.export_all_data(timestamp=timestamp)
        click.echo(f"✅ Data export completed successfully!")
        click.echo(f"📁 Export location: {export_path}")
        
        # Show summary
        summary_path = f"{export_path}/export_summary.json"
        with open(summary_path, 'r') as f:
            summary = json.load(f)
        
        click.echo("\n📊 Export Summary:")
        total_records = 0
        for table_name, info in summary.items():
            if isinstance(info, dict) and 'records_exported' in info:
                records = info['records_exported']
                total_records += records
                status = "✅" if records > 0 else "⚠️"
                click.echo(f"  {status} {table_name}: {records} records")
        
        click.echo(f"\n📈 Total records exported: {total_records}")
        
    except Exception as e:
        click.echo(f"❌ Export failed: {e}")
        raise

@click.command()
@click.option('--import-dir', required=True, help='Directory containing exported data')
@click.option('--clear/--no-clear', default=False, help='Clear existing data before import')
@click.confirmation_option(prompt='Are you sure you want to import data? This may modify your database.')
@with_appcontext
def import_data(import_dir, clear):
    """Import data from JSON files into models."""
    click.echo("Starting data import...")
    
    if clear:
        click.echo("⚠️  WARNING: Existing data will be cleared!")
    
    manager = DataManager()
    
    try:
        summary = manager.import_all_data(import_dir, clear_existing=clear)
        
        if summary['status'] == 'completed':
            click.echo("✅ Data import completed successfully!")
        else:
            click.echo(f"❌ Import failed: {summary.get('error', 'Unknown error')}")
            return
        
        # Show summary
        click.echo("\n📊 Import Summary:")
        total_records = 0
        for table_name, info in summary['results'].items():
            if isinstance(info, dict) and 'records_imported' in info:
                records = info['records_imported']
                total_records += records
                status = "✅" if records > 0 else "⚠️"
                click.echo(f"  {status} {table_name}: {records} records")
                
                if 'errors' in info:
                    click.echo(f"    ⚠️  {len(info['errors'])} errors occurred")
        
        click.echo(f"\n📈 Total records imported: {total_records}")
        
    except Exception as e:
        click.echo(f"❌ Import failed: {e}")
        raise

@click.command()
@with_appcontext
def show_models():
    """Show information about discovered models."""
    manager = DataManager()
    info = manager.get_model_info()
    
    click.echo(f"📋 Discovered {info['total_models']} models:")
    click.echo(f"🔄 Processing order: {' → '.join(info['dependency_order'])}")
    
    click.echo("\n📊 Model Details:")
    for table_name, model_info in info['models'].items():
        click.echo(f"\n  📄 {table_name} ({model_info['class_name']})")
        click.echo(f"     Records: {model_info['record_count']}")
        click.echo(f"     Columns: {len(model_info['columns'])}")
        
        if model_info['foreign_keys']:
            click.echo("     Foreign Keys:")
            for fk in model_info['foreign_keys']:
                click.echo(f"       • {fk['column']} → {fk['references']}")

# Register commands with Flask CLI
def register_commands(app):
    """Register custom commands with the Flask app."""
    app.cli.add_command(export_data)
    app.cli.add_command(import_data)
    app.cli.add_command(show_models)
    register_tag_commands(app)
