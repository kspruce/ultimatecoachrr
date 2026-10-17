from flask import Blueprint, render_template, redirect, request, url_for
from app.utils.team_filter import get_current_team_id
from flask_login import current_user
from app import csrf, db, limiter, onboarding
from app.models.player import Player
from app.models.game import Game
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from datetime import date, datetime
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


bp = Blueprint('main', __name__)


def _dashboard_extras(team_id):
    """Results, season numbers, next game and tournament sign-ups for the
    homepage. Kept apart from the older upcoming/activity code above."""
    from app.models.tournament_rsvp import TournamentRSVP

    today = date.today()
    played = (Game.query
              .filter(Game.team_organization_id == team_id,
                      Game.date.isnot(None), Game.date <= today)
              .order_by(Game.date.desc(), Game.id.desc())
              .all())
    # A game with no points scored yet hasn't really been played
    played = [g for g in played if (g.our_score or 0) + (g.their_score or 0) > 0]

    season_games = [g for g in played if g.date.year == today.year]
    wins = sum(1 for g in season_games if g.is_win)
    losses = sum(1 for g in season_games if g.is_loss)
    season = {
        'year': today.year,
        'games': len(season_games),
        'wins': wins,
        'losses': losses,
        'win_rate': round(wins / len(season_games) * 100) if season_games else 0,
        'point_diff': sum((g.our_score or 0) - (g.their_score or 0) for g in season_games),
        # Oldest first, for the little bar chart
        'diffs': [(g.our_score or 0) - (g.their_score or 0) for g in reversed(season_games[:12])],
    }
    recent_results = [{
        'opponent': g.opponent,
        'score': f'{g.our_score}–{g.their_score}',
        'result': 'W' if g.is_win else ('L' if g.is_loss else 'T'),
        'date': g.date,
        'tournament': g.tournament.name if g.tournament else None,
        'link': url_for('game.detail', game_id=g.id),
    } for g in played[:5]]

    next_game = (Game.query
                 .filter(Game.team_organization_id == team_id,
                         Game.date.isnot(None), Game.date >= today,
                         Game.our_score == 0, Game.their_score == 0)
                 .order_by(Game.date.asc(), Game.id.asc())
                 .first())
    later_games = []
    if next_game:
        later_games = (Game.query
                       .filter(Game.team_organization_id == team_id,
                               Game.date == next_game.date, Game.id != next_game.id,
                               Game.our_score == 0, Game.their_score == 0)
                       .order_by(Game.id.asc()).limit(3).all())

    squad = None
    next_tournament = (Tournament.query
                       .filter(Tournament.team_organization_id == team_id,
                               Tournament.start_date.isnot(None), Tournament.start_date >= today)
                       .order_by(Tournament.start_date.asc()).first())
    if next_tournament:
        counts = dict(db.session.query(TournamentRSVP.status, db.func.count(TournamentRSVP.id))
                      .filter(TournamentRSVP.tournament_id == next_tournament.id)
                      .group_by(TournamentRSVP.status).all())
        active = Player.query.filter_by(team_organization_id=team_id, active=True).count()
        attending = counts.get('attending', 0)
        maybe = counts.get('maybe', 0)
        out = counts.get('not_attending', 0)
        squad = {
            'tournament': next_tournament,
            'attending': attending,
            'maybe': maybe,
            'out': out,
            'no_reply': max(active - attending - maybe - out, 0),
            'active': active,
        }

    return {
        'season': season,
        'recent_results': recent_results,
        'next_game': next_game,
        'later_games': later_games,
        'squad': squad,
        'today': today,
    }

