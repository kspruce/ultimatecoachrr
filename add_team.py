# assign_team_to_existing_data.py
from app import create_app, db
from app.models.team_organization import TeamOrganization
from app.models.tournament import Tournament
from app.models.game import Game
from app.models.player import Player
from app.models.point import Point
from app.models.event import Event, Pull
from app.models.clip import Clip, ClipTag
from app.models.tournament_rsvp import TournamentRSVP
from app.models.game_player import GamePlayer
from app.models.session import SessionPlan, SessionComponent, Attendance
from app.models.fitness import FitnessMetric, FitnessRecord
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
        
        # Update tournament RSVPs
        print("Updating tournament RSVPs...")
        rsvps_updated = 0
        for rsvp in TournamentRSVP.query.filter(TournamentRSVP.team_organization_id.is_(None)).all():
            rsvp.team_organization_id = default_team.id
            rsvps_updated += 1
        print(f"Updated {rsvps_updated} tournament RSVPs")
        
        # Update game players
        print("Updating game players...")
        game_players_updated = 0
        for gp in GamePlayer.query.filter(GamePlayer.team_organization_id.is_(None)).all():
            gp.team_organization_id = default_team.id
            game_players_updated += 1
        print(f"Updated {game_players_updated} game players")
        
        # Update fitness metrics
        print("Updating fitness metrics...")
        metrics_updated = 0
        for metric in FitnessMetric.query.filter(FitnessMetric.team_organization_id.is_(None)).all():
            metric.team_organization_id = default_team.id
            metrics_updated += 1
        print(f"Updated {metrics_updated} fitness metrics")
        
        # Update fitness records
        print("Updating fitness records...")
        records_updated = 0
        for record in FitnessRecord.query.filter(FitnessRecord.team_organization_id.is_(None)).all():
            record.team_organization_id = default_team.id
            records_updated += 1
        print(f"Updated {records_updated} fitness records")
        
        # Update session plans
        print("Updating session plans...")
        sessions_updated = 0
        for session in SessionPlan.query.filter(SessionPlan.team_organization_id.is_(None)).all():
            session.team_organization_id = default_team.id
            sessions_updated += 1
        print(f"Updated {sessions_updated} session plans")
        
        # Update clips
        print("Updating clips...")
        clips_updated = 0
        for clip in Clip.query.filter(Clip.team_organization_id.is_(None)).all():
            clip.team_organization_id = default_team.id
            clips_updated += 1
        print(f"Updated {clips_updated} clips")
        
        # Update clip tags
        print("Updating clip tags...")
        tags_updated = 0
        for tag in ClipTag.query.filter(ClipTag.team_organization_id.is_(None)).all():
            tag.team_organization_id = default_team.id
            tags_updated += 1
        print(f"Updated {tags_updated} clip tags")
        
        # Update points
        print("Updating points...")
        try:
            # Check if points table has team_organization_id column
            result = db.session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'point' AND column_name = 'team_organization_id'
            )
            """)).fetchone()
            
            if result[0]:
                points_updated = db.session.execute(text("""
                UPDATE point SET team_organization_id = :team_id WHERE team_organization_id IS NULL
                """), {"team_id": default_team.id}).rowcount
                print(f"Updated {points_updated} points")
        except Exception as e:
            print(f"Error updating points: {e}")
        
        # Update events
        print("Updating events...")
        try:
            # Check if events table has team_organization_id column
            result = db.session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'event' AND column_name = 'team_organization_id'
            )
            """)).fetchone()
            
            if result[0]:
                events_updated = db.session.execute(text("""
                UPDATE event SET team_organization_id = :team_id WHERE team_organization_id IS NULL
                """), {"team_id": default_team.id}).rowcount
                print(f"Updated {events_updated} events")
        except Exception as e:
            print(f"Error updating events: {e}")
        
        # Update other tables that might have team_organization_id
        tables_to_check = [
            'attendance', 'session_component', 'session_rsvp', 'line_template',
            'line_template_player', 'gameday_event', 'gameday_player_stats',
            'player_point_stats', 'export_log', 'scouting_report', 'opponent_player',
            'scouting_clip', 'saved_drill'
        ]
        
        for table in tables_to_check:
            try:
                # Check if table exists and has team_organization_id column
                result = db.session.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = '{table}' AND column_name = 'team_organization_id'
                )
                """)).fetchone()
                
                if result and result[0]:
                    rows_updated = db.session.execute(text(f"""
                    UPDATE "{table}" SET team_organization_id = :team_id WHERE team_organization_id IS NULL
                    """), {"team_id": default_team.id}).rowcount
                    print(f"Updated {rows_updated} rows in {table}")
            except Exception as e:
                print(f"Error updating {table}: {e}")
        
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
