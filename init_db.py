from app import create_app, db
from app.models.user import User
from app.models.player import Player
from app.models.tournament import Tournament
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.clip import ClipTag
from datetime import datetime, date

def init_db():
    app = create_app()
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Check if admin user exists
        admin = User.query.filter_by(username='admin').first()
        if admin is None:
            admin = User(username='admin', email='admin@example.com', role='admin')
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created.')
        else:
            print('Admin user already exists.')
        
        # Create some sample players if none exist
        if Player.query.count() == 0:
            players = [
                Player(name='John Smith', position='handler', line_preference='O-line', jersey_number=1, gender_match='male'),
                Player(name='Jane Doe', position='cutter', line_preference='O-line', jersey_number=2, gender_match='female'),
                Player(name='Mike Johnson', position='handler', line_preference='D-line', jersey_number=3, gender_match='male'),
                Player(name='Sarah Williams', position='cutter', line_preference='D-line', jersey_number=4, gender_match='female'),
                Player(name='David Brown', position='hybrid', line_preference='both', jersey_number=5, gender_match='male'),
                Player(name='Emily Davis', position='handler', line_preference='O-line', jersey_number=6, gender_match='female'),
                Player(name='Robert Wilson', position='cutter', line_preference='D-line', jersey_number=7, gender_match='male'),
                Player(name='Lisa Moore', position='hybrid', line_preference='both', jersey_number=8, gender_match='female'),
                Player(name='James Taylor', position='handler', line_preference='O-line', jersey_number=9, gender_match='male'),
                Player(name='Jennifer Garcia', position='cutter', line_preference='O-line', jersey_number=10, gender_match='female'),
                Player(name='Michael Martinez', position='handler', line_preference='D-line', jersey_number=11, gender_match='male'),
                Player(name='Amanda Robinson', position='cutter', line_preference='D-line', jersey_number=12, gender_match='female'),
                Player(name='Daniel Lee', position='hybrid', line_preference='both', jersey_number=13, gender_match='male'),
                Player(name='Jessica White', position='handler', line_preference='O-line', jersey_number=14, gender_match='female'),
            ]
            
            for player in players:
                db.session.add(player)
            
            db.session.commit()
            print(f'{len(players)} sample players created.')
        
        # Create a sample tournament if none exist
        if Tournament.query.count() == 0:
            tournament = Tournament(
                name='Sample Tournament',
                start_date=date.today(),
                end_date=date.today(),
                location='Sample Location',
                season='2023'
            )
            db.session.add(tournament)
            db.session.commit()
            print('Sample tournament created.')
            
            # Create a sample game
            game = Game(
                tournament_id=tournament.id,
                opponent='Sample Opponent',
                our_score=15,
                their_score=12,
                date=date.today()
            )
            db.session.add(game)
            db.session.commit()
            print('Sample game created.')
        
        # Create some clip tags if none exist
        if ClipTag.query.count() == 0:
            tags = [
                ClipTag(name='Zone Offense'),
                ClipTag(name='Zone Defense'),
                ClipTag(name='Handler Movement'),
                ClipTag(name='Cutter Movement'),
                ClipTag(name='Break Throws'),
                ClipTag(name='Hucks'),
                ClipTag(name='Defensive Pressure'),
                ClipTag(name='Endzone Offense'),
                ClipTag(name='Pull Play'),
                ClipTag(name='Transition')
            ]
            
            for tag in tags:
                db.session.add(tag)
            
            db.session.commit()
            print(f'{len(tags)} sample clip tags created.')

if __name__ == '__main__':
    init_db()
