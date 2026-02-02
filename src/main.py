import os
import sys
from pathlib import Path

# Add project root to sys.path to ensure 'src' package is found regardless of execution method
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

import discord
from discord.ext import commands
from dotenv import load_dotenv
from src.database import db

# Load environment variables
print("Loading environment variables...")
pre_load_token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')

load_dotenv()

post_load_token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')

if pre_load_token != post_load_token:
    print("Notice: Token was changed after load_dotenv(). This means a .env file might be overriding Railway variables.")

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
    # Attempt to get token from both common environment variable names
    raw_token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
    
    if not raw_token:
        print("Error: Neither DISCORD_BOT_TOKEN nor DISCORD_TOKEN is set.")
        return
    
    # Clean the token: remove whitespace and potential quotes (can happen in some environments)
    token = raw_token.strip().strip('"').strip("'")
    
    # Remove 'Bot ' prefix if user accidentally included it in Railway variables
    if token.lower().startswith('bot '):
        print("Notice: 'Bot ' prefix detected and removed.")
        token = token[4:].strip()
        
    if len(token) > 0:
        # Debug info (Safe fragments)
        print(f"Token loaded (length: {len(token)})")
        print(f"Token fragment for verification: {token[:3]}...{token[-3:]}")
    else:
        print("Error: Cleaned token is empty.")
        
    bot = LOLBot()
    bot.run(token)

if __name__ == '__main__':
    main()