@bp.route('/')
@bp.route('/index')
def index():
    # First visit (or a promotion): show the welcome for their role
    if current_user.is_authenticated and onboarding.needs_welcome(current_user):
        return redirect(url_for('onboarding.welcome'))

    # Initialize stats and activities
    stats = {
        'active_players_count': 0,
        'games_count': 0,
        'win_rate': 0,
        'next_game_date': None
    }
    
    recent_activities = []
    upcoming_events = []
    team_name = None
    next_session = None
    next_tournament = None
    extras = {}

    if current_user.is_authenticated:
        try:
            logger.debug("Starting to gather dashboard data")
            
            # Get the team ID for filtering data
            team_id = get_current_team_id()
            logger.debug(f"Current team ID: {team_id}")
            
            # Only proceed if we have a team ID
            if team_id:
                # Debug database records
                logger.debug("Debugging database records:")
                
                # Check for games with NULL dates
                null_date_games = db.session.query(Game).filter(
                    Game.date.is_(None),
                    Game.team_organization_id == team_id
                ).all()
                logger.debug(f"Found {len(null_date_games)} games with NULL dates")
                for game in null_date_games:
                    logger.debug(f"Game ID {game.id} vs {game.opponent} has NULL date")
                
                # Check for sessions with NULL dates
                null_date_sessions = db.session.query(SessionPlan).filter(
                    SessionPlan.date.is_(None),
                    SessionPlan.team_organization_id == team_id
                ).all()
                logger.debug(f"Found {len(null_date_sessions)} sessions with NULL dates")
                for session in null_date_sessions:
                    logger.debug(f"Session ID {session.id}: {session.title} has NULL date")
                
                # Check for tournaments with NULL dates
                null_date_tournaments = db.session.query(Tournament).filter(
                    Tournament.start_date.is_(None),
                    Tournament.team_organization_id == team_id
                ).all()
                logger.debug(f"Found {len(null_date_tournaments)} tournaments with NULL dates")
                for tournament in null_date_tournaments:
                    logger.debug(f"Tournament ID {tournament.id}: {tournament.name} has NULL start_date")

                # Calculate Quick Stats
                # Active Players Count
                stats['active_players_count'] = Player.query.filter_by(
                    active=True,
                    team_organization_id=team_id
                ).count()

                # Check if we have any future events in the database
                future_games_count = Game.query.filter(
                    Game.date >= datetime.now(),
                    Game.team_organization_id == team_id
                ).count()
                future_sessions_count = SessionPlan.query.filter(
                    SessionPlan.date >= datetime.now().date(),
                    SessionPlan.team_organization_id == team_id
                ).count()
                future_tournaments_count = Tournament.query.filter(
                    Tournament.start_date >= datetime.now().date(),
                    Tournament.team_organization_id == team_id
                ).count()
                
                logger.debug(f"Database counts - Games: {future_games_count}, Sessions: {future_sessions_count}, Tournaments: {future_tournaments_count}")

                # Games Statistics
                current_year = datetime.now().year
                games = Game.query.filter(
                    db.extract('year', Game.date) == current_year,
                    Game.team_organization_id == team_id
                ).all()
                
                stats['games_count'] = len(games)
                if games:
                    wins = sum(1 for game in games if game.is_win)
                    stats['win_rate'] = round((wins / len(games)) * 100) if len(games) > 0 else 0
                next_game = Game.query.filter(
                    Game.date >= datetime.now(),
                    Game.team_organization_id == team_id
                ).order_by(Game.date.asc()).first()
                if next_game:
                    stats['next_game_date'] = next_game.date.strftime('%b %d')

                # Recent Activities
                recent_games = Game.query.filter(
                    Game.team_organization_id == team_id
                ).order_by(Game.date.desc()).limit(3).all()
                for game in recent_games:
                    recent_activities.append({
                        'type': 'game', 'icon': 'bi-trophy', 'title': f'Game vs {game.opponent}',
                        'timestamp': game.date.strftime('%b %d, %Y'), 'link': url_for('game.detail', game_id=game.id)
                    })
                recent_sessions = SessionPlan.query.filter(
                    SessionPlan.team_organization_id == team_id
                ).order_by(SessionPlan.date.desc()).limit(3).all()
                for session in recent_sessions:
                    recent_activities.append({
                        'type': 'practice', 'icon': 'bi-calendar-check', 'title': f'Practice: {session.title}',
                        'timestamp': session.date.strftime('%b %d, %Y'), 'link': url_for('session.detail', session_id=session.id)
                    })
                recent_tournaments = Tournament.query.filter(
                    Tournament.team_organization_id == team_id
                ).order_by(Tournament.start_date.desc()).limit(2).all()
                for tournament in recent_tournaments:
                    recent_activities.append({
                        'type': 'tournament', 'icon': 'bi-trophy-fill', 'title': f'Tournament: {tournament.name}',
                        'timestamp': tournament.start_date.strftime('%b %d, %Y'), 'link': url_for('tournament.detail', tournament_id=tournament.id)
                    })
                recent_activities.sort(key=lambda x: datetime.strptime(x['timestamp'], '%b %d, %Y'), reverse=True)
                recent_activities = recent_activities[:5]

                # Upcoming Events
                # Future Games
                future_games = Game.query.filter(
                    Game.date >= date.today(),
                    Game.team_organization_id == team_id
                ).order_by(Game.date.asc()).limit(3).all()
                logger.debug(f"Found {len(future_games)} future games")
                for game in future_games:
                    try:
                        # Check if game.date is None before using strftime
                        if game.date is None:
                            logger.warning(f"Game ID {game.id} vs {game.opponent} has NULL date, skipping")
                            continue
                            
                        logger.debug(f"Processing game: {game.opponent} on {game.date}")
                        upcoming_events.append({
                            'type': 'game',
                            'title': f'vs {game.opponent}',
                            'date_time': game.date.strftime('%b %d, %Y - %I:%M %p'),
                            # Game.date is a date; sessions use datetimes, so match them to sort together
                            'sort_date': datetime.combine(game.date, datetime.min.time()),
                            'location': game.location if hasattr(game, 'location') and game.location else "No location",
                            'badge_color': 'danger',
                            'link': url_for('game.detail', game_id=game.id)
                        })
                    except Exception as e:
                        logger.error(f"Error processing game {game.id}: {str(e)}")
                
                # Future Practice Sessions
                future_sessions = SessionPlan.query.filter(
                    SessionPlan.date >= datetime.now().date(),
                    SessionPlan.team_organization_id == team_id
                ).order_by(SessionPlan.date.asc()).limit(3).all()
                logger.debug(f"Found {len(future_sessions)} future sessions")
                for session in future_sessions:
                    try:
                        # Check if session.date is None
                        if session.date is None:
                            logger.warning(f"Session ID {session.id}: {session.title} has NULL date, skipping")
                            continue
                            
                        # Create a safe sort_datetime
                        if session.start_time:
                            sort_datetime = datetime.combine(session.date, session.start_time)
                        else:
                            sort_datetime = datetime.combine(session.date, datetime.min.time())
                        
                        # Create a safe formatted_time
                        formatted_time = session.formatted_time if hasattr(session, 'formatted_time') else "No time specified"
                        
                        logger.debug(f"Processing session: {session.title} on {session.date}, sort_datetime: {sort_datetime}")
                        
                        upcoming_events.append({
                            'type': 'practice',
                            'title': session.title,
                            'date_time': f"{session.date.strftime('%b %d, %Y')} - {formatted_time}",
                            'sort_date': sort_datetime,
                            'location': session.location if session.location else "No location",
                            'badge_color': 'success',
                            'link': url_for('session.detail', session_id=session.id)
                        })
                    except Exception as e:
                        logger.error(f"Error processing session {session.id}: {str(e)}")
                    
                # Future Tournaments
                future_tournaments = Tournament.query.filter(
                    Tournament.start_date >= datetime.now().date(),
                    Tournament.team_organization_id == team_id
                ).order_by(Tournament.start_date.asc()).limit(2).all()
                logger.debug(f"Found {len(future_tournaments)} future tournaments")
                for tournament in future_tournaments:
                    try:
                        # Check if tournament.start_date is None
                        if tournament.start_date is None:
                            logger.warning(f"Tournament ID {tournament.id}: {tournament.name} has NULL start_date, skipping")
                            continue
                            
                        sort_datetime = datetime.combine(tournament.start_date, datetime.min.time())
                        
                        # Check if formatted_date_range exists and is not None
                        formatted_date = tournament.formatted_date_range if hasattr(tournament, 'formatted_date_range') and tournament.formatted_date_range else tournament.start_date.strftime('%b %d, %Y')
                        
                        logger.debug(f"Processing tournament: {tournament.name} on {tournament.start_date}, sort_datetime: {sort_datetime}")
                        
                        upcoming_events.append({
                            'type': 'tournament',
                            'title': tournament.name,
                            'date_time': formatted_date,
                            'sort_date': sort_datetime,
                            'location': tournament.location if tournament.location else "No location",
                            'badge_color': 'warning',
                            'link': url_for('tournament.detail', tournament_id=tournament.id)
                        })
                    except Exception as e:
                        logger.error(f"Error processing tournament {tournament.id}: {str(e)}")
                
                logger.debug(f"Total upcoming events before sorting: {len(upcoming_events)}")

                # Only try to sort if we have events
                if upcoming_events:
                    # Debug each event's sort_date before sorting
                    for i, event in enumerate(upcoming_events):
                        logger.debug(f"Event {i}: {event['title']} - sort_date: {event['sort_date']} - type: {type(event['sort_date'])}")

                    # Sort upcoming events by the actual date object, not a string
                    try:
                        upcoming_events.sort(key=lambda x: x['sort_date'])
                        logger.debug("Events sorted successfully")
                    except Exception as e:
                        logger.error(f"Error sorting events: {str(e)}")
                        # Don't empty the list on error, just leave it unsorted

                    upcoming_events = upcoming_events[:5]
                    logger.debug(f"Final upcoming events count: {len(upcoming_events)}")
                else:
                    logger.warning("No upcoming events to sort")
                
                # Get team name for display
                from app.models.team_organization import TeamOrganization
                team = TeamOrganization.query.get(team_id)
                if team:
                    team_name = team.name

                # Next session and tournament for homepage spotlight
                next_session = SessionPlan.query.filter(
                    SessionPlan.date >= datetime.now().date(),
                    SessionPlan.team_organization_id == team_id
                ).order_by(SessionPlan.date.asc(), SessionPlan.start_time.asc()).first()

                next_tournament = Tournament.query.filter(
                    Tournament.start_date >= datetime.now().date(),
                    Tournament.team_organization_id == team_id
                ).order_by(Tournament.start_date.asc()).first()

                extras = _dashboard_extras(team_id)

        except Exception as e:
            # Log any errors but don't crash the application
            logger.exception(f"Error generating dashboard data: {str(e)}")
            # Don't empty the upcoming_events list here

    checklist = None
    roster_signup = None
    if current_user.is_authenticated and not current_user.is_guest:
        from app.models.team_organization import TeamOrganization
        current_team_id = get_current_team_id()
        team = TeamOrganization.query.get(current_team_id) if current_team_id else None
        if team:
            checklist = onboarding.progress(current_user, team)
            if checklist and (checklist['dismissed'] or checklist['complete']):
                checklist = None
            if current_user.is_coach:
                roster_signup = onboarding.roster_signup(team.id)

    return render_template('index.html',
                         title='Home',
                         stats=stats,
                         recent_activities=recent_activities,
                         upcoming_events=upcoming_events,
                         team_name=team_name,
                         next_session=next_session,
                         next_tournament=next_tournament,
                         checklist=checklist,
                         roster_signup=roster_signup,
                         **extras)


@bp.route('/about')
def about():
    return render_template('about.html', title='About')

@bp.route('/how-to-use')
def how_to_use():
    """Display the How to Use guide page."""
    return render_template('how_to_use.html', title='How to Use Ultimate Coach')

@bp.route('/admin/data-management')
def data_management():
    """The old backup page: everything now lives on the enhanced page."""
    return redirect(url_for('data_management.data_management'), code=301)


@bp.route('/csp-report', methods=['POST'])
@csrf.exempt
@limiter.limit('30 per minute')
def csp_report():
    """Browsers post here when a page breaks the report-only CSP (see
    CSP_REPORT_ONLY in app/__init__.py)."""
    report = (request.get_json(force=True, silent=True) or {}).get('csp-report') or {}
    logger.warning('CSP would block %s (%s) on %s', str(report.get('blocked-uri'))[:200],
                   str(report.get('violated-directive'))[:80],
                   str(report.get('document-uri'))[:200])
    return '', 204
