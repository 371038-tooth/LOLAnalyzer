import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import db
from src.utils import rank_calculator
from src.utils.opgg_client import opgg_client
from datetime import datetime, date, timedelta
import asyncio
import re

class Scheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()

    async def cog_load(self):
        await self.reload_schedules()

    async def reload_schedules(self):
        self.scheduler.remove_all_jobs()
        schedules = await db.get_all_schedules()
        
        for s in schedules:
            # s['schedule_time'] is a datetime.time object
            sched_time = s['schedule_time']
            channel_id = s['channel_id']
            period_days = s['period_days']
            
            self.scheduler.add_job(
                self.run_daily_task,
                'cron',
                hour=sched_time.hour,
                minute=sched_time.minute,
                second=sched_time.second,
                args=[channel_id, period_days]
            )
        print(f"Loaded {len(schedules)} schedules.")

    # Schedule Command Group
    schedule_group = app_commands.Group(name="schedule", description="定期実行スケジュールを管理します")

    @schedule_group.command(name="show", description="現在登録されているスケジュールの一覧を表示します")
    async def schedule_show(self, interaction: discord.Interaction):
        schedules = await db.get_all_schedules()
        if not schedules:
            await interaction.response.send_message("登録されているスケジュールはありません。")
            return

        msg = "**登録スケジュール一覧**\n"
        for s in schedules:
            # s['schedule_time'] might be time object
            t = s['schedule_time']
            t_str = t.strftime("%H:%M") if hasattr(t, 'strftime') else str(t)
            msg += f"ID: {s['id']} | 時間: {t_str} | Ch: {s['channel_id']} | 期間: {s['period_days']}日\n"
        
        await interaction.response.send_message(msg)

    @schedule_group.command(name="add", description="スケジュールを登録します")
    async def schedule_add(self, interaction: discord.Interaction):
        await interaction.response.send_message("登録するスケジュールを入力してください。\n形式: `時間(HH:MM) チャンネル(ID or here) 期間(日数)`\n例: `21:00 here 7`")

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send("タイムアウトしました。")
            return

        time_str, channel_id, period_days, error = self.parse_schedule_input(msg.content, interaction.channel.id)
        if error:
            await interaction.followup.send(error)
            return

        try:
            await db.register_schedule(time_str, channel_id, interaction.user.id, period_days)
            await self.reload_schedules()
            await interaction.followup.send(f"スケジュール登録完了: {time_str} にチャンネル {channel_id} へ通知 ({period_days}日分)")
        except Exception as e:
            await interaction.followup.send(f"エラーが発生しました: {e}")

    @schedule_group.command(name="del", description="スケジュールIDを指定して削除します")
    async def schedule_del(self, interaction: discord.Interaction, schedule_id: int):
        s = await db.get_schedule_by_id(schedule_id)
        if not s:
            await interaction.response.send_message(f"スケジュールID {schedule_id} は存在しません。", ephemeral=True)
            return

        try:
            await db.delete_schedule(schedule_id)
            await self.reload_schedules()
            await interaction.response.send_message(f"スケジュールID {schedule_id} を削除しました。")
        except Exception as e:
            await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)

    @schedule_group.command(name="edit", description="スケジュールIDを指定してスケジュールを変更します")
    async def schedule_edit(self, interaction: discord.Interaction, schedule_id: int):
        s = await db.get_schedule_by_id(schedule_id)
        if not s:
            await interaction.response.send_message(f"スケジュールID {schedule_id} は存在しません。", ephemeral=True)
            return

        current_time = s['schedule_time'].strftime("%H:%M") if hasattr(s['schedule_time'], 'strftime') else str(s['schedule_time'])
        await interaction.response.send_message(f"変更内容を入力してください (ID: {schedule_id})\n現在の設定: `{current_time} {s['channel_id']} {s['period_days']}`\n形式: `時間 チャンネル 期間` (例: `22:00 here 7`)")

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send("タイムアウトしました。")
            return

        time_str, channel_id, period_days, error = self.parse_schedule_input(msg.content, interaction.channel.id)
        if error:
            await interaction.followup.send(error)
            return

        try:
            await db.update_schedule(schedule_id, time_str, channel_id, period_days)
            await self.reload_schedules()
            await interaction.followup.send(f"スケジュールID {schedule_id} を更新しました。")
        except Exception as e:
            await interaction.followup.send(f"エラーが発生しました: {e}")

    @schedule_group.command(name="help", description="scheduleコマンドの使い方を表示します")
    async def schedule_help(self, interaction: discord.Interaction):
        msg = """
**schedule コマンドの使い方**
`/schedule show` : 現在登録されているスケジュールの一覧を表示します。
`/schedule add` : 新しいスケジュールを登録します。対話形式で `時間 チャンネル 期間` を入力します。
`/schedule del schedule_id` : 指定したIDのスケジュールを削除します。
`/schedule edit schedule_id` : 指定したIDのスケジュールを変更します。

**入力形式の例**
`21:00 here 7` : 毎日21時に、このチャンネルに、過去7日間のレポートを表示
`09:30 1234567890 3` : 毎日9:30に、チャンネルID 1234567890 に、過去3日間のレポートを表示
"""
        await interaction.response.send_message(msg)

    def parse_schedule_input(self, text: str, current_channel_id: int):
        # Normalize spaces
        parts = text.strip().split()
        if len(parts) < 3:
            return None, None, None, "入力形式が正しくありません。`時間 チャンネル 期間` の順で入力してください。(例: 21:00 here 7)"

        # Simple heuristic parsing (Expect Time Channel Period order, but try to be flexible if distinct)
        # Time usually has ':'
        # Channel is 'here' or long digits
        # Period is small digits

        # Let's try strict order first as per example instructions, but example was `21:00 here 7`
        
        t_str = parts[0]
        c_str = parts[1]
        p_str = parts[2]

        # Validate Time
        if ':' not in t_str:
             return None, None, None, "時間の形式が正しくありません (例: 21:00)"
        
        # Validate Channel
        channel_id = None
        if c_str.lower() == 'here':
            channel_id = current_channel_id
        elif c_str.isdigit():
            channel_id = int(c_str)
        else:
             return None, None, None, "チャンネル指定が正しくありません ('here' または ID)"

        # Validate Period
        if not p_str.isdigit():
             return None, None, None, "期間（日数）は数値で入力してください"
        period_days = int(p_str)

        return t_str, channel_id, period_days, None


    async def run_daily_task(self, channel_id: int, period_days: int):
        print(f"Running task for channel {channel_id}")
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"Channel {channel_id} not found.")
            return

        users = await db.get_all_users()
        if not users:
            await channel.send("登録ユーザーがいません。")
            return

        today = date.today()
        
        # 1. Fetch and Save current rank for all users
        for user in users:
            try:
                await self.fetch_and_save_rank(user)
            except Exception as e:
                print(f"Failed to fetch rank for user {user['riot_id']}: {e}")

        # 2. Generate Report
        try:
            report = await self.generate_report_table(users, today, period_days)
            # Discord message limit is 2000. If report is too long, we might need to split it.
            # Simple splitting by line
            if len(report) > 1990:
                # Basic chunking
                chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
                for chunk in chunks:
                    await channel.send(f"```{chunk}```")
            else:
                await channel.send(f"```{report}```")

        except Exception as e:
            await channel.send(f"レポート生成中にエラーが発生しました: {e}")
            print(e)
            import traceback
            traceback.print_exc()

    async def fetch_and_save_rank(self, user):
        discord_id = user['discord_id']
        riot_id = user['riot_id'] # Expected "Name#Tag"
        if '#' not in riot_id:
            # Fallback or error
            return

        name, tag = riot_id.split('#', 1)
        
        # Get Summoner
        # Using JP region default
        from opgg.params import Region
        summoner = await opgg_client.get_summoner(name, tag, Region.JP)
        
        if not summoner:
            # User might have changed name or OPGG issue
            print(f"User not found on OPGG: {riot_id}")
            # Could insert a 'skipped' record or just ignore
            return
            
        # Get Rank
        tier, rank, lp, wins, losses = await opgg_client.get_rank_info(summoner)
            
        await db.add_rank_history(discord_id, riot_id, tier, rank, lp, wins, losses, date.today())


    async def generate_report_table(self, users, today: date, period_days: int) -> str:
        # Determine date range
        start_date = today - timedelta(days=period_days)
        
        # Fetch history for all users
        data_map = {} # {(discord_id, riot_id): {date: {tier, rank, lp, wins, losses}}}
        all_dates = set()
        
        for user in users:
            uid = user['discord_id']
            rid = user['riot_id']
            history = await db.get_rank_history(uid, rid, start_date, today)
            user_history = {}
            for h in history:
                d = h['fetch_date'] # datetime.date
                user_history[d] = {
                    'tier': h['tier'], 
                    'rank': h['rank'], 
                    'lp': h['lp'],
                    'wins': h['wins'],
                    'losses': h['losses']
                }
                all_dates.add(d)
            data_map[(uid, rid)] = user_history
            
        sorted_dates = sorted(list(all_dates))
        if not sorted_dates:
            return "表示対象期間にデータがありません。"

        # Formatter helper
        def format_date_header(d):
            return d.strftime("%m/%d")

        # Headers
        headers = ["Nom"] + [format_date_header(d) for d in sorted_dates] + ["Diff", "W/L"]
        
        vals = [] # List of rows
        
        for user in users:
            uid = user['discord_id']
            rid = user['riot_id']
            h_map = data_map.get((uid, rid), {})
            
            # User Name
            name = rid.split('#')[0]
            
            row = [name]
            
            for d in sorted_dates:
                entry = h_map.get(d)
                if entry:
                    cell = rank_calculator.format_rank_display(entry['tier'], entry['rank'], entry['lp'])
                else:
                    cell = "-"
                row.append(cell)
            
            # Diff Calculation
            today_entry = h_map.get(today)
            yesterday = today - timedelta(days=1)
            yesterday_entry = h_map.get(yesterday)
            
            # Period Start (or earliest in range)
            start_entry = h_map.get(sorted_dates[0])
            if start_entry == today_entry:
                start_entry = None

            diff_texts = []
            if yesterday_entry and today_entry:
                d_text = rank_calculator.calculate_diff_text(yesterday_entry, today_entry)
                diff_texts.append(f"前日比 {d_text}")
            elif today_entry:
                pass

            if len(sorted_dates) >= 2 and start_entry and today_entry and start_entry != yesterday_entry:
                day_diff = (today - sorted_dates[0]).days
                d_text = rank_calculator.calculate_diff_text(start_entry, today_entry)
                diff_texts.append(f"{day_diff}日前比 {d_text}")
            elif not diff_texts and today_entry:
                diff_texts.append("履歴なし")

            row.append(" | ".join(diff_texts))

            # Daily W/L Calculation
            wl_text = "-"
            if today_entry and yesterday_entry:
                d_wins = today_entry['wins'] - yesterday_entry['wins']
                d_losses = today_entry['losses'] - yesterday_entry['losses']
                if d_wins > 0 or d_losses > 0:
                    wl_text = f"{d_wins}W {d_losses}L"
                else:
                    wl_text = "0戦"
            elif today_entry:
                wl_text = "new"

            row.append(wl_text)
            vals.append(row)

        # Build Table String manually for alignment
        # Calculate max width for each column
        col_widths = [len(h) for h in headers]
        for row in vals:
            for i, cell in enumerate(row):
                # Handle extended ascii chars width? (Japanese chars are wide)
                # Simple len() is inaccurate for JP text alignment.
                # But for Discord code block, it's monospaced but JP chars are double width.
                # `wcwidth` lib is good but external.
                # For now use loose alignment.
                col_widths[i] = max(col_widths[i], len(str(cell))) # Python len counts chars, not display width
        
        # Formatting rows
        # Since I can't guarantee font width in Discord mobile vs desktop,
        # I'll stick to simple pipe separation.
        
        # Header
        header_line = "| " + " | ".join(headers) + " |"
        
        # Separator (optional)
        # sep_line = "| " + " | ".join(["-" * w for w in col_widths]) + " |"
        
        lines = [header_line]
        for row in vals:
            lines.append("| " + " | ".join([str(c) for c in row]) + " |")
            
        return "\n".join(lines)

async def setup(bot):
    await bot.add_cog(Scheduler(bot))
