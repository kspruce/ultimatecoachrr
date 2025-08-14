import os
import discord
from discord.ext import commands, tasks
import datetime
from flask import current_app
import asyncio
import logging

# Set up logging
logger = logging.getLogger(__name__)

class UltimateCoachBot:
    def __init__(self, app=None):
        self.app = app
        self.bot = None
        self.token = None
        self.guild_id = None
        self.calendar_channel_id = None
        self.notification_channel_id = None
        self.sync_task = None
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the bot with Flask app context"""
        self.app = app
        
        # Get configuration from Flask app
        self.token = app.config.get('DISCORD_BOT_TOKEN')
        self.guild_id = app.config.get('DISCORD_GUILD_ID')
        self.calendar_channel_id = app.config.get('DISCORD_CALENDAR_CHANNEL_ID')
        self.notification_channel_id = app.config.get('DISCORD_NOTIFICATION_CHANNEL_ID')
        
        # Initialize bot with intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.guild_scheduled_events = True
        
        self.bot = commands.Bot(command_prefix='!uc ', intents=intents)
        
        # Register event handlers
        @self.bot.event
        async def on_ready():
            logger.info(f'Bot logged in as {self.bot.user}')
            # Start background tasks
            if not self.sync_task or not self.sync_task.is_running():
                self.sync_calendar.start()
        
        # Register commands
        @self.bot.command(name='upcoming')
        async def upcoming_events(ctx):
            """Show upcoming events"""
            with self.app.app_context():
                from app.models.event import Event
                from app.models.session import Session
                from app.models.tournament import Tournament
                from app.models.game import Game
                from datetime import datetime, timedelta
                
                # Get events for the next 7 days
                now = datetime.now()
                next_week = now + timedelta(days=7)
                
                # Get all types of events
                sessions = Session.query.filter(Session.date >= now, Session.date <= next_week).all()
                tournaments = Tournament.query.filter(Tournament.start_date >= now, Tournament.start_date <= next_week).all()
                games = Game.query.filter(Game.date >= now, Game.date <= next_week).all()
                
                if not sessions and not tournaments and not games:
                    await ctx.send("No upcoming events in the next 7 days.")
                    return
                
                embed = discord.Embed(
                    title="Upcoming Events (Next 7 Days)",
                    color=discord.Color.blue()
                )
                
                # Add sessions
                if sessions:
                    session_text = ""
                    for session in sessions:
                        session_text += f"**{session.title}** - {session.date.strftime('%Y-%m-%d %H:%M')}\n"
                        if session.location:
                            session_text += f"📍 {session.location}\n"
                        session_text += "\n"
                    embed.add_field(name="Training Sessions", value=session_text or "None", inline=False)
                
                # Add tournaments
                if tournaments:
                    tournament_text = ""
                    for tournament in tournaments:
                        tournament_text += f"**{tournament.name}** - {tournament.start_date.strftime('%Y-%m-%d')}"
                        if tournament.end_date and tournament.end_date != tournament.start_date:
                            tournament_text += f" to {tournament.end_date.strftime('%Y-%m-%d')}\n"
                        else:
                            tournament_text += "\n"
                        if tournament.location:
                            tournament_text += f"📍 {tournament.location}\n"
                        tournament_text += "\n"
                    embed.add_field(name="Tournaments", value=tournament_text or "None", inline=False)
                
                # Add games
                if games:
                    game_text = ""
                    for game in games:
                        opponent = game.opponent if hasattr(game, 'opponent') else "TBD"
                        game_text += f"**vs {opponent}** - {game.date.strftime('%Y-%m-%d %H:%M')}\n"
                        if game.location:
                            game_text += f"📍 {game.location}\n"
                        game_text += "\n"
                    embed.add_field(name="Games", value=game_text or "None", inline=False)
                
                await ctx.send(embed=embed)
        
        @self.bot.command(name='rsvp')
        async def rsvp_command(ctx, event_type, event_id: int, response: str):
            """RSVP to an event
            
            Parameters:
            -----------
            event_type: str
                The type of event (session, tournament, game)
            event_id: int
                The ID of the event
            response: str
                Your response (yes, no, maybe)
            """
            valid_responses = ['yes', 'no', 'maybe']
            if response.lower() not in valid_responses:
                await ctx.send(f"Invalid response. Please use one of: {', '.join(valid_responses)}")
                return
            
            with self.app.app_context():
                from app.models.user import User
                from app.models.session import Session, SessionRSVP
                from app.models.tournament import Tournament, TournamentRSVP
                from flask_login import current_user
                from app import db
                
                # Find the Discord user's linked account
                discord_id = str(ctx.author.id)
                user = User.query.filter_by(discord_id=discord_id).first()
                
                if not user:
                    await ctx.send("Your Discord account is not linked to an Ultimate Coach account. Please link your account first.")
                    return
                
                if not user.player:
                    await ctx.send("Your account is not linked to a player profile. Please link your account to a player first.")
                    return
                
                try:
                    if event_type.lower() == 'session':
                        event = Session.query.get(event_id)
                        if not event:
                            await ctx.send(f"Session with ID {event_id} not found.")
                            return
                        
                        # Check if RSVP already exists
                        rsvp = SessionRSVP.query.filter_by(session_id=event_id, player_id=user.player.id).first()
                        
                        if rsvp:
                            rsvp.status = response.lower()
                            db.session.commit()
                            await ctx.send(f"Updated your RSVP for {event.title} to '{response}'.")
                        else:
                            new_rsvp = SessionRSVP(
                                session_id=event_id,
                                player_id=user.player.id,
                                status=response.lower()
                            )
                            db.session.add(new_rsvp)
                            db.session.commit()
                            await ctx.send(f"You've RSVP'd '{response}' to {event.title}.")
                    
                    elif event_type.lower() == 'tournament':
                        event = Tournament.query.get(event_id)
                        if not event:
                            await ctx.send(f"Tournament with ID {event_id} not found.")
                            return
                        
                        # Check if RSVP already exists
                        rsvp = TournamentRSVP.query.filter_by(tournament_id=event_id, player_id=user.player.id).first()
                        
                        if rsvp:
                            rsvp.status = response.lower()
                            db.session.commit()
                            await ctx.send(f"Updated your RSVP for {event.name} to '{response}'.")
                        else:
                            new_rsvp = TournamentRSVP(
                                tournament_id=event_id,
                                player_id=user.player.id,
                                status=response.lower()
                            )
                            db.session.add(new_rsvp)
                            db.session.commit()
                            await ctx.send(f"You've RSVP'd '{response}' to {event.name}.")
                    
                    else:
                        await ctx.send(f"Invalid event type: {event_type}. Valid types are: session, tournament")
                
                except Exception as e:
                    logger.error(f"Error processing RSVP: {str(e)}")
                    await ctx.send("An error occurred while processing your RSVP. Please try again later.")
        
        @self.bot.command(name='link')
        async def link_account(ctx, email: str):
            """Link your Discord account to your Ultimate Coach account
            
            Parameters:
            -----------
            email: str
                The email address associated with your Ultimate Coach account
            """
            with self.app.app_context():
                from app.models.user import User
                from app import db
                
                user = User.query.filter_by(email=email).first()
                
                if not user:
                    await ctx.send(f"No account found with email: {email}")
                    return
                
                # Link Discord ID to user account
                user.discord_id = str(ctx.author.id)
                db.session.commit()
                
                await ctx.send(f"Your Discord account has been linked to {user.username}!")
                
                # Send a DM to the user with confirmation
                try:
                    await ctx.author.send(f"Your Discord account has been successfully linked to your Ultimate Coach account ({user.username}).")
                except:
                    # If DM fails, just continue
                    pass
        
        @self.bot.command(name='help')
        async def help_command(ctx):
            """Show available commands"""
            embed = discord.Embed(
                title="Ultimate Coach Bot Commands",
                description="Here are the commands you can use:",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="!uc upcoming",
                value="Shows upcoming events for the next 7 days",
                inline=False
            )
            
            embed.add_field(
                name="!uc rsvp [event_type] [event_id] [response]",
                value="RSVP to an event (session, tournament)\nResponses: yes, no, maybe\nExample: !uc rsvp session 5 yes",
                inline=False
            )
            
            embed.add_field(
                name="!uc link [email]",
                value="Link your Discord account to your Ultimate Coach account\nExample: !uc link player@example.com",
                inline=False
            )
            
            await ctx.send(embed=embed)
    
    @tasks.loop(hours=12)
    async def sync_calendar(self):
        """Sync calendar events with Discord scheduled events"""
        logger.info("Starting calendar sync")
        
        try:
            with self.app.app_context():
                from app.models.session import Session
                from app.models.tournament import Tournament
                from app.models.game import Game
                from datetime import datetime, timedelta
                
                # Get guild
                guild = self.bot.get_guild(int(self.guild_id))
                if not guild:
                    logger.error(f"Could not find guild with ID {self.guild_id}")
                    return
                
                # Get events for the next 30 days
                now = datetime.now()
                next_month = now + timedelta(days=30)
                
                # Get all types of events
                sessions = Session.query.filter(Session.date >= now, Session.date <= next_month).all()
                tournaments = Tournament.query.filter(Tournament.start_date >= now, Tournament.start_date <= next_month).all()
                games = Game.query.filter(Game.date >= now, Game.date <= next_month).all()
                
                # Get existing Discord events
                discord_events = await guild.fetch_scheduled_events()
                discord_event_names = {event.name: event for event in discord_events}
                
                # Sync sessions
                for session in sessions:
                    event_name = f"Training: {session.title}"
                    
                    # Check if event already exists
                    if event_name in discord_event_names:
                        # Update existing event if needed
                        discord_event = discord_event_names[event_name]
                        # TODO: Update event if details changed
                    else:
                        # Create new event
                        location = session.location or "TBD"
                        description = f"Training session: {session.title}\n\n"
                        if session.description:
                            description += f"{session.description}\n\n"
                        description += f"RSVP in the app or use the command:\n!uc rsvp session {session.id} [yes/no/maybe]"
                        
                        try:
                            end_time = session.date + timedelta(hours=2)  # Assume 2 hours duration
                            await guild.create_scheduled_event(
                                name=event_name,
                                description=description,
                                start_time=session.date,
                                end_time=end_time,
                                location=location
                            )
                            logger.info(f"Created Discord event for session: {session.title}")
                        except Exception as e:
                            logger.error(f"Error creating Discord event for session {session.id}: {str(e)}")
                
                # Sync tournaments
                for tournament in tournaments:
                    event_name = f"Tournament: {tournament.name}"
                    
                    # Check if event already exists
                    if event_name in discord_event_names:
                        # Update existing event if needed
                        discord_event = discord_event_names[event_name]
                        # TODO: Update event if details changed
                    else:
                        # Create new event
                        location = tournament.location or "TBD"
                        description = f"Tournament: {tournament.name}\n\n"
                        if tournament.description:
                            description += f"{tournament.description}\n\n"
                        description += f"RSVP in the app or use the command:\n!uc rsvp tournament {tournament.id} [yes/no/maybe]"
                        
                        try:
                            # Use end_date if available, otherwise assume 1 day
                            if tournament.end_date:
                                end_time = datetime.combine(tournament.end_date, datetime.max.time())
                            else:
                                end_time = datetime.combine(tournament.start_date, datetime.max.time())
                            
                            start_time = datetime.combine(tournament.start_date, datetime.min.time())
                            
                            await guild.create_scheduled_event(
                                name=event_name,
                                description=description,
                                start_time=start_time,
                                end_time=end_time,
                                location=location
                            )
                            logger.info(f"Created Discord event for tournament: {tournament.name}")
                        except Exception as e:
                            logger.error(f"Error creating Discord event for tournament {tournament.id}: {str(e)}")
                
                # Sync games
                for game in games:
                    opponent = game.opponent if hasattr(game, 'opponent') else "TBD"
                    event_name = f"Game: vs {opponent}"
                    
                    # Check if event already exists
                    if event_name in discord_event_names:
                        # Update existing event if needed
                        discord_event = discord_event_names[event_name]
                        # TODO: Update event if details changed
                    else:
                        # Create new event
                        location = game.location or "TBD"
                        description = f"Game vs {opponent}\n\n"
                        if hasattr(game, 'description') and game.description:
                            description += f"{game.description}\n\n"
                        
                        try:
                            end_time = game.date + timedelta(hours=2)  # Assume 2 hours duration
                            await guild.create_scheduled_event(
                                name=event_name,
                                description=description,
                                start_time=game.date,
                                end_time=end_time,
                                location=location
                            )
                            logger.info(f"Created Discord event for game vs {opponent}")
                        except Exception as e:
                            logger.error(f"Error creating Discord event for game {game.id}: {str(e)}")
                
                logger.info("Calendar sync completed")
        
        except Exception as e:
            logger.error(f"Error during calendar sync: {str(e)}")
    
    def start_bot(self):
        """Start the Discord bot in a separate thread"""
        if not self.token:
            logger.error("Discord bot token not configured")
            return
        
        import threading
        
        def run_bot():
            asyncio.run(self.bot.start(self.token))
        
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        logger.info("Discord bot started in background thread")
    
    def send_notification(self, title, message, embed=None):
        """Send a notification to the configured channel"""
        if not self.bot or not self.notification_channel_id:
            logger.error("Bot not initialized or notification channel not configured")
            return False
        
        async def _send():
            try:
                channel = self.bot.get_channel(int(self.notification_channel_id))
                if not channel:
                    logger.error(f"Could not find channel with ID {self.notification_channel_id}")
                    return False
                
                if embed:
                    await channel.send(content=message, embed=embed)
                else:
                    await channel.send(content=f"**{title}**\n{message}")
                return True
            except Exception as e:
                logger.error(f"Error sending notification: {str(e)}")
                return False
        
        # Create a new event loop for the async call
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_send())
        loop.close()
        return result

# Create a global instance
discord_bot = UltimateCoachBot()