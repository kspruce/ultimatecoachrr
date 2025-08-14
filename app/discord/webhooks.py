import json
import requests
import logging
from flask import current_app
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)

class DiscordWebhook:
    def __init__(self, app=None):
        self.app = app
        self.webhook_url = None
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app context"""
        self.app = app
        self.webhook_url = app.config.get('DISCORD_WEBHOOK_URL')
    
    def send_message(self, content, embeds=None, username=None, avatar_url=None):
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
        
        Returns:
        --------
        bool
            True if successful, False otherwise
        """
        if not self.webhook_url:
            logger.error("Discord webhook URL not configured")
            return False
        
        payload = {"content": content}
        
        if embeds:
            payload["embeds"] = embeds
        
        if username:
            payload["username"] = username
        
        if avatar_url:
            payload["avatar_url"] = avatar_url
        
        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Error sending Discord webhook: {str(e)}")
            return False
    
    def notify_new_game(self, game):
        """Send notification about a new game
        
        Parameters:
        -----------
        game: Game
            The game object
        """
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
        
        return self.send_message(
            content="@everyone A new game has been added to the calendar!",
            embeds=[embed],
            username="Ultimate Coach"
        )
    
    def notify_upcoming_game(self, game, days_until):
        """Send notification about an upcoming game
        
        Parameters:
        -----------
        game: Game
            The game object
        days_until: int
            Number of days until the game
        """
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
            username="Ultimate Coach"
        )
    
    def notify_new_session(self, session):
        """Send notification about a new training session
        
        Parameters:
        -----------
        session: Session
            The session object
        """
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
        
        return self.send_message(
            content="A new training session has been added to the calendar!",
            embeds=[embed],
            username="Ultimate Coach"
        )
    
    def notify_upcoming_session(self, session, days_until):
        """Send notification about an upcoming training session
        
        Parameters:
        -----------
        session: Session
            The session object
        days_until: int
            Number of days until the session
        """
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
        
        return self.send_message(
            content=content,
            embeds=[embed],
            username="Ultimate Coach"
        )
    
    def notify_new_tournament(self, tournament):
        """Send notification about a new tournament
        
        Parameters:
        -----------
        tournament: Tournament
            The tournament object
        """
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
        
        return self.send_message(
            content="@everyone A new tournament has been added to the calendar!",
            embeds=[embed],
            username="Ultimate Coach"
        )
    
    def notify_upcoming_tournament(self, tournament, days_until):
        """Send notification about an upcoming tournament
        
        Parameters:
        -----------
        tournament: Tournament
            The tournament object
        days_until: int
            Number of days until the tournament
        """
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
            username="Ultimate Coach"
        )

# Create a global instance
discord_webhook = DiscordWebhook()