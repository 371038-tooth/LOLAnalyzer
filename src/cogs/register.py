import discord
from discord import app_commands
from discord.ext import commands
from src.database import db
import asyncio
from src.utils.opgg_client import opgg_client
from opgg.params import Region
import urllib.parse


class Register(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="register_user", description="LoLアカウントを登録します")
    async def register_user(self, interaction: discord.Interaction):
        await interaction.response.send_message("DiscordID(または表示名) を入力してください。自分自身の場合は 'me' と入力するか、何も入力せずにリターンしてください。")

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send("タイムアウトしました。")
            return

        target_input = msg.content.strip()
        target_user = None

        if not target_input or target_input.lower() == 'me':
            target_user = interaction.user
        else:
            # Try to resolve user by ID or Name
            guild = interaction.guild
            if not guild:
                await interaction.followup.send("このコマンドはサーバー内でのみ使用できます。")
                return

            # Check if input is ID
            if target_input.isdigit():
                target_user = guild.get_member(int(target_input))
            
            # If not found by ID, search by name
            if not target_user:
                target_user = discord.utils.find(lambda m: m.name == target_input or m.display_name == target_input, guild.members)

        if not target_user:
            await interaction.followup.send(f"ユーザー '{target_input}' が見つかりませんでした。このサーバーに登録されているユーザーを指定してください。")
            return

        # Proceed to Riot ID
        await interaction.followup.send(f"対象ユーザー: {target_user.display_name}\nRiotID (GameName#TagLine) を入力してください。")

        try:
            riot_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send("タイムアウトしました。")
            return

        riot_id_input = riot_msg.content.strip()
        
        if 'op.gg' in riot_id_input:
             # Parse URL
             try:
                 # Format: https://www.op.gg/summoners/jp/Name-Tag
                 parsed = urllib.parse.urlparse(riot_id_input)
                 path_parts = parsed.path.split('/')
                 # path_parts example: ['', 'summoners', 'jp', 'Name-Tag']
                 if len(path_parts) >= 4 and path_parts[1] == 'summoners':
                     # region = path_parts[2] # We assume JP for now based on context or use mapping
                     # name_tag = path_parts[3]
                     # Decoded: Name-Tag
                     decoded_part = urllib.parse.unquote(path_parts[-1])
                     
                     # Split by last hyphen? Or how is it formatted?
                     # OP.GG URL uses hyphen separator for Name-Tag? 
                     # Actually recently they changed to Name-Tag. But if name has hyphen?
                     # Let's try splitting by '-' from right? Or check #?
                     # Wait, OP.GG URLs for Riot ID usually look like: /summoners/jp/Name-Tag
                     # If users copy-paste, it might be safer to ask "Name#Tag" but we promised URL support.
                     # Let's assume standard format Name-Tag (where Tag is last part after -)
                     # CAUTION: If name contains '-', this is ambiguous.
                     # BUT, Riot ID Tag is usually 3-5 chars alphanumeric.
                     
                     # Simple approach: Split by '-' 
                     # real naming: "Hide on bush-KR1"
                     
                     if '-' in decoded_part:
                         game_name = decoded_part.rsplit('-', 1)[0]
                         tag_line = decoded_part.rsplit('-', 1)[1]
                     else:
                         await interaction.followup.send("URLからNameとTagを特定できませんでした。")
                         return
                 else:
                     await interaction.followup.send("OP.GGのURL形式を認識できませんでした。")
                     return
             except Exception as e:
                 await interaction.followup.send(f"URL解析エラー: {e}")
                 return
        elif '#' in riot_id_input:
            game_name, tag_line = riot_id_input.split('#', 1)
        else:
             await interaction.followup.send("RiotIDの形式が正しくありません。GameName#TagLine の形式、またはOP.GGのURLを入力してください。")
             return

        # Validate with OPGG Client
        try:
            # We assume JP region as default per user context
            summoner = await opgg_client.get_summoner(game_name, tag_line, Region.JP)
            
            if not summoner:
                 await interaction.followup.send(f"ユーザー '{game_name}#{tag_line}' が見つかりませんでした。")
                 return
            
            # Use internal ID as pseudo-PUUID or just empty if not available
            # We must store something in 'puuid' column as it is NOT NULL
            # summoner.summoner_id might be available
            # Let's store "OPGG:{summoner_id}" to distinguish
            fake_puuid = f"OPGG:{summoner.summoner_id}" 
            real_riot_id = f"{summoner.name}#{tag_line.upper()}" # Tag might not be in summoner obj directly if not searched?
            
            # Ideally verify name from summoner object
            # summoner.name should be correct GameName
            
            # Save to DB
            await db.register_user(target_user.id, real_riot_id, fake_puuid)
            await interaction.followup.send(f"登録完了: {target_user.display_name} -> {real_riot_id}")

        except Exception as e:
            # For API errors
            await interaction.followup.send(f"登録処理中にエラーが発生しました。\nError: {e}")
            return




async def setup(bot):
    await bot.add_cog(Register(bot))
