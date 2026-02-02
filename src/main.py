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
        
        # Explicitly add commands defined in this class
        self.add_command(self.ping)
        self.add_command(self.sync)
        
        # Sync slash commands
        await self.tree.sync()
        print("Slash commands synced")

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

    @commands.command()
    async def ping(self, ctx):
        print(f"DEBUG: 'ping' command triggered by {ctx.author}")
        await ctx.send(f'Pong! (Delay: {round(self.latency * 1000)}ms)')

    @commands.command()
    async def sync(self, ctx):
        """Syncs slash commands to the current server immediately."""
        print(f"DEBUG: 'sync' command triggered by {ctx.author}")
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("This command is for administrators only.")
            return
            
        await ctx.send("Syncing slash commands...")
        self.tree.copy_global_to(guild=ctx.guild)
        synced = await self.tree.sync(guild=ctx.guild)
        await ctx.send(f"Synced {len(synced)} commands to this server! You should see / commands now.")

def main():
    # Attempt to get token from environment variables
    raw_token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
    
    if not raw_token:
        print("Error: No Discord token found in environment variables.")
        return

    # Clean the token for robustness (removes potential whitespace/quotes/non-printable chars)
    token = "".join(char for char in raw_token if char.isprintable()).strip().strip('"').strip("'")
    
    # Prefix handling (case-insensitive)
    if token.lower().startswith('bot '):
        token = token[4:].strip()
        
    # Automatic fix for common copy error (missing leading 'M' if token starts with TQ2...)
    if token.startswith('TQ2') and not token.startswith('MTQ2'):
        token = 'M' + token

    bot = LOLBot()
    bot.run(token)

if __name__ == '__main__':
    main()
