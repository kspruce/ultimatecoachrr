# app/commands.py
import click
from flask.cli import with_appcontext
from app import db
from app.models.user import User

@click.command('create-admin')
@with_appcontext
def create_admin():
    """Create an admin user"""
    # Check if admin already exists
    admin = User.query.filter_by(email='kspruce98@outlook.com').first()
    if admin:
        click.echo('Admin user already exists')
        return

    # Create admin user
    admin = User(
        username='admin',
        email='kspruce98@outlook.com',
        role='admin',
        is_admin=True
    )
    admin.set_password('Mythago22!')
    
    db.session.add(admin)
    db.session.commit()
    
    click.echo('Admin user created successfully')

