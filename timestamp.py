from datetime import datetime
from app import create_app, db
from app.models.player import Player

app = create_app()

with app.app_context():

    for p in Player.query.all():
        if not p.created_at:
            p.created_at = datetime.utcnow()

    db.session.commit()

    print("Player timestamps updated successfully.")