import os
import sys
from pathlib import Path

# Add project root to sys.path
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

import discord
from discord.ext import commands
from src.database import db

# --- START OF DIAGNOSTIC HEADER ---
print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
print("!!!   FINAL DIAGNOSTIC VERSION: 2026-02-03 01:15     !!!")
print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
# --- END OF DIAGNOSTIC HEADER ---

class LOLBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents, help_command=None)
            
    async def setup_hook(self):
        await db.connect()
        await self.load_extension('src.cogs.register')
        await self.load_extension('src.cogs.scheduler')
        await self.tree.sync()
        print("Bot is ready and commands synced.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')

def main():
    print("--- EXECUTION START: 01:15 ---")
    
    # Priority: DISCORD_BOT_TOKEN -> DISCORD_TOKEN
    raw_token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
    
    if not raw_token:
        print("ERROR: NO TOKEN FOUND IN ENV VARS")
        return

    # ABSOLUTE TRUTH: Show exactly what is in the env var (first 5 and last 5)
    # We use repr() to see hidden characters
    clean_repr = repr(raw_token.strip())
    print(f"DIAGNOSTIC - RAW LENGTH: {len(raw_token)}")
    print(f"DIAGNOSTIC - STARTS WITH: {raw_token.strip()[:5]}")
    print(f"DIAGNOSTIC - ENDS WITH: {raw_token.strip()[-5:]}")

    # Aggressive cleaning
    token = "".join(char for char in raw_token if char.isprintable()).strip().strip('"').strip("'")
    
    if token.lower().startswith('bot '):
        token = token[4:].strip()
        
    if token.startswith('TQ2') and not token.startswith('MTQ2'):
        token = 'M' + token

    bot = LOLBot()
    bot.run(token)

if __name__ == '__main__':
    main()
