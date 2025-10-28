import json
#import requests
import logging
from flask import current_app
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)

class DiscordWebhook:
    def __init__(self, app=None):
        self.app = app
        self.webhook_url = None
        self.team_webhook_urls = {}  # Map team_id to webhook URL
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app context"""
        self.app = app
        self.webhook_url = app.config.get('DISCORD_WEBHOOK_URL')
        
        # Load team-specific webhook URLs from config or database
        # This would be implemented based on how you store team-specific Discord settings
        with app.app_context():
            try:
                from app.models.team_organization import TeamOrganization
                from app.models.team_settings import TeamSettings
                
                teams = TeamOrganization.query.all()
                for team in teams:
                    settings = TeamSettings.query.filter_by(team_id=team.id).first()
                    if settings and hasattr(settings, 'discord_webhook_url') and settings.discord_webhook_url:
                        self.team_webhook_urls[team.id] = settings.discord_webhook_url
            except Exception as e:
                logger.error(f"Error loading team webhook URLs: {str(e)}")
    
    def get_webhook_url(self, team_id=None):
        """Get the appropriate webhook URL for the team
        
        Parameters:
        -----------
        team_id: int
            The team organization ID
            
        Returns:
        --------
        str
            The webhook URL to use
        """
        if team_id and team_id in self.team_webhook_urls:
            return self.team_webhook_urls[team_id]
        return self.webhook_url
    
    def send_message(self, content, embeds=None, username=None, avatar_url=None, team_id=None):
        """Send a message to the Discord webhook
        
        Parameters:
        -----------
        content: str
            The message content
        embeds: list
            List of embed dictionaries
        username: str
            Override the webhook's username
        avatar_url: str
            Override the webhook's avatar
        team_id: int
            The team organization ID
        
        Returns:
        --------
        bool
            True if successful, False otherwise
        """
        webhook_url = self.get_webhook_url(team_id)
        
        try:
            import requests  # lazy import to avoid requiring it during CLI tasks
        except Exception as e:
            logger.error(f"requests library not available: {e}")
            return False
        
        if not webhook_url:
            logger.error(f"Discord webhook URL not configured for team {team_id}")
            return False
        
        payload = {"content": content}
        
        if embeds:
            payload["embeds"] = embeds
        
        if username:
            payload["username"] = username
        
        if avatar_url:
            payload["avatar_url"] = avatar_url
        
        try:
            # Add rate limiting - wait between requests
            import time
            time.sleep(1)  # Wait 1 second between webhook requests
            
            response = requests.post(
                webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 429:
                # If rate limited, get retry_after from response and wait
                retry_after = response.json().get('retry_after', 5)
                logger.warning(f"Rate limited by Discord, waiting {retry_after} seconds")
                time.sleep(retry_after)
                
                # Try again after waiting
                response = requests.post(
                    webhook_url,
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"}
                )
            
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Error sending Discord webhook: {str(e)}")
            return False

    def notify_new_game(self, game, team_id=None):
        """Send notification about a new game
        
        Parameters:
        -----------
        game: Game
            The game object
        team_id: int
            The team organization ID
        """
        # Get team_id from game if not provided
        if team_id is None and hasattr(game, 'team_organization_id'):
            team_id = game.team_organization_id
            
        opponent = game.opponent if hasattr(game, 'opponent') else "TBD"
        game_date = game.date.strftime("%Y-%m-%d %H:%M") if hasattr(game, 'date') else "TBD"
        location = game.location if hasattr(game, 'location') else "TBD"
        
        embed = {
            "title": f"New Game Added: vs {opponent}",
            "description": f"A new game has been added to the calendar!",
            "color": 5814783,  # Blue color
            "fields": [
                {
                    "name": "Date",
                    "value": game_date,
                    "inline": True
                },
                {
                    "name": "Location",
                    "value": location,
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Game ID: {game.id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add link to view the game
        base_url = current_app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')
        game_url = f"{base_url}/games/{game.id}/detail"
        embed["fields"].append({
            "name": "View Game",
            "value": f"[Click here for details]({game_url})",
            "inline": False
        })
        
        return self.send_message(
            content="@everyone A new game has been added to the calendar!",
            embeds=[embed],
            username="Ultimate Coach",
            team_id=team_id
        )
    
    def notify_upcoming_game(self, game, days_until, team_id=None):
        """Send notification about an upcoming game
        
        Parameters:
        -----------
        game: Game
            The game object
        days_until: int
            Number of days until the game
        team_id: int
            The team organization ID
        """
        # Get team_id from game if not provided
        if team_id is None and hasattr(game, 'team_organization_id'):
            team_id = game.team_organization_id
            
        opponent = game.opponent if hasattr(game, 'opponent') else "TBD"
        game_date = game.date.strftime("%Y-%m-%d %H:%M") if hasattr(game, 'date') else "TBD"
        location = game.location if hasattr(game, 'location') else "TBD"
        
        if days_until == 0:
            title = f"Game Today: vs {opponent}"
            content = "@everyone We have a game today!"
        elif days_until == 1:
            title = f"Game Tomorrow: vs {opponent}"
            content = "@everyone We have a game tomorrow!"
        else:
            title = f"Upcoming Game: vs {opponent}"
            content = f"@everyone We have a game in {days_until} days!"
        
        embed = {
            "title": title,
            "description": f"Get ready for our upcoming game!",
            "color": 15105570,  # Orange color
            "fields": [
                {
                    "name": "Date",
                    "value": game_date,
                    "inline": True
                },
                {
                    "name": "Location",
                    "value": location,
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Game ID: {game.id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return self.send_message(
            content=content,
            embeds=[embed],
            username="Ultimate Coach",
            team_id=team_id
        )
    
    def notify_new_session(self, session, team_id=None):
        """Send notification about a new training session
        
        Parameters:
        -----------
        session: Session
            The session object
        team_id: int
            The team organization ID
        """
        # Get team_id from session if not provided
        if team_id is None and hasattr(session, 'team_organization_id'):
            team_id = session.team_organization_id
            
        session_date = session.date.strftime("%Y-%m-%d %H:%M") if hasattr(session, 'date') else "TBD"
        location = session.location if hasattr(session, 'location') else "TBD"
        
        embed = {
            "title": f"New Training Session: {session.title}",
            "description": f"A new training session has been added to the calendar!",
            "color": 3066993,  # Green color
            "fields": [
                {
                    "name": "Date",
                    "value": session_date,
                    "inline": True
                },
                {
                    "name": "Location",
                    "value": location,
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Session ID: {session.id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add link to view the session
        base_url = current_app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')
        session_url = f"{base_url}/sessions/{session.id}/detail"
        embed["fields"].append({
            "name": "View Session",
            "value": f"[Click here for details]({session_url})",
            "inline": False
        })
        
        return self.send_message(
            content="A new training session has been added to the calendar!",
            embeds=[embed],
            username="Ultimate Coach",
            team_id=team_id
        )
    
    def notify_upcoming_session(self, session, days_until, team_id=None):
        """Send notification about an upcoming training session
        
        Parameters:
        -----------
        session: Session
            The session object
        days_until: int
            Number of days until the session
        team_id: int
            The team organization ID
        """
        # Get team_id from session if not provided
        if team_id is None and hasattr(session, 'team_organization_id'):
            team_id = session.team_organization_id
            
        session_date = session.date.strftime("%Y-%m-%d %H:%M") if hasattr(session, 'date') else "TBD"
        location = session.location if hasattr(session, 'location') else "TBD"
        
        if days_until == 0:
            title = f"Training Today: {session.title}"
            content = "We have training today!"
        elif days_until == 1:
            title = f"Training Tomorrow: {session.title}"
            content = "We have training tomorrow!"
        else:
            title = f"Upcoming Training: {session.title}"
            content = f"We have training in {days_until} days!"
        
        embed = {
            "title": title,
            "description": f"Get ready for our upcoming training session!",
            "color": 3066993,  # Green color
            "fields": [
                {
                    "name": "Date",
                    "value": session_date,
                    "inline": True
                },
                {
                    "name": "Location",
                    "value": location,
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Session ID: {session.id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add RSVP instructions
        embed["fields"].append({
            "name": "RSVP",
            "value": f"Please RSVP in the app or use the command:\n`!uc rsvp session {session.id} [yes/no/maybe]`",
            "inline": False
        })
        
        # Add link to view the session
        base_url = current_app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')
        session_url = f"{base_url}/sessions/{session.id}/detail"
        embed["fields"].append({
            "name": "View Session",
            "value": f"[Click here for details]({session_url})",
            "inline": False
        })
        
        return self.send_message(
            content=content,
            embeds=[embed],
            username="Ultimate Coach",
            team_id=team_id
        )
    
    def notify_new_tournament(self, tournament, team_id=None):
        """Send notification about a new tournament
        
        Parameters:
        -----------
        tournament: Tournament
            The tournament object
        team_id: int
            The team organization ID
        """
        # Get team_id from tournament if not provided
        if team_id is None and hasattr(tournament, 'team_organization_id'):
            team_id = tournament.team_organization_id
            
        start_date = tournament.start_date.strftime("%Y-%m-%d") if hasattr(tournament, 'start_date') else "TBD"
        end_date = tournament.end_date.strftime("%Y-%m-%d") if hasattr(tournament, 'end_date') and tournament.end_date else start_date
        location = tournament.location if hasattr(tournament, 'location') else "TBD"
        
        date_str = start_date
        if start_date != end_date:
            date_str = f"{start_date} to {end_date}"
        
        embed = {
            "title": f"New Tournament: {tournament.name}",
            "description": f"A new tournament has been added to the calendar!",
            "color": 15844367,  # Gold color
            "fields": [
                {
                    "name": "Date",
                    "value": date_str,
                    "inline": True
                },
                {
                    "name": "Location",
                    "value": location,
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Tournament ID: {tournament.id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add link to view the tournament
        base_url = current_app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')
        tournament_url = f"{base_url}/tournaments/{tournament.id}/detail"
        embed["fields"].append({
            "name": "View Tournament",
            "value": f"[Click here for details]({tournament_url})",
            "inline": False
        })
        
        return self.send_message(
            content="@everyone A new tournament has been added to the calendar!",
            embeds=[embed],
            username="Ultimate Coach",
            team_id=team_id
        )
    
    def notify_upcoming_tournament(self, tournament, days_until, team_id=None):
        """Send notification about an upcoming tournament
        
        Parameters:
        -----------
        tournament: Tournament
            The tournament object
        days_until: int
            Number of days until the tournament
        team_id: int
            The team organization ID
        """
        # Get team_id from tournament if not provided
        if team_id is None and hasattr(tournament, 'team_organization_id'):
            team_id = tournament.team_organization_id
            
        start_date = tournament.start_date.strftime("%Y-%m-%d") if hasattr(tournament, 'start_date') else "TBD"
        end_date = tournament.end_date.strftime("%Y-%m-%d") if hasattr(tournament, 'end_date') and tournament.end_date else start_date
        location = tournament.location if hasattr(tournament, 'location') else "TBD"
        
        date_str = start_date
        if start_date != end_date:
            date_str = f"{start_date} to {end_date}"
        
        if days_until == 0:
            title = f"Tournament Today: {tournament.name}"
            content = "@everyone Our tournament starts today!"
        elif days_until == 1:
            title = f"Tournament Tomorrow: {tournament.name}"
            content = "@everyone Our tournament starts tomorrow!"
        else:
            title = f"Upcoming Tournament: {tournament.name}"
            content = f"@everyone Our tournament starts in {days_until} days!"
        
        embed = {
            "title": title,
            "description": f"Get ready for our upcoming tournament!",
            "color": 15844367,  # Gold color
            "fields": [
                {
                    "name": "Date",
                    "value": date_str,
                    "inline": True
                },
                {
                    "name": "Location",
                    "value": location,
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Tournament ID: {tournament.id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add RSVP instructions
        embed["fields"].append({
            "name": "RSVP",
            "value": f"Please RSVP in the app or use the command:\n`!uc rsvp tournament {tournament.id} [yes/no/maybe]`",
            "inline": False
        })
        
        return self.send_message(
            content=content,
            embeds=[embed],
            username="Ultimate Coach",
            team_id=team_id
        )

    def notify_new_clip(self, clip, team_id=None):
        """Send notification about a new clip
        
        Parameters:
        -----------
        clip: Clip
            The clip object
        team_id: int
            The team organization ID
        """
        # Get team_id from clip if not provided
        if team_id is None and hasattr(clip, 'team_organization_id'):
            team_id = clip.team_organization_id
            
        title = clip.title if hasattr(clip, 'title') else f"Clip #{clip.id}"
        game_info = f" from game vs {clip.game.opponent}" if hasattr(clip, 'game') and hasattr(clip.game, 'opponent') else ""
        
        embed = {
            "title": f"New Clip Added: {title}",
            "description": f"A new video clip has been added to the library{game_info}!",
            "color": 10181046,  # Purple color
            "fields": [],
            "footer": {
                "text": f"Clip ID: {clip.id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add tags if available
        if hasattr(clip, 'tags') and clip.tags:
            tags_text = ", ".join([tag.name for tag in clip.tags])
            embed["fields"].append({
                "name": "Tags",
                "value": tags_text,
                "inline": True
            })
        
        # Add link to view the clip
        base_url = current_app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')
        clip_url = f"{base_url}/clips/view/{clip.id}"
        embed["fields"].append({
            "name": "View Clip",
            "value": f"[Click here to view]({clip_url})",
            "inline": False
        })
        
        return self.send_message(
            content="A new video clip has been added to the library!",
            embeds=[embed],
            username="Ultimate Coach",
            team_id=team_id
        )
    
    def notify_new_theory(self, theory_item, team_id=None):
        """Send notification about new theory content
        
        Parameters:
        -----------
        theory_item: TheoryTopic or TheorySection
            The theory content object
        team_id: int
            The team organization ID
        """
        # Get team_id from theory_item if not provided
        if team_id is None and hasattr(theory_item, 'team_organization_id'):
            team_id = theory_item.team_organization_id
            
        # Determine if it's a topic or section
        is_topic = hasattr(theory_item, 'section_id')
        
        if is_topic:
            title = f"New Theory Topic: {theory_item.title}"
            section_name = theory_item.section.title if hasattr(theory_item, 'section') and theory_item.section else "Unknown Section"
            description = f"A new theory topic has been added to the {section_name} section!"
        else:
            title = f"New Theory Section: {theory_item.title}"
            description = "A new theory section has been added to the knowledge base!"
        
        embed = {
            "title": title,
            "description": description,
            "color": 3447003,  # Blue color
            "fields": [],
            "footer": {
                "text": f"Theory {'Topic' if is_topic else 'Section'} ID: {theory_item.id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add a brief excerpt if available
        if hasattr(theory_item, 'content') and theory_item.content:
            # Truncate content if it's too long
            content_preview = theory_item.content[:150] + "..." if len(theory_item.content) > 150 else theory_item.content
            embed["fields"].append({
                "name": "Preview",
                "value": content_preview,
                "inline": False
            })
        
        # Add link to view the theory content
        base_url = current_app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')
        if is_topic:
            theory_url = f"{base_url}/theory/topic/{theory_item.id}"
        else:
            theory_url = f"{base_url}/theory/section/{theory_item.id}"
        
        embed["fields"].append({
            "name": "Read More",
            "value": f"[Click here to read]({theory_url})",
            "inline": False
        })
        
        return self.send_message(
            content=f"New theory {'topic' if is_topic else 'section'} added: **{theory_item.title}**",
            embeds=[embed],
            username="Ultimate Coach",
            team_id=team_id
        )


# Create a global instance
discord_webhook = DiscordWebhook()
