import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import db
from src.utils import rank_calculator
from src.utils.opgg_client import opgg_client
from datetime import datetime, date, timedelta
import asyncio

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
        # We stored fake PUUID or OPGG ID in puuid field.
        # But OPGG client needs name#tag to search again OR we can try to use stored ID if library supports it.
        # The library's `get_rank_info` takes a Summoner object.
        # We can reconstruct Summoner object if we had enough info, but better to re-search or use ID.
        # For simplicity and robustness (names change), using ID would be better if supported.
        # However, opgg.py v2/v3 mainly searches by name.
        # Re-fetching by name#tag (stored in riot_id) is safest for now.
        
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
        tier, rank, lp = await opgg_client.get_rank_info(summoner)
            
        await db.add_rank_history(discord_id, tier, rank, lp, date.today())


    async def generate_report_table(self, users, today: date, period_days: int) -> str:
        # Determine date range
        start_date = today - timedelta(days=period_days)
        # We want to display all dates in range? Or just those with data?
        # User example: 1/15 | 1/17 ... (dates with data?)
        # "1週間分出したいのであれば7" -> 7 days back.
        
        # Fetch history for all users in one go per user (optimized later, loop for now)
        data_map = {} # {user_id: {date: {tier, rank, lp}}}
        all_dates = set()
        
        for user in users:
            uid = user['discord_id']
            history = await db.get_rank_history(uid, start_date, today)
            user_history = {}
            for h in history:
                d = h['fetch_date'] # datetime.date
                user_history[d] = {'tier': h['tier'], 'rank': h['rank'], 'lp': h['lp']}
                all_dates.add(d)
            data_map[uid] = user_history
            
        sorted_dates = sorted(list(all_dates))
        if not sorted_dates:
            return "表示対象期間にデータがありません。"

        # Formatter helper
        def format_date_header(d):
            return d.strftime("%m/%d")

        # Headers
        # | 日付 | ... dates ... | 比 |
        # Actually user example: empty corner cell? "       1/15|..."
        headers = ["Nom"] + [format_date_header(d) for d in sorted_dates] + ["Diff"]
        
        # Adjust column widths? Use simple CSV-like with pipes or aligned?
        # Aligned is better.
        
        vals = [] # List of rows
        
        for user in users:
            uid = user['discord_id']
            h_map = data_map.get(uid, {})
            
            # User Name
            # We can use riot_id from DB or discord name (requires lookup)
            # User example uses "abc" (looks like short name). RiotID is good.
            name = user['riot_id'].split('#')[0] # Show GameName only for brevity?
            
            row = [name]
            
            for d in sorted_dates:
                entry = h_map.get(d)
                if entry:
                    cell = rank_calculator.format_rank_display(entry['tier'], entry['rank'], entry['lp'])
                else:
                    cell = "-"
                row.append(cell)
            
            # Diff Calculation
            # "前日比" (Yesterday vs Today) and "Period Start vs Today"
            # Today's data
            today_entry = h_map.get(today)
            
            # Yesterday (or latest previous entry?)
            # User example requirement: "前日比は必ず出す"
            yesterday = today - timedelta(days=1)
            yesterday_entry = h_map.get(yesterday)
            
            # If no yesterday entry, maybe use latest available before today? 
            # Requirement says "前日比". If no data for yesterday, maybe "-" or compare with latest?
            # Let's look for yesterday strictly first.
            
            # Period Start (or earliest in range)
            start_entry = h_map.get(sorted_dates[0])
            if start_entry == today_entry: # If start is today (only 1 day data), avoid redundant diff
                start_entry = None

            diff_texts = []
            
            # 1. Yesterday Diff (Strict yesterday or previous available?)
            # "前日比" usually means vs Yesterday.
            if yesterday_entry and today_entry:
                d_text = rank_calculator.calculate_diff_text(yesterday_entry, today_entry)
                diff_texts.append(f"前日比 {d_text}")
            elif today_entry:
                 # Try to find the previous entry if yesterday is missing?
                 # User example shows explicit dates. If 1/15, 1/17... data exists.
                 # If 1/16 is missing, maybe compare with 1/15 as "Previous"?
                 # But "前日比" implies Yesterday. I'll stick to strict yesterday if exists, else "Prev".
                 # Actually, let's just use "Previous Day" if available.
                 pass

            # 2. Period Diff
            if len(sorted_dates) >= 2 and start_entry and today_entry and start_entry != yesterday_entry:
                 # "7日前比" -> Label based on actual days diff?
                 day_diff = (today - sorted_dates[0]).days
                 d_text = rank_calculator.calculate_diff_text(start_entry, today_entry)
                 diff_texts.append(f"{day_diff}日前比 {d_text}")
            elif not diff_texts and today_entry:
                 diff_texts.append("履歴なし")

            row.append(" | ".join(diff_texts))
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
