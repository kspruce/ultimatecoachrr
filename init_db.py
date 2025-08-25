from app_factory import create_app, db
from app.models.user import User

def init_db():
    app = create_app()
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Check if admin user exists
        admin = User.query.filter_by(username='admin').first()
        if admin is None:
            admin = User(
                username='admin',
                email='admin@example.com',
                role='admin',
                is_admin=True
            )
            admin.set_password('admin')  # Make sure to change this password
            db.session.add(admin)
            db.session.commit()
            print('Admin user created')

if __name__ == '__main__':
    init_db()
