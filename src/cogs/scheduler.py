import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import db
from src.utils import rank_calculator
from src.utils.opgg_client import opgg_client
from src.utils.opgg_compat import Region, OPGG, IS_V2
from src.utils.graph_generator import generate_rank_graph
from datetime import datetime, date, timedelta
import asyncio
import io
import logging

logger = logging.getLogger(__name__)

class Scheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()

    async def cog_load(self):
        await self.reload_schedules()

    async def reload_schedules(self):
        self.scheduler.remove_all_jobs()
        
        # 1. System-wide Rank Collection Job (Daily 23:55)
        # Records data for the current day
        self.scheduler.add_job(
            self.fetch_all_users_rank,
            'cron',
            hour=23,
            minute=55,
            second=0,
            name="daily_rank_fetch"
        )

        # 2. User-defined Reporting Jobs
        schedules = await db.get_all_schedules()
        for s in schedules:
            sched_time = s['schedule_time']
            channel_id = s['channel_id']
            period_days = s['period_days']
            
            if s['status'] != 'ENABLED':
                continue

            self.scheduler.add_job(
                self.run_daily_report,
                'cron',
                hour=sched_time.hour,
                minute=sched_time.minute,
                second=sched_time.second,
                args=[channel_id, period_days, s['output_type']]
            )
        print(f"Loaded {len(schedules)} reporting schedules and set Fetch Job at 01:00.")

    @app_commands.command(name="graph", description="指定したユーザーのランク推移をグラフで表示します")
    @app_commands.describe(
        riot_id="表示するユーザーのRiot ID (例: Name#Tag)",
        period="表示期間 (daily:1週間, weekly:2ヶ月, monthly:6ヶ月)",
        force_fetch="最新の履歴をOPGGから取得して更新するか (default: False)"
    )
    async def graph(self, interaction: discord.Interaction, riot_id: str, period: str = "daily", force_fetch: bool = False):
        await interaction.response.defer()
        
        # Validate period
        # Calculate start date
        today_date = date.today()
        if period == "daily":
            start_date = today_date - timedelta(days=7)
        elif period == "weekly":
            start_date = today_date - timedelta(days=60)
        else: # monthly
            start_date = today_date - timedelta(days=180)

        # "all" support
        if riot_id.lower() == "all":
            users = await db.get_all_users()
            if not users:
                await interaction.followup.send("登録されているユーザーがいません。")
                return
            
            user_data = {}
            for u in users:
                rows = await db.get_rank_history_for_graph(u['discord_id'], u['riot_id'], start_date)
                if rows:
                    user_data[u['riot_id']] = [dict(r) for r in rows]
            
            if not user_data:
                await interaction.followup.send("表示するデータがありません。")
                return
                
            buf = generate_rank_graph(user_data, period, " (All Users)")
            if not buf:
                await interaction.followup.send("グラフの生成に失敗しました。")
                return
            
            file = discord.File(fp=buf, filename="all_rank_graph.png")
            await interaction.followup.send(f"**全員** のランク推移 ({period})", file=file)
            return

        # Single user logic
        # Find user in DB
        user = await db.get_user_by_riot_id(riot_id)
        if not user:
            await interaction.followup.send(f"ユーザー {riot_id} は登録されていません。", ephemeral=True)
            return

        discord_id = user['discord_id']
        
        # Force fetch if requested
        if force_fetch:
            try:
                # Need summoner object to get internal ID
                name, tag = riot_id.split('#')
                summoner = await opgg_client.get_summoner(name, tag, Region.JP)
                if summoner:
                    history = await opgg_client.get_tier_history(summoner.summoner_id, Region.JP)
                    for entry in history:
                        # Map OPGG history to rank_history
                        h_date = entry['updated_at'].date()
                        await db.add_rank_history(
                            discord_id, riot_id, 
                            entry['tier'], entry['rank'], entry['lp'],
                            0, 0, h_date
                        )
            except Exception as e:
                print(f"Error during force fetch: {e}")

        # Fetch data from DB
        rows = await db.get_rank_history_for_graph(discord_id, riot_id, start_date)
        
        if not rows:
            await interaction.followup.send("表示するデータがありません。(`/test fetch` でデータを取得してください)")
            return

        # Generate Graph
        row_dicts = [dict(r) for r in rows]
        buf = generate_rank_graph({riot_id: row_dicts}, period, f": {riot_id.split('#')[0]}")
        if not buf:
            await interaction.followup.send("グラフの生成に失敗しました。")
            return

        file = discord.File(fp=buf, filename="rank_graph.png")
        await interaction.followup.send(f"**{riot_id}** のランク推移 ({period})", file=file)

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
            status_emoji = "✅" if s['status'] == 'ENABLED' else "❌"
            msg += f"{status_emoji} ID: {s['id']} | 時間: {t_str} | Ch: {s['channel_id']} | 期間: {s['period_days']}日 | 形式: {s['output_type']}\n"
        
        await interaction.response.send_message(msg)

    @schedule_group.command(name="add", description="スケジュールを登録します")
    async def schedule_add(self, interaction: discord.Interaction):
        await interaction.response.send_message("登録するスケジュールを入力してください。\n形式: `時間(HH:MM) チャンネル(ID/here) 期間(日) 出力形式(table/graph)`\n例: `21:00 here 7 graph`")

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send("タイムアウトしました。")
            return

        time_str, channel_id, period_days, output_type, error = self.parse_schedule_input(msg.content, interaction.channel.id)
        if error:
            await interaction.followup.send(error)
            return

        try:
            await db.register_schedule(time_str, channel_id, interaction.user.id, period_days, output_type)
            await self.reload_schedules()
            await interaction.followup.send(f"スケジュール登録完了: {time_str} にチャンネル {channel_id} へ通知 ({period_days}日分, 形式: {output_type})")
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

    @schedule_group.command(name="enable", description="スケジュールを有効にします")
    async def schedule_enable(self, interaction: discord.Interaction, schedule_id: int):
        s = await db.get_schedule_by_id(schedule_id)
        if not s:
            await interaction.response.send_message(f"スケジュールID {schedule_id} は存在しません。", ephemeral=True)
            return
        await db.set_schedule_status(schedule_id, 'ENABLED')
        await self.reload_schedules()
        await interaction.response.send_message(f"スケジュールID {schedule_id} を有効にしました。")

    @schedule_group.command(name="disable", description="スケジュールを無効にします")
    async def schedule_disable(self, interaction: discord.Interaction, schedule_id: int):
        s = await db.get_schedule_by_id(schedule_id)
        if not s:
            await interaction.response.send_message(f"スケジュールID {schedule_id} は存在しません。", ephemeral=True)
            return
        await db.set_schedule_status(schedule_id, 'DISABLED')
        await self.reload_schedules()
        await interaction.response.send_message(f"スケジュールID {schedule_id} を無効にしました。")

    @schedule_group.command(name="edit", description="スケジュールIDを指定してスケジュールを変更します")
    async def schedule_edit(self, interaction: discord.Interaction, schedule_id: int):
        s = await db.get_schedule_by_id(schedule_id)
        if not s:
            await interaction.response.send_message(f"スケジュールID {schedule_id} は存在しません。", ephemeral=True)
            return

        current_time = s['schedule_time'].strftime("%H:%M") if hasattr(s['schedule_time'], 'strftime') else str(s['schedule_time'])
        await interaction.response.send_message(f"変更内容を入力してください (ID: {schedule_id})\n現在の設定: `{current_time} {s['channel_id']} {s['period_days']} {s['output_type']}`\n形式: `時間 チャンネル 期間 形式` (例: `22:00 here 7 graph`)")

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send("タイムアウトしました。")
            return

        time_str, channel_id, period_days, output_type, error = self.parse_schedule_input(msg.content, interaction.channel.id)
        if error:
            await interaction.followup.send(error)
            return

        try:
            await db.update_schedule(schedule_id, time_str, channel_id, period_days, output_type)
            await self.reload_schedules()
            await interaction.followup.send(f"スケジュールID {schedule_id} を更新しました。")
        except Exception as e:
            await interaction.followup.send(f"エラーが発生しました: {e}")

    @schedule_group.command(name="help", description="scheduleコマンドの使い方を表示します")
    async def schedule_help(self, interaction: discord.Interaction):
        msg = """
**schedule コマンドの使い方**
`/schedule show` : 現在登録されているスケジュールの一覧を表示します。
`/schedule add` : 新しいスケジュールを登録します。対話形式で `時間 チャンネル 期間 形式` を入力します。
`/schedule edit schedule_id` : 指定したIDのスケジュールを変更します。
`/schedule enable schedule_id` : スケジュールを有効化します。
`/schedule disable schedule_id` : スケジュールを無効化します。
`/schedule del schedule_id` : 指定したIDのスケジュールを削除します。

**形式について**
`table`: 見やすい表形式で出力
`graph`: 登録ユーザー全員の推移を1つのグラフで出力

**入力形式の例**
`21:00 here 7 table` : 毎日21時に、このチャンネルに、過去7日間のレポートを表で表示
`09:30 1234567890 3 graph` : 毎日9:30に、チャンネルID 1234567890 に、過去3日間のレポートをグラフで表示
"""
        await interaction.response.send_message(msg)

    @app_commands.command(name="fetch", description="指定したユーザーの現在のランク情報を取得してDBに登録します")
    @app_commands.describe(riot_id="対象ユーザーのRiot ID (例: Name#Tag) または 'all' で全ユーザー")
    async def fetch(self, interaction: discord.Interaction, riot_id: str):
        await interaction.response.defer()
        try:
            if riot_id.lower() == "all":
                results = await self.fetch_all_users_rank()
                await interaction.followup.send(f"✅ 全ユーザーのランク情報を取得しました: 成功 {results['success']}, 失敗 {results['failed']} (合計 {results['total']})")
                return

            # Find user in DB
            user = await db.get_user_by_riot_id(riot_id)
            if not user:
                await interaction.followup.send(f"ユーザー `{riot_id}` は登録されていません。`/user add` で登録してください。")
                return
            
            # Fetch and save current rank
            success = await self.fetch_and_save_rank(user)
            if success:
                # Get the latest rank from DB to display
                today = date.today()
                history = await db.get_rank_history(user['discord_id'], riot_id, today, today)
                if history:
                    h = history[0]
                    rank_display = rank_calculator.format_rank_display(h['tier'], h['rank'], h['lp'])
                    await interaction.followup.send(f"✅ `{riot_id}` のランク情報を取得しました: **{rank_display}**")
                else:
                    await interaction.followup.send(f"✅ `{riot_id}` のランク情報を取得しましたが、履歴の確認に失敗しました。")
            else:
                await interaction.followup.send(f"❌ `{riot_id}` のランク情報取得に失敗しました。OPGGで見つからないか、エラーが発生しました。")
        except Exception as e:
            logger.error(f"Error in fetch command: {e}", exc_info=True)
            await interaction.followup.send(f"実行中にエラーが発生しました: {e}")

    @app_commands.command(name="report", description="指定した日数の集計結果を表示します")
    @app_commands.describe(days="集計期間 (日数、デフォルト: 7)")
    async def report(self, interaction: discord.Interaction, days: int = 7):
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
            logger.error(f"Error in report command: {e}", exc_info=True)
            await interaction.followup.send(f"集計出力中にエラーが発生しました: {e}")

    def parse_schedule_input(self, text: str, current_channel_id: int):
        parts = text.strip().split()
        if len(parts) < 4:
            return None, None, None, None, "入力形式が正しくありません。`時間 チャンネル 期間 形式` の順で入力してください。(例: 21:00 here 7 graph)"
        
        t_str = parts[0]
        c_str = parts[1]
        p_str = parts[2]
        o_str = parts[3].lower()

        # Validate Time
        if ':' not in t_str:
             return None, None, None, None, "時間の形式が正しくありません (例: 21:00)"
        
        # Validate Channel
        channel_id = None
        if c_str.lower() == 'here':
            channel_id = current_channel_id
        elif c_str.isdigit():
            channel_id = int(c_str)
        else:
             return None, None, None, None, "チャンネル指定が正しくありません ('here' または ID)"

        # Validate Period
        if not p_str.isdigit():
             return None, None, None, None, "期間（日数）は数値で入力してください"
        period_days = int(p_str)

        # Validate Output Type
        if o_str not in ['table', 'graph']:
            return None, None, None, None, "出力形式は `table` または `graph` を指定してください"

        return t_str, channel_id, period_days, o_str, None

    async def fetch_all_users_rank(self, backfill: bool = False):
        """Fetch current rank and optionally backfill history."""
        logger.info(f"Starting global rank collection (backfill={backfill})...")
        today = date.today()
        users = await db.get_all_users()
        
        results = {'total': len(users), 'success': 0, 'failed': 0}
        
        for user in users:
            uid = user['discord_id']
            rid = user['riot_id']
            try:
                # 1. Fetch Current
                success = await self.fetch_and_save_rank(user, today)
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
                
                # 2. Backfill if requested
                if backfill and '#' in rid:
                    name, tag = rid.split('#')
                    summoner = await opgg_client.get_summoner(name, tag, Region.JP)
                    if summoner:
                        history = await opgg_client.get_tier_history(summoner.summoner_id, Region.JP)
                        for entry in history:
                            h_date = entry['updated_at'].date()
                            # Avoid overwriting today's report
                            if h_date < today:
                                await db.add_rank_history(
                                    uid, rid, 
                                    entry['tier'], entry['rank'], entry['lp'],
                                    0, 0, h_date
                                )
                
                await asyncio.sleep(1) # Base rate limiting
            except Exception as e:
                logger.error(f"Failed to fetch rank for user {rid}: {e}")
                results['failed'] += 1
                
        logger.info(f"Global rank collection completed: {results}")
        return results

    async def run_daily_report(self, channel_id: int, period_days: int, output_type: str = 'table'):
        print(f"Running report for channel {channel_id} (type: {output_type})")
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"Channel {channel_id} not found.")
            return

        users = await db.get_all_users()
        if not users:
            await channel.send("登録ユーザーがいません。")
            return

        today = date.today()
        
        try:
            if output_type == 'graph':
                # Generate multi-user graph
                start_date = today - timedelta(days=period_days)
                user_data = {}
                for u in users:
                    rows = await db.get_rank_history_for_graph(u['discord_id'], u['riot_id'], start_date)
                    if rows:
                        user_data[u['riot_id']] = [dict(r) for r in rows]
                
                if not user_data:
                    await channel.send(f"過去 {period_days} 日間のグラフデータがありません。")
                    return

                buf = generate_rank_graph(user_data, "daily" if period_days <= 14 else "weekly", " (All - Scheduled)")
                if buf:
                    file = discord.File(fp=buf, filename="scheduled_graph.png")
                    await channel.send(content=f"**定期レポート (過去{period_days}日間)**", file=file)
                else:
                    await channel.send("グラフの生成に失敗しました。")
            else:
                # Table output
                report = await self.generate_report_table(users, today, period_days)
                if len(report) > 1990:
                    chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
                    for chunk in chunks:
                        await channel.send(f"```{chunk}```")
                else:
                    await channel.send(f"```{report}```")

        except Exception as e:
            await channel.send(f"レポート生成中にエラーが発生しました: {e}")
            logger.error(f"Error in scheduled report: {e}", exc_info=True)

    async def fetch_and_save_rank(self, user, target_date=None):
        if target_date is None:
            target_date = date.today()

        discord_id = user['discord_id']
        riot_id = user['riot_id'] # Expected "Name#Tag"
        if '#' not in riot_id:
            return False

        name, tag = riot_id.split('#', 1)
        
        # Get Summoner
        try:
            logger.info(f"Fetching rank for {riot_id} on {target_date}")
            summoner = await opgg_client.get_summoner(name, tag, Region.JP)
            if not summoner:
                logger.warning(f"User not found on OPGG: {riot_id}")
                return False
                
            # Get Rank
            tier, rank, lp, wins, losses = await opgg_client.get_rank_info(summoner)
            logger.info(f"Rank info for {riot_id}: {tier} {rank} {lp}LP (W:{wins} L:{losses})")
            await db.add_rank_history(discord_id, riot_id, tier, rank, lp, wins, losses, target_date)
            return True
        except Exception as e:
            logger.error(f"Error in fetch_and_save_rank for {riot_id}: {e}", exc_info=True)
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

        # Helper for W/L record
        def format_record(start, end):
            if not start or not end:
                return "ランク戦情報なし"
            w = end['wins'] - start['wins']
            l = end['losses'] - start['losses']
            g = w + l
            if g <= 0:
                return "ランク戦情報なし"
            rate = (w / g * 100) if g > 0 else 0
            return f"{g}戦{w}勝 勝率{int(rate)}％"

        # Headers
        headers = ["RIOT ID"] + [format_date_header(d) for d in sorted_dates] + ["前日比", f"{period_days}日比", "戦績（前日）", f"戦績（{period_days}日分）"]
        
        # Determine anchor date for Diff (Latest available in sorted_dates)
        anchor_date = sorted_dates[-1] if sorted_dates else today

        vals = [] # List of rows
        
        for user in users:
            uid = user['discord_id']
            rid = user['riot_id']
            h_map = data_map.get((uid, rid), {})
            
            # User Name - show full Riot ID including tag
            name = rid
            
            row = [name]
            
            for d in sorted_dates:
                entry = h_map.get(d)
                if entry:
                    cell = rank_calculator.format_rank_display(entry['tier'], entry['rank'], entry['lp'])
                else:
                    cell = "-"
                row.append(cell)
            
            # 1. 前日比 (Daily Diff)
            anchor_entry = h_map.get(anchor_date)
            prev_to_anchor = anchor_date - timedelta(days=1)
            prev_entry = h_map.get(prev_to_anchor)
            
            daily_diff_str = "-"
            if prev_entry and anchor_entry:
                daily_diff_str = rank_calculator.calculate_diff_text(prev_entry, anchor_entry, include_prefix=False)
            elif anchor_entry:
                daily_diff_str = "履歴なし"
            row.append(daily_diff_str)

            # 2. 〇日比 (Period Diff)
            start_entry = h_map.get(sorted_dates[0]) if sorted_dates else None
            period_diff_str = "-"
            if start_entry and anchor_entry:
                if start_entry == anchor_entry:
                    period_diff_str = "期間中変化なし"
                else:
                    period_diff_str = rank_calculator.calculate_diff_text(start_entry, anchor_entry, include_prefix=False)
            elif anchor_entry:
                period_diff_str = "履歴なし"
            row.append(period_diff_str)

            # 戦績（前日）
            row.append(format_record(prev_entry, anchor_entry))
            
            # 戦績（〇日分）
            row.append(format_record(start_entry, anchor_entry))
            
            vals.append(row)

        # Build Table String manually for alignment
        import unicodedata
        def get_display_width(s):
            """Calculate display width considering full-width characters."""
            width = 0
            for char in str(s):
                eaw = unicodedata.east_asian_width(char)
                # 'W' (Wide) and 'F' (Fullwidth) are 2 cells
                # 'A' (Ambiguous) symbols like ± or ⇒ are usually 1 cell in Discord code blocks
                if eaw in ('W', 'F'):
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
