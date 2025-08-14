import discord
import os
import logging
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token from environment variable
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')

# Create intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Create client
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    logger.info(f'Bot logged in as {client.user}')
    logger.info(f'Bot is in {len(client.guilds)} guilds')
    for guild in client.guilds:
        logger.info(f'- {guild.name} (id: {guild.id})')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!hello'):
        await message.channel.send('Hello!')

# Run the client
try:
    logger.info("Starting bot...")
    client.run(TOKEN)
except Exception as e:
    logger.error(f"Error running bot: {str(e)}")
    logger.exception(e)