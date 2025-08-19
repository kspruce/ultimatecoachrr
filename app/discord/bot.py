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
        self.team_discord_settings = {}  # Map team_id to Discord settings
        
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
        
        # Load team-specific Discord settings
        with app.app_context():
            try:
                from app.models.team_organization import TeamOrganization
                from app.models.team_settings import TeamSettings
                
                teams = TeamOrganization.query.all()
                for team in teams:
                    settings = TeamSettings.query.filter_by(team_id=team.id).first()
                    if settings:
                        self.team_discord_settings[team.id] = {
                            'guild_id': getattr(settings, 'discord_guild_id', self.guild_id),
                            'calendar_channel_id': getattr(settings, 'discord_calendar_channel_id', self.calendar_channel_id),
                            'notification_channel_id': getattr(settings, 'discord_notification_channel_id', self.notification_channel_id)
                        }
            except Exception as e:
                logger.error(f"Error loading team Discord settings: {str(e)}")
        
        # Initialize bot with intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.guild_scheduled_events = True
        
        self.bot = commands.Bot(command_prefix='!uc ', intents=intents)
        self.bot.remove_command('help')
        
        # Register event handlers
        @self.bot.event
        async def on_ready():
            logger.info(f'Bot logged in as {self.bot.user}')
            # Start background tasks
            if not self.sync_task or not self.sync_task.is_running():
                self.sync_calendar.start()

        
                
        @self.bot.event
        async def on_reaction_add(reaction, user):
            """Handle reactions to event messages for RSVPs"""
            # Ignore bot's own reactions
            if user.bot:
                return
            
            # Check if this is a reaction to an event message
            if not hasattr(self, 'event_messages') or reaction.message.id not in self.event_messages:
                return
            
            # Get the event info
            event_info = self.event_messages[reaction.message.id]
            event_type = event_info['type']
            event_id = event_info['id']
            
            # Map emoji to RSVP status
            emoji_to_session_status = {
                "✅": "yes",
                "❌": "no",
                "❓": "maybe"
            }
            
            # Map emoji to tournament RSVP status
            emoji_to_tournament_status = {
                "✅": "attending",
                "❌": "not_attending",
                "❓": "maybe"
            }
            
            # Check if this is a valid RSVP emoji
            emoji = str(reaction.emoji)
            if emoji not in emoji_to_session_status:  # Both maps have the same keys
                return
            
            # Process the RSVP
            try:
                with self.app.app_context():
                    from app.models.user import User
                    from app.models.session import SessionPlan, SessionRSVP
                    from app.models.tournament import Tournament
                    from app.models.tournament_rsvp import TournamentRSVP
                    from app import db
                    
                    # Find the Discord user's linked account
                    discord_id = str(user.id)
                    db_user = User.query.filter_by(discord_id=discord_id).first()
                    
                    if not db_user:
                        # Send a DM to the user if their account isn't linked
                        try:
                            await user.send("Your Discord account is not linked to an Ultimate Coach account. "
                                           f"Please use `!uc link your@email.com` to link your account.")
                        except:
                            # If DM fails, just continue
                            pass
                        return
                    
                    if not db_user.player:
                        # Send a DM if they don't have a player profile
                        try:
                            await user.send("Your account is not linked to a player profile. "
                                           "Please link your account to a player profile in the Ultimate Coach app.")
                        except:
                            pass
                        return
                    
                    # Process the RSVP based on event type
                    if event_type == 'session':
                        event = SessionPlan.query.get(event_id)
                        if not event:
                            return
                        
                        status = emoji_to_session_status[emoji]
                        
                        # Check if RSVP already exists
                        rsvp = SessionRSVP.query.filter_by(session_id=event_id, player_id=db_user.player.id).first()
                        
                        if rsvp:
                            rsvp.status = status
                            db.session.commit()
                            response_msg = f"Updated your RSVP for {event.title} to '{status}'."
                        else:
                            new_rsvp = SessionRSVP(
                                session_id=event_id,
                                player_id=db_user.player.id,
                                status=status
                            )
                            db.session.add(new_rsvp)
                            db.session.commit()
                            response_msg = f"You've RSVP'd '{status}' to {event.title}."
                    
                    elif event_type == 'tournament':
                        event = Tournament.query.get(event_id)
                        if not event:
                            return
                        
                        status = emoji_to_tournament_status[emoji]
                        
                        # Check if RSVP already exists
                        rsvp = TournamentRSVP.query.filter_by(tournament_id=event_id, player_id=db_user.player.id).first()
                        
                        if rsvp:
                            rsvp.status = status
                            db.session.commit()
                            response_msg = f"Updated your RSVP for {event.name} to '{status}'."
                        else:
                            new_rsvp = TournamentRSVP(
                                tournament_id=event_id,
                                player_id=db_user.player.id,
                                status=status
                            )
                            db.session.add(new_rsvp)
                            db.session.commit()
                            response_msg = f"You've RSVP'd '{status}' to {event.name}."

                    
                    else:
                        # Handle other event types if needed
                        return
                    
                    # Send a confirmation DM to the user
                    try:
                        await user.send(response_msg)
                    except:
                        # If DM fails, just continue
                        pass
            
            except Exception as e:
                logger.error(f"Error processing reaction RSVP: {str(e)}")
                # Try to notify the user of the error
                try:
                    await user.send("An error occurred while processing your RSVP. Please try again later.")
                except:
                    pass

        @self.bot.event
        async def on_reaction_remove(reaction, user):
            """Handle reaction removals to cancel RSVPs"""
            # Ignore bot's own reactions
            if user.bot:
                return
            
            # Check if this is a reaction to an event message
            if not hasattr(self, 'event_messages') or reaction.message.id not in self.event_messages:
                return
            
            # Get the event info
            event_info = self.event_messages[reaction.message.id]
            event_type = event_info['type']
            event_id = event_info['id']
            
            # Map emoji to RSVP status
            emoji_to_session_status = {
                "✅": "yes",
                "❌": "no",
                "❓": "maybe"
            }
            
            # Map emoji to tournament RSVP status
            emoji_to_tournament_status = {
                "✅": "attending",
                "❌": "not_attending",
                "❓": "maybe"
            }
            
            # Check if this is a valid RSVP emoji
            emoji = str(reaction.emoji)
            if emoji not in emoji_to_session_status:  # Both maps have the same keys
                return


            # Process the RSVP removal
            try:
                with self.app.app_context():
                    from app.models.user import User
                    from app.models.session import SessionPlan, SessionRSVP
                    from app.models.tournament import Tournament
                    from app.models.tournament_rsvp import TournamentRSVP
                    from app import db
                    
                    # Find the Discord user's linked account
                    discord_id = str(user.id)
                    db_user = User.query.filter_by(discord_id=discord_id).first()
                    
                    if not db_user or not db_user.player:
                        return  # User not properly linked, nothing to cancel
                    
                    # Check if the user has other reactions on this message
                    # If they do, we don't want to cancel their RSVP, they're just changing their response
                    for react_emoji in emoji_to_session_status.keys():  # Both maps have the same keys
                        if react_emoji == emoji:
                            continue  # Skip the emoji that was just removed
                        
                        # Check if user has this reaction on the message
                        for reaction_check in reaction.message.reactions:
                            if str(reaction_check.emoji) == react_emoji:
                                async for reaction_user in reaction_check.users():
                                    if reaction_user.id == user.id:
                                        return  # User has another reaction, they're just changing their response
                    
                    # If we get here, the user has removed all their reactions, so cancel their RSVP
                    if event_type == 'session':
                        event = SessionPlan.query.get(event_id)
                        if not event:
                            return
                        
                        # Find and delete the RSVP
                        rsvp = SessionRSVP.query.filter_by(session_id=event_id, player_id=db_user.player.id).first()
                        if rsvp:
                            db.session.delete(rsvp)
                            db.session.commit()
                            response_msg = f"Your RSVP for {event.title} has been cancelled."
                            
                            # Send a confirmation DM to the user
                            try:
                                await user.send(response_msg)
                            except:
                                # If DM fails, just continue
                                pass
                    
                    elif event_type == 'tournament':
                        event = Tournament.query.get(event_id)
                        if not event:
                            return
                        
                        # Find and delete the RSVP
                        rsvp = TournamentRSVP.query.filter_by(tournament_id=event_id, player_id=db_user.player.id).first()
                        if rsvp:
                            db.session.delete(rsvp)
                            db.session.commit()
                            response_msg = f"Your RSVP for {event.name} has been cancelled."
                            
                            # Send a confirmation DM to the user
                            try:
                                await user.send(response_msg)
                            except:
                                # If DM fails, just continue
                                pass
                    
                    # Handle other event types if needed
            
            except Exception as e:
                logger.error(f"Error processing reaction removal: {str(e)}")
                logger.exception(e)  # This will print the full stack trace
                # Try to notify the user of the error
                try:
                    await user.send(f"An error occurred while processing your RSVP cancellation: {str(e)}")
                except:
                    pass



        @self.bot.command(name='attendees')
        async def show_attendees(ctx, event_type, event_id: int):
            """Show who's attending an event"""
            with self.app.app_context():
                try:
                    if event_type.lower() == 'session':
                        from app.models.session import SessionPlan, SessionRSVP
                        from app.models.player import Player
                        
                        event = SessionPlan.query.get(event_id)
                        if not event:
                            await ctx.send(f"Session with ID {event_id} not found.")
                            return
                        
                        # Get RSVPs
                        rsvps = SessionRSVP.query.filter_by(session_id=event_id).all()
                        
                        # Create embed
                        embed = discord.Embed(
                            title=f"Attendees for {event.title}",
                            color=discord.Color.blue()
                        )
                        
                        # Group by status
                        yes_list = []
                        no_list = []
                        maybe_list = []
                        
                        for rsvp in rsvps:
                            player = Player.query.get(rsvp.player_id)
                            if not player:
                                continue
                            
                            name = player.name
                            
                            if rsvp.status == 'yes':
                                yes_list.append(name)
                            elif rsvp.status == 'no':
                                no_list.append(name)
                            elif rsvp.status == 'maybe':
                                maybe_list.append(name)
                        
                        # Add fields
                        embed.add_field(
                            name=f"✅ Yes ({len(yes_list)})",
                            value="\n".join(yes_list) if yes_list else "None",
                            inline=False
                        )
                        
                        embed.add_field(
                            name=f"❓ Maybe ({len(maybe_list)})",
                            value="\n".join(maybe_list) if maybe_list else "None",
                            inline=False
                        )
                        
                        embed.add_field(
                            name=f"❌ No ({len(no_list)})",
                            value="\n".join(no_list) if no_list else "None",
                            inline=False
                        )
                        
                        await ctx.send(embed=embed)
                    
                    elif event_type.lower() == 'tournament':
                        # Similar implementation for tournaments
                        pass
                    
                    else:
                        await ctx.send(f"Invalid event type: {event_type}. Valid types are: session, tournament")
                
                except Exception as e:
                    logger.error(f"Error showing attendees: {str(e)}")
                    await ctx.send("An error occurred while retrieving attendees. Please try again later.")


        # Register commands
        @self.bot.command(name='upcoming')
        async def upcoming_events(ctx):
            """Show upcoming events"""
            with self.app.app_context():
                from app.models.session import SessionPlan, SessionRSVP
                from app.models.tournament import Tournament
                from app.models.game import Game
                from datetime import datetime, timedelta
                
                # Get events for the next 7 days
                now = datetime.now()
                next_week = now + timedelta(days=7)
                
                # Get all types of events
                sessions = SessionPlan.query.filter(SessionPlan.date >= now, SessionPlan.date <= next_week).all()
                tournaments = Tournament.query.filter(Tournament.start_date >= now, Tournament.start_date <= next_week).all()
                games = Game.query.filter(Game.date >= now, Game.date <= next_week).all()
                
                if not sessions and not tournaments and not games:
                    await ctx.send("No upcoming events in the next 7 days.")
                    return
                
                # Create embeds for each event type to allow individual reactions
                all_events = []
                
                # Process sessions
                for session in sessions:
                    
                    base_url = self.app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')

                    # Create the session detail URL
                    session_url = f"{base_url}/session/detail/{session.id}"
                    
                    embed = discord.Embed(
                        title=f"Training: {session.title}",
                        description="React to RSVP:\n✅ Yes | ❌ No | ❓ Maybe",
                        color=discord.Color.blue(),
                        url=session_url
                    )
                    
                    # Format date and time
                    date_str = session.date.strftime('%Y-%m-%d')
                    time_str = ""
                    if hasattr(session, 'start_time') and session.start_time:
                        time_str = f" at {session.start_time.strftime('%H:%M')}"
                    
                    # Add session details
                    embed.add_field(name="Date", value=f"{date_str}{time_str}", inline=True)
                    if session.location:
                        embed.add_field(name="Location", value=session.location, inline=True)
                    
                    # Add session type if available
                    if hasattr(session, 'session_type_display') and session.session_type_display:
                        embed.add_field(name="Type", value=session.session_type_display, inline=True)
                    
                    # Add a field with a direct link
                    embed.add_field(
                        name="More Details",
                        value=f"[View Session Details]({session_url})",
                        inline=False
                    )
                    
                    # Add footer with event ID for the reaction handler
                    embed.set_footer(text=f"Session ID: {session.id} | Type !uc help for more commands")
                    
                    # Store the event info for later
                    all_events.append({
                        'type': 'session',
                        'id': session.id,
                        'embed': embed
                    })
                
                # Process tournaments
                for tournament in tournaments:
                    base_url = self.app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')

                    # Create the tournament detail URL
                    tournament_url = f"{base_url}/tournament/detail/{tournament.id}"
                    
                    embed = discord.Embed(
                        title=f"Tournament: {tournament.name}",
                        description="React to RSVP:\n✅ Yes | ❌ No | ❓ Maybe",
                        color=discord.Color.gold(),
                        url=tournament_url
                    )
                    
                    # Format date range
                    date_str = tournament.start_date.strftime('%Y-%m-%d')
                    if tournament.end_date and tournament.end_date != tournament.start_date:
                        date_str += f" to {tournament.end_date.strftime('%Y-%m-%d')}"
                    
                    # Add tournament details
                    embed.add_field(name="Date", value=date_str, inline=True)
                    if tournament.location:
                        embed.add_field(name="Location", value=tournament.location, inline=True)
                    
                    # Add a field with a direct link
                    embed.add_field(
                        name="More Details",
                        value=f"[View Tournament Details]({tournament_url})",
                        inline=False
                    )
                    
                    # Add footer with event ID for the reaction handler
                    embed.set_footer(text=f"Tournament ID: {tournament.id} | Type !uc help for more commands")
                    
                    # Store the event info for later
                    all_events.append({
                        'type': 'tournament',
                        'id': tournament.id,
                        'embed': embed
                    })
                
                # Process games (optional, if you want to allow RSVPs for games)
                for game in games:
                    opponent = game.opponent if hasattr(game, 'opponent') else "TBD"
                    
                    # Get base URL from config
                    base_url = self.app.config.get('BASE_URL', 'https://ultimatecoach.applikuapp.com')
                    
                    # Create the game detail URL
                    game_url = f"{base_url}/game/detail/{game.id}"
                    
                    embed = discord.Embed(
                        title=f"Game: vs {opponent}",
                        description="React to RSVP:\n✅ Yes | ❌ No | ❓ Maybe",
                        color=discord.Color.red(),
                        url=game_url  
                    )
                    
                    # Format date and time
                    date_str = game.date.strftime('%Y-%m-%d %H:%M')
                    
                    # Add game details
                    embed.add_field(name="Date", value=date_str, inline=True)
                    if game.location:
                        embed.add_field(name="Location", value=game.location, inline=True)
                    
                    # Add a field with a direct link
                    embed.add_field(
                        name="More Details",
                        value=f"[View Game Details]({game_url})",
                        inline=False
                    )
                    
                    # Add footer with event ID for the reaction handler
                    embed.set_footer(text=f"Game ID: {game.id} | Type !uc help for more commands")
                    
                    # Store the event info for later
                    all_events.append({
                        'type': 'game',
                        'id': game.id,
                        'embed': embed
                    })
                
                # Send a summary message first
                summary = discord.Embed(
                    title="Upcoming Events (Next 7 Days)",
                    description=f"Found {len(all_events)} upcoming events. Check below for details and react to RSVP.",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=summary)
                
                # Send each event as a separate message with reactions
                for event in all_events:
                    message = await ctx.send(embed=event['embed'])
                    
                    # Add reaction emojis
                    await message.add_reaction("✅")  # Yes
                    await message.add_reaction("❌")  # No
                    await message.add_reaction("❓")  # Maybe
                    
                    # Store the message ID and event info in the bot's cache
                    # This will be used by the reaction handler
                    if not hasattr(self, 'event_messages'):
                        self.event_messages = {}
                    
                    self.event_messages[message.id] = {
                        'type': event['type'],
                        'id': event['id']
                    }

        
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
                from app.models.session import SessionPlan, SessionRSVP
                from app.models.tournament import Tournament
                from app.models.tournament_rsvp import TournamentRSVP
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
                        event = SessionPlan.query.get(event_id)
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
            from app.models.session import SessionPlan
            from app.models.tournament import Tournament
            from app.models.game import Game
            from app.models.team_organization import TeamOrganization
            from datetime import datetime, timedelta, timezone
            
            # Get events for the next 30 days
            now = datetime.now()
            next_month = now + timedelta(days=30)
            
            # Process each team separately
            teams = TeamOrganization.query.all()
            
            for team in teams:
                team_id = team.id
                
                # Skip teams without Discord settings
                if team_id not in self.team_discord_settings:
                    logger.info(f"No Discord settings for team {team_id}, using default settings")
                    team_discord = {
                        'guild_id': self.guild_id,
                        'calendar_channel_id': self.calendar_channel_id,
                        'notification_channel_id': self.notification_channel_id
                    }
                else:
                    team_discord = self.team_discord_settings[team_id]
                
                guild_id = team_discord.get('guild_id')
                
                if not guild_id:
                    logger.warning(f"No Discord guild ID for team {team_id}, skipping")
                    continue
                
                # Get guild
                try:
                    guild = self.bot.get_guild(int(guild_id))
                    if not guild:
                        logger.error(f"Could not find guild with ID {guild_id} for team {team_id}")
                        continue
                except ValueError:
                    logger.error(f"Invalid guild ID for team {team_id}: {guild_id}")
                    continue
                
                logger.info(f"Processing calendar sync for team {team_id} in guild {guild.name}")
                
                # Get all types of events for this team
                sessions = SessionPlan.query.filter(
                    SessionPlan.date >= now, 
                    SessionPlan.date <= next_month,
                    SessionPlan.team_organization_id == team_id
                ).all()
                
                tournaments = Tournament.query.filter(
                    Tournament.start_date >= now.date(), 
                    Tournament.start_date <= next_month.date(),
                    Tournament.team_organization_id == team_id
                ).all()
                
                games = Game.query.filter(
                    Game.date >= now, 
                    Game.date <= next_month,
                    Game.team_organization_id == team_id
                ).all()
                
                # Get existing Discord events
                try:
                    discord_events = await guild.fetch_scheduled_events()
                    discord_event_names = {event.name: event for event in discord_events}
                except Exception as e:
                    logger.error(f"Error fetching scheduled events for team {team_id}: {str(e)}")
                    discord_event_names = {}
                
                # Sync sessions
                for session in sessions:
                    event_name = f"Training: {session.title}"
                    
                    # Check if event already exists
                    if event_name in discord_event_names:
                        # Update existing event if needed
                        discord_event = discord_event_names[event_name]
                        
                        # Check if event details need updating
                        location = session.location or "TBD"
                        description = f"Training session: {session.title}\n\n"
                        if hasattr(session, 'notes') and session.notes:
                            description += f"{session.notes}\n\n"
                        description += f"RSVP in the app or use the command:\n!uc rsvp session {session.id} [yes/no/maybe]"
                        
                        # Convert date to datetime with timezone
                        if isinstance(session.date, datetime):
                            start_time = session.date.replace(tzinfo=timezone.utc)
                        else:
                            # If it's just a date, convert to datetime
                            start_time = datetime.combine(session.date, datetime.min.time()).replace(tzinfo=timezone.utc)
                        
                        end_time = start_time + timedelta(hours=2)  # Assume 2 hours duration
                        
                        # Check if any details have changed
                        needs_update = (
                            discord_event.description != description or
                            discord_event.location != location or
                            abs((discord_event.start_time - start_time).total_seconds()) > 60 or
                            abs((discord_event.end_time - end_time).total_seconds()) > 60
                        )
                        
                        if needs_update:
                            try:
                                await discord_event.edit(
                                    name=event_name,
                                    description=description,
                                    start_time=start_time,
                                    end_time=end_time,
                                    location=location,
                                    entity_type=discord.EntityType.external,
                                    privacy_level=discord.PrivacyLevel.guild_only
                                )
                                logger.info(f"Updated Discord event for session: {session.title} (Team {team_id})")
                            except Exception as e:
                                logger.error(f"Error updating Discord event for session {session.id} (Team {team_id}): {str(e)}")
                    else:
                        # Create new event
                        location = session.location or "TBD"
                        description = f"Training session: {session.title}\n\n"
                        if hasattr(session, 'notes') and session.notes:
                            description += f"{session.notes}\n\n"
                        description += f"RSVP in the app or use the command:\n!uc rsvp session {session.id} [yes/no/maybe]"
                        
                        try:
                            # Convert date to datetime with timezone
                            if isinstance(session.date, datetime):
                                start_time = session.date.replace(tzinfo=timezone.utc)
                            else:
                                # If it's just a date, convert to datetime
                                start_time = datetime.combine(session.date, datetime.min.time()).replace(tzinfo=timezone.utc)
                            
                            end_time = start_time + timedelta(hours=2)  # Assume 2 hours duration
                            
                            # Add team name to description for clarity
                            description += f"\n\nTeam: {team.name}"
                            
                            await guild.create_scheduled_event(
                                name=event_name,
                                description=description,
                                start_time=start_time,
                                end_time=end_time,
                                location=location,
                                entity_type=discord.EntityType.external,
                                privacy_level=discord.PrivacyLevel.guild_only
                            )
                            logger.info(f"Created Discord event for session: {session.title} (Team {team_id})")
                        except Exception as e:
                            logger.error(f"Error creating Discord event for session {session.id} (Team {team_id}): {str(e)}")
                
                # Sync tournaments
                for tournament in tournaments:
                    event_name = f"Tournament: {tournament.name}"
                    
                    # Check if event already exists
                    if event_name in discord_event_names:
                        # Update existing event if needed
                        discord_event = discord_event_names[event_name]
                        
                        # Check if event details need updating
                        location = tournament.location or "TBD"
                        description = f"Tournament: {tournament.name}\n\n"
                        if hasattr(tournament, 'description') and tournament.description:
                            description += f"{tournament.description}\n\n"
                        description += f"RSVP in the app or use the command:\n!uc rsvp tournament {tournament.id} [attending/not_attending/maybe]"
                        
                        # Use end_date if available, otherwise assume 1 day
                        if hasattr(tournament, 'end_date') and tournament.end_date:
                            end_time = datetime.combine(tournament.end_date, datetime.max.time())
                        else:
                            end_time = datetime.combine(tournament.start_date, datetime.max.time())
                        
                        start_time = datetime.combine(tournament.start_date, datetime.min.time())
                        
                        # Add timezone info
                        start_time = start_time.replace(tzinfo=timezone.utc)
                        end_time = end_time.replace(tzinfo=timezone.utc)
                        
                        # Check if any details have changed
                        needs_update = (
                            discord_event.description != description or
                            discord_event.location != location or
                            abs((discord_event.start_time - start_time).total_seconds()) > 60 or
                            abs((discord_event.end_time - end_time).total_seconds()) > 60
                        )
                        
                        if needs_update:
                            try:
                                await discord_event.edit(
                                    name=event_name,
                                    description=description,
                                    start_time=start_time,
                                    end_time=end_time,
                                    location=location,
                                    entity_type=discord.EntityType.external,
                                    privacy_level=discord.PrivacyLevel.guild_only
                                )
                                logger.info(f"Updated Discord event for tournament: {tournament.name} (Team {team_id})")
                            except Exception as e:
                                logger.error(f"Error updating Discord event for tournament {tournament.id} (Team {team_id}): {str(e)}")
                    else:
                        # Create new event
                        location = tournament.location or "TBD"
                        description = f"Tournament: {tournament.name}\n\n"
                        if hasattr(tournament, 'description') and tournament.description:
                            description += f"{tournament.description}\n\n"
                        description += f"RSVP in the app or use the command:\n!uc rsvp tournament {tournament.id} [attending/not_attending/maybe]"
                        
                        try:
                            # Use end_date if available, otherwise assume 1 day
                            if hasattr(tournament, 'end_date') and tournament.end_date:
                                end_time = datetime.combine(tournament.end_date, datetime.max.time())
                            else:
                                end_time = datetime.combine(tournament.start_date, datetime.max.time())
                            
                            start_time = datetime.combine(tournament.start_date, datetime.min.time())
                            
                            # Add timezone info
                            start_time = start_time.replace(tzinfo=timezone.utc)
                            end_time = end_time.replace(tzinfo=timezone.utc)
                            
                            # Add team name to description for clarity
                            description += f"\n\nTeam: {team.name}"
                            
                            await guild.create_scheduled_event(
                                name=event_name,
                                description=description,
                                start_time=start_time,
                                end_time=end_time,
                                location=location,
                                entity_type=discord.EntityType.external,
                                privacy_level=discord.PrivacyLevel.guild_only
                            )
                            logger.info(f"Created Discord event for tournament: {tournament.name} (Team {team_id})")
                        except Exception as e:
                            logger.error(f"Error creating Discord event for tournament {tournament.id} (Team {team_id}): {str(e)}")
                
                # Sync games
                for game in games:
                    opponent = game.opponent if hasattr(game, 'opponent') else "TBD"
                    event_name = f"Game: vs {opponent}"
                    
                    # Check if event already exists
                    if event_name in discord_event_names:
                        # Update existing event if needed
                        discord_event = discord_event_names[event_name]
                        
                        # Check if event details need updating
                        location = game.location or "TBD"
                        description = f"Game vs {opponent}\n\n"
                        if hasattr(game, 'description') and game.description:
                            description += f"{game.description}\n\n"
                        
                        # Add timezone info to game date
                        if isinstance(game.date, datetime):
                            start_time = game.date.replace(tzinfo=timezone.utc)
                        else:
                            # If it's just a date, convert to datetime
                            start_time = datetime.combine(game.date, datetime.min.time()).replace(tzinfo=timezone.utc)
                            
                        end_time = start_time + timedelta(hours=2)  # Assume 2 hours duration
                        
                        # Check if any details have changed
                        needs_update = (
                            discord_event.description != description or
                            discord_event.location != location or
                            abs((discord_event.start_time - start_time).total_seconds()) > 60 or
                            abs((discord_event.end_time - end_time).total_seconds()) > 60
                        )
                        
                        if needs_update:
                            try:
                                await discord_event.edit(
                                    name=event_name,
                                    description=description,
                                    start_time=start_time,
                                    end_time=end_time,
                                    location=location,
                                    entity_type=discord.EntityType.external,
                                    privacy_level=discord.PrivacyLevel.guild_only
                                )
                                logger.info(f"Updated Discord event for game vs {opponent} (Team {team_id})")
                            except Exception as e:
                                logger.error(f"Error updating Discord event for game {game.id} (Team {team_id}): {str(e)}")
                    else:
                        # Create new event
                        location = game.location or "TBD"
                        description = f"Game vs {opponent}\n\n"
                        if hasattr(game, 'description') and game.description:
                            description += f"{game.description}\n\n"
                        
                        try:
                            # Add timezone info to game date
                            if isinstance(game.date, datetime):
                                start_time = game.date.replace(tzinfo=timezone.utc)
                            else:
                                # If it's just a date, convert to datetime
                                start_time = datetime.combine(game.date, datetime.min.time()).replace(tzinfo=timezone.utc)
                                
                            end_time = start_time + timedelta(hours=2)  # Assume 2 hours duration
                            
                            # Add team name to description for clarity
                            description += f"\n\nTeam: {team.name}"
                            
                            await guild.create_scheduled_event(
                                name=event_name,
                                description=description,
                                start_time=start_time,
                                end_time=end_time,
                                location=location,
                                entity_type=discord.EntityType.external,
                                privacy_level=discord.PrivacyLevel.guild_only
                            )
                            logger.info(f"Created Discord event for game vs {opponent} (Team {team_id})")
                        except Exception as e:
                            logger.error(f"Error creating Discord event for game {game.id} (Team {team_id}): {str(e)}")
                
                # Clean up old events that no longer exist in the database
                current_event_ids = set()
                
                # Add all current session IDs
                for session in sessions:
                    event_name = f"Training: {session.title}"
                    current_event_ids.add(event_name)
                
                # Add all current tournament IDs
                for tournament in tournaments:
                    event_name = f"Tournament: {tournament.name}"
                    current_event_ids.add(event_name)
                
                # Add all current game IDs
                for game in games:
                    opponent = game.opponent if hasattr(game, 'opponent') else "TBD"
                    event_name = f"Game: vs {opponent}"
                    current_event_ids.add(event_name)
                
                # Delete events that are no longer in the database
                for event_name, discord_event in discord_event_names.items():
                    # Only delete events that match our naming pattern and are not in current_event_ids
                    if (event_name.startswith(("Training: ", "Tournament: ", "Game: vs ")) and 
                        event_name not in current_event_ids):
                        try:
                            # Check if this event belongs to our team by looking at the description
                            if hasattr(discord_event, 'description') and discord_event.description:
                                if f"Team: {team.name}" in discord_event.description:
                                    await discord_event.delete()
                                    logger.info(f"Deleted obsolete Discord event: {event_name} (Team {team_id})")
                        except Exception as e:
                            logger.error(f"Error deleting Discord event {event_name} (Team {team_id}): {str(e)}")
            
            logger.info("Calendar sync completed")
    
    except Exception as e:
        logger.error(f"Error during calendar sync: {str(e)}")
        logger.exception(e)  # This will print the full stack trace

    
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
    
    def send_notification(self, title, message, embed=None, team_id=None):
        """Send a notification to the configured channel
        
        Parameters:
        -----------
        title: str
            The notification title
        message: str
            The notification message
        embed: discord.Embed
            Optional embed to include
        team_id: int
            The team organization ID
        
        Returns:
        --------
        bool
            True if successful, False otherwise
        """
        if not self.bot:
            logger.error("Bot not initialized")
            return False
        
        # Get the appropriate channel ID for the team
        notification_channel_id = self.notification_channel_id
        
        if team_id and team_id in self.team_discord_settings:
            team_discord = self.team_discord_settings[team_id]
            notification_channel_id = team_discord.get('notification_channel_id', notification_channel_id)
        
        if not notification_channel_id:
            logger.error(f"Notification channel not configured for team {team_id}")
            return False
        
        async def _send():
            try:
                channel = self.bot.get_channel(int(notification_channel_id))
                if not channel:
                    logger.error(f"Could not find channel with ID {notification_channel_id}")
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