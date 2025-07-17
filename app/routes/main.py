from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user
from app import db
from app.models.player import Player
from app.models.game import Game
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from datetime import datetime, timedelta

bp = Blueprint('main', __name__)

@bp.route('/')
@bp.route('/index')
def index():
    # Initialize stats and activities
    stats = {
        'active_players_count': 0,
        'games_count': 0,
        'win_rate': 0,
        'next_game_date': None
    }
    
    recent_activities = []
    upcoming_events = []

    if current_user.is_authenticated:
        try:
            # Calculate Quick Stats
            # Active Players Count
            stats['active_players_count'] = Player.query.filter_by(active=True).count()

            # Games Statistics
            current_year = datetime.now().year
            games = Game.query.filter(
                db.extract('year', Game.date) == current_year
            ).all()
            
            stats['games_count'] = len(games)
            if games:
                wins = sum(1 for game in games if game.is_win)
                stats['win_rate'] = round((wins / len(games)) * 100) if len(games) > 0 else 0

            # Next Game
            next_game = Game.query.filter(
                Game.date >= datetime.now()
            ).order_by(Game.date.asc()).first()
            
            if next_game:
                stats['next_game_date'] = next_game.date.strftime('%b %d')

            # Recent Activities
            # Recent Games
            recent_games = Game.query.order_by(Game.date.desc()).limit(3).all()
            for game in recent_games:
                recent_activities.append({
                    'type': 'game',
                    'icon': 'bi-trophy',
                    'title': f'Game vs {game.opponent}',
                    'timestamp': game.date.strftime('%b %d, %Y'),
                    'link': url_for('game.detail', game_id=game.id)
                })

            # Recent Practice Sessions
            recent_sessions = SessionPlan.query.order_by(
                SessionPlan.date.desc()
            ).limit(3).all()
            
            for session in recent_sessions:
                recent_activities.append({
                    'type': 'practice',
                    'icon': 'bi-calendar-check',
                    'title': f'Practice: {session.title}',
                    'timestamp': session.date.strftime('%b %d, %Y'),
                    'link': url_for('session.detail', session_id=session.id)
                })

            # Recent Tournament Activities
            recent_tournaments = Tournament.query.order_by(
                Tournament.start_date.desc()
            ).limit(2).all()
            
            for tournament in recent_tournaments:
                recent_activities.append({
                    'type': 'tournament',
                    'icon': 'bi-trophy-fill',
                    'title': f'Tournament: {tournament.name}',
                    'timestamp': tournament.start_date.strftime('%b %d, %Y'),
                    'link': url_for('tournament.detail', tournament_id=tournament.id)
                })

            # Sort activities by date
            recent_activities.sort(
                key=lambda x: datetime.strptime(x['timestamp'], '%b %d, %Y'),
                reverse=True
            )
            recent_activities = recent_activities[:5]  # Keep only the 5 most recent

            # Upcoming Events
            # Future Games
            future_games = Game.query.filter(
                Game.date >= datetime.now()
            ).order_by(Game.date.asc()).limit(3).all()
            
            for game in future_games:
                upcoming_events.append({
                    'type': 'game',
                    'title': f'vs {game.opponent}',
                    'date_time': game.date.strftime('%b %d, %Y - %I:%M %p'),
                    'location': game.location if hasattr(game, 'location') else None,
                    'badge_color': 'danger'
                })

            # Future Practice Sessions
            future_sessions = SessionPlan.query.filter(
                SessionPlan.date >= datetime.now()
            ).order_by(SessionPlan.date.asc()).limit(3).all()
            
            for session in future_sessions:
                upcoming_events.append({
                    'type': 'practice',
                    'title': session.title,
                    'date_time': f"{session.date.strftime('%b %d, %Y')} - {session.formatted_time}",
                    'location': session.location,
                    'badge_color': 'success'
                })

            # Future Tournaments
            future_tournaments = Tournament.query.filter(
                Tournament.start_date >= datetime.now()
            ).order_by(Tournament.start_date.asc()).limit(2).all()
            
            for tournament in future_tournaments:
                upcoming_events.append({
                    'type': 'tournament',
                    'title': tournament.name,
                    'date_time': tournament.start_date.strftime('%b %d, %Y'),
                    'location': tournament.location,
                    'badge_color': 'warning'
                })

            # Sort upcoming events by date
            upcoming_events.sort(
                key=lambda x: datetime.strptime(x['date_time'].split(' - ')[0], '%b %d, %Y')
            )
            upcoming_events = upcoming_events[:5]  # Keep only the 5 most recent

        except Exception as e:
            # Log any errors but don't crash the application
            print(f"Error generating dashboard data: {str(e)}")
            # You might want to add proper logging here

    return render_template('index.html',
                         title='Home',
                         stats=stats,
                         recent_activities=recent_activities,
                         upcoming_events=upcoming_events)

@bp.route('/about')
def about():
    return render_template('about.html', title='About')

@bp.route('/how-to-use')
def how_to_use():
    """Display the How to Use guide page."""
    return render_template('how_to_use.html', title='How to Use Ultimate Coach')
