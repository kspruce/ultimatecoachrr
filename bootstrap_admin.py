"""
Minimal admin creation script — does not import the full app.
Run on Railway shell with: /opt/venv/bin/python bootstrap_admin.py
"""
import os
import psycopg2
from werkzeug.security import generate_password_hash

db_url = os.environ.get('DATABASE_URL')
if not db_url:
    raise RuntimeError("DATABASE_URL not set")

# Handle Railway's postgres:// prefix
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)

username = 'admin'
email = 'kspruce98@outlook.com'
password = 'Mythago22!'
pw_hash = generate_password_hash(password)

conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Check if user already exists
cur.execute('SELECT id FROM "user" WHERE email = %s', (email,))
if cur.fetchone():
    print(f'User {email} already exists.')
else:
    cur.execute(
        '''INSERT INTO "user" (username, email, password_hash, role, is_admin, is_superadmin)
           VALUES (%s, %s, %s, %s, %s, %s)''',
        (username, email, pw_hash, 'admin', True, True)
    )
    conn.commit()
    print(f'Admin user created: {email}')

cur.close()
conn.close()
