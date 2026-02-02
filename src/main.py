import os
import sys
from pathlib import Path

# Add project root to sys.path to ensure 'src' package is found
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

import discord
from discord.ext import commands
from src.database import db

class LOLBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
            
    async def setup_hook(self):
        # Connect to Database
        await db.connect()
        print("Connected to Database")
        
        # Load extensions
        await self.load_extension('src.cogs.register')
        await self.load_extension('src.cogs.scheduler')
        await self.load_extension('src.cogs.utils')
        
        # Sync slash commands
        await self.tree.sync()
        print("Global slash commands synced")

    async def on_message(self, message):
        if message.author.bot:
            return
        
        # Logging to see if messages are reaching the bot
        print(f"DEBUG: Message from {message.author} in {message.channel}: {message.content}")
        
        await self.process_commands(message)

    async def close(self):
        await db.close()
        await super().close()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')

def main():
    # Attempt to get token from environment variables
    raw_token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
    
    if not raw_token:
        print("Error: No Discord token found in environment variables.")
        return

    # Clean the token for robustness
    token = "".join(char for char in raw_token if char.isprintable()).strip().strip('"').strip("'")
    
    # Prefix handling (case-insensitive)
    if token.lower().startswith('bot '):
        token = token[4:].strip()
        
    # Automatic fix for common copy error
    if token.startswith('TQ2') and not token.startswith('MTQ2'):
        token = 'M' + token

    bot = LOLBot()
    bot.run(token)

if __name__ == '__main__':
    main()
