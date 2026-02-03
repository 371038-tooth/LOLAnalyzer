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
        
        # 1. System-wide Rank Collection Job (Daily 01:00)
        # Records data for the previous day
        self.scheduler.add_job(
            self.fetch_all_users_rank,
            'cron',
            hour=1,
            minute=0,
            second=0,
            name="daily_rank_fetch"
        )

        # 2. User-defined Reporting Jobs
        schedules = await db.get_all_schedules()
        for s in schedules:
            sched_time = s['schedule_time']
            channel_id = s['channel_id']
            period_days = s['period_days']
            
            self.scheduler.add_job(
                self.run_daily_report,
                'cron',
                hour=sched_time.hour,
                minute=sched_time.minute,
                second=sched_time.second,
                args=[channel_id, period_days]
            )
        print(f"Loaded {len(schedules)} reporting schedules and set Fetch Job at 01:00.")

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

    # Test Command Group
    test_group = app_commands.Group(name="test", description="動作確認用のテストコマンドです")

    @test_group.command(name="fetch", description="即座に全ユーザーのランク情報を取得します(01:00の取得と同じ動作)")
    async def test_fetch(self, interaction: discord.Interaction, days_ago: int = 1):
        if not (0 <= days_ago <= 7):
            await interaction.response.send_message("days_ago は 0 から 7 の範囲で指定してください。", ephemeral=True)
            return

        await interaction.response.send_message(f"{days_ago}日前として全ユーザーのランク情報を取得中... (数分かかる場合があります)")
        try:
            results = await self.fetch_all_users_rank(days_ago)
            total = results['total']
            success = results['success']
            failed = results['failed']
            
            msg = f"ランク情報の取得が完了しました。\n"
            msg += f"- 対象ユーザー数: {total}\n"
            msg += f"- 成功: {success}\n"
            msg += f"- 失敗/スキップ: {failed}"
            
            await interaction.followup.send(msg)
        except Exception as e:
            await interaction.followup.send(f"実行中にエラーが発生しました: {e}")

    @test_group.command(name="report", description="即座に指定した日数の集計結果を表示します")
    async def test_report(self, interaction: discord.Interaction, days: int = 7):
        await interaction.response.send_message(f"過去 {days} 日間の集計結果を出力します...")
        try:
            users = await db.get_all_users()
            if not users:
                await interaction.followup.send("登録されているユーザーがいません。`/user add` で登録してください。")
                return

            today = date.today()
            report = await self.generate_report_table(users, today, days)
            
            if len(report) > 1990:
                chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
                for chunk in chunks:
                    await interaction.followup.send(f"```{chunk}```")
            else:
                await interaction.followup.send(f"```{report}```")
        except Exception as e:
            await interaction.followup.send(f"集計出力中にエラーが発生しました: {e}")

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

    async def fetch_all_users_rank(self, days_ago: int = 1):
        print(f"Starting global rank collection (days_ago={days_ago})...")
        # Collection records data for the specified day
        target_date = date.today() - timedelta(days=days_ago)
        users = await db.get_all_users()
        
        results = {'total': len(users), 'success': 0, 'failed': 0}
        
        for user in users:
            try:
                success = await self.fetch_and_save_rank(user, target_date)
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            except Exception as e:
                print(f"Failed to fetch rank for user {user['riot_id']}: {e}")
                results['failed'] += 1
                
        print(f"Global rank collection for {target_date} completed: {results}")
        return results

    async def run_daily_report(self, channel_id: int, period_days: int):
        print(f"Running report for channel {channel_id}")
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"Channel {channel_id} not found.")
            return

        users = await db.get_all_users()
        if not users:
            await channel.send("登録ユーザーがいません。")
            return

        today = date.today()
        
        # Generate Report (fetch_and_save_rank removed from here)
        try:
            report = await self.generate_report_table(users, today, period_days)
            if len(report) > 1990:
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

    async def fetch_and_save_rank(self, user, target_date=None):
        if target_date is None:
            target_date = date.today()

        discord_id = user['discord_id']
        riot_id = user['riot_id'] # Expected "Name#Tag"
        if '#' not in riot_id:
            return False

        name, tag = riot_id.split('#', 1)
        
        # Get Summoner
        from opgg.params import Region
        try:
            summoner = await opgg_client.get_summoner(name, tag, Region.JP)
            if not summoner:
                print(f"User not found on OPGG: {riot_id}")
                return False
                
            # Get Rank
            tier, rank, lp, wins, losses = await opgg_client.get_rank_info(summoner)
            await db.add_rank_history(discord_id, riot_id, tier, rank, lp, wins, losses, target_date)
            return True
        except Exception as e:
            print(f"Error in fetch_and_save_rank for {riot_id}: {e}")
            return False


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
        
        # Determine anchor date for Diff (Latest available in sorted_dates)
        anchor_date = sorted_dates[-1] if sorted_dates else today

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
            # Compare anchor_date with its previous day
            anchor_entry = h_map.get(anchor_date)
            prev_to_anchor = anchor_date - timedelta(days=1)
            prev_entry = h_map.get(prev_to_anchor)
            
            # Period Start (earliest in range)
            start_entry = h_map.get(sorted_dates[0]) if sorted_dates else None
            if start_entry == anchor_entry:
                start_entry = None

            diff_texts = []
            if prev_entry and anchor_entry:
                d_text = rank_calculator.calculate_diff_text(prev_entry, anchor_entry)
                diff_texts.append(f"前日比 {d_text}")
            elif anchor_entry:
                pass

            if len(sorted_dates) >= 2 and start_entry and anchor_entry and start_entry != prev_entry:
                day_diff = (anchor_date - sorted_dates[0]).days
                d_text = rank_calculator.calculate_diff_text(start_entry, anchor_entry)
                diff_texts.append(f"{day_diff}日前比 {d_text}")
            elif not diff_texts and anchor_entry:
                diff_texts.append("履歴なし")

            row.append(" | ".join(diff_texts))

            # Daily W/L Calculation (for anchor_date)
            wl_text = "-"
            if anchor_entry and prev_entry:
                d_wins = anchor_entry['wins'] - prev_entry['wins']
                d_losses = anchor_entry['losses'] - prev_entry['losses']
                if d_wins > 0 or d_losses > 0:
                    wl_text = f"{d_wins}W {d_losses}L"
                else:
                    wl_text = "0戦"
            elif anchor_entry:
                wl_text = "new"

            row.append(wl_text)
            vals.append(row)

        # Build Table String manually for alignment
        def get_display_width(s):
            """Calculate display width considering full-width characters."""
            width = 0
            for char in str(s):
                if ord(char) > 0x7F: # Non-ASCII
                    width += 2
                else:
                    width += 1
            return width

        def pad_string(s, width):
            """Pad string with spaces to reach visual width."""
            s_str = str(s)
            current_w = get_display_width(s_str)
            padding = width - current_w
            return s_str + (" " * max(0, padding))

        # Calculate max visual width for each column
        col_widths = [get_display_width(h) for h in headers]
        for row in vals:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], get_display_width(cell))
        
        # Formatting rows
        # Header
        header_line = "| " + " | ".join([pad_string(h, col_widths[i]) for i, h in enumerate(headers)]) + " |"
        
        # Separator Line
        sep_line = "|-" + "-|-".join(["-" * w for w in col_widths]) + "-|"
        
        lines = [header_line, sep_line]
        for row in vals:
            lines.append("| " + " | ".join([pad_string(c, col_widths[i]) for i, c in enumerate(row)]) + " |")
            
        return "\n".join(lines)

async def setup(bot):
    await bot.add_cog(Scheduler(bot))
