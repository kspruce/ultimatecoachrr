# add_team.py (modified version)
from app import create_app, db
from app.models.team_organization import TeamOrganization
from app.models.tournament import Tournament
from app.models.game import Game
from app.models.player import Player
from app.models.user import User
from sqlalchemy import text

app = create_app()

def assign_team_to_existing_data():
    with app.app_context():
        print("Starting migration of existing data to team organizations...")
        
        # Get or create default team
        default_team = TeamOrganization.query.filter_by(slug='default-team').first()
        if not default_team:
            print("Creating default team organization...")
            default_team = TeamOrganization(
                name='Default Team',
                slug='default-team',
                description='Default team created during migration'
            )
            db.session.add(default_team)
            db.session.commit()
            print(f"Created default team with ID: {default_team.id}")
        else:
            print(f"Using existing default team with ID: {default_team.id}")
        
        # Update tournaments
        print("Updating tournaments...")
        tournaments_updated = 0
        for tournament in Tournament.query.filter(Tournament.team_organization_id.is_(None)).all():
            tournament.team_organization_id = default_team.id
            tournaments_updated += 1
        print(f"Updated {tournaments_updated} tournaments")
        
        # Update games
        print("Updating games...")
        games_updated = 0
        for game in Game.query.filter(Game.team_organization_id.is_(None)).all():
            game.team_organization_id = default_team.id
            games_updated += 1
        print(f"Updated {games_updated} games")
        
        # Update players
        print("Updating players...")
        players_updated = 0
        for player in Player.query.filter(Player.team_organization_id.is_(None)).all():
            player.team_organization_id = default_team.id
            players_updated += 1
        print(f"Updated {players_updated} players")
        
        # Update users
        print("Updating users...")
        users_updated = 0
        for user in User.query.filter(User.team_organization_id.is_(None)).all():
            user.team_organization_id = default_team.id
            users_updated += 1
        print(f"Updated {users_updated} users")
        
        # Update tournament RSVPs - First check if the column exists
        print("Checking tournament_rsvp table...")
        try:
            # Check if the column exists
            result = db.session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'tournament_rsvp' AND column_name = 'team_organization_id'
            )
            """)).fetchone()
            
            if not result[0]:
                print("Adding team_organization_id column to tournament_rsvp table...")
                db.session.execute(text("""
                ALTER TABLE tournament_rsvp ADD COLUMN team_organization_id INTEGER REFERENCES team_organization(id)
                """))
                db.session.commit()
                print("Column added successfully")
            
            # Now update the records
            print("Updating tournament RSVPs...")
            rsvps_updated = db.session.execute(text("""
            UPDATE tournament_rsvp SET team_organization_id = :team_id WHERE team_organization_id IS NULL
            """), {"team_id": default_team.id}).rowcount
            print(f"Updated {rsvps_updated} tournament RSVPs")
            
        except Exception as e:
            print(f"Error updating tournament RSVPs: {e}")
        
        # Continue with other tables...
        
        # Commit all changes
        try:
            db.session.commit()
            print("All changes committed successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error committing changes: {e}")
            raise

if __name__ == "__main__":
    assign_team_to_existing_data()
