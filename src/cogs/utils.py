import discord
from discord import app_commands
from discord.ext import commands

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        """Botの生存確認用コマンド"""
        print(f"DEBUG: 'ping' command triggered by {ctx.author}")
        latency = round(self.bot.latency * 1000)
        await ctx.send(f'Pong! (応答速度: {latency}ms)')

    @commands.command()
    async def sync(self, ctx):
        """スラッシュコマンドを現在のサーバーに強制同期します"""
        print(f"DEBUG: 'sync' command triggered by {ctx.author}")
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("このコマンドは管理者専用です。")
            return
            
        await ctx.send("スラッシュコマンドを同期中...")
        try:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"{len(synced)} 件のコマンドをこのサーバーに同期しました。/コマンドが使えるようになっているはずです。")
        except Exception as e:
            await ctx.send(f"同期中にエラーが発生しました: {e}")

async def setup(bot):
    await bot.add_cog(Utils(bot))
