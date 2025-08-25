from app_factory import create_app, db
from app.models.user import User

def create_admin_user():
    app = create_app()
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(email='kspruce98@outlook.com').first()
        if admin:
            print('Admin user already exists')
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
        
        print('Admin user created successfully')

if __name__ == '__main__':
    create_admin_user()
