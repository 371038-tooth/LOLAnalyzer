import os
import sys
from pathlib import Path

# Add project root to sys.path to ensure 'src' package is found regardless of execution method
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

import discord
from discord.ext import commands
from src.database import db

# In production (Railway), environment variables are provided directly.
# .env file is no longer used.

class LOLBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True # Needed to search for members
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        # Riot API setup removed
        # OPGG Client is initialized globally in src/utils/opgg_client.py
        # and imported where needed.
            
    async def setup_hook(self):
        # Connect to Database
        await db.connect()
        print("Connected to Database")
        
        # Load extensions
        await self.load_extension('src.cogs.register')
        await self.load_extension('src.cogs.scheduler')
        # Sync slash commands
        await self.tree.sync()
        print("Commands synced")

    async def close(self):
        await db.close()
        await super().close()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')

def main():
    raw_token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
    
    if not raw_token:
        print("Error: Neither DISCORD_BOT_TOKEN nor DISCORD_TOKEN is set in environment variables.")
        return

    # Aggressive cleaning: Remove whitespace, quotes, and hidden control characters
    token = "".join(char for char in raw_token if char.isprintable()).strip().strip('"').strip("'")
    
    # Prefix handling (case-insensitive)
    if token.lower().startswith('bot '):
        token = token[4:].strip()
        
    # AUTOMATIC FIX: If the token is missing the leading 'M' (common copy error)
    if token.startswith('TQ2') and not token.startswith('MTQ2'):
        token = 'M' + token

    # Final check
    bot = LOLBot()
    bot.run(token)

if __name__ == '__main__':
    main()
