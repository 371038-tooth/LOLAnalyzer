import os
import asyncpg
from datetime import datetime, date, time

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        # Support both custom URLs and Railway default URLs
        dsn = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
        
        if dsn:
            self.pool = await asyncpg.create_pool(dsn)
        else:
            # Support both 'DB_' and 'PG' prefixes (Railway uses PGxxx)
            self.pool = await asyncpg.create_pool(
                host=os.getenv('PGHOST') or os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('PGPORT') or os.getenv('DB_PORT', 5432)),
                user=os.getenv('PGUSER') or os.getenv('DB_USER', 'postgres'),
                password=os.getenv('PGPASSWORD') or os.getenv('DB_PASSWORD', 'password'),
                database=os.getenv('PGDATABASE') or os.getenv('DB_NAME', 'railway')
            )
        
        # Initialize schema
        await self.initialize()

    async def initialize(self):
        # Determine path to schema.sql relative to this file
        # src/database.py -> ../../schema.sql
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        schema_path = os.path.join(base_dir, '..', 'schema.sql')
        
        # If running from src/main.py, base dir might be different depending on cwd
        # Try finding schema.sql in likely locations
        if not os.path.exists(schema_path):
             # Try current directory or parent
             if os.path.exists('schema.sql'):
                 schema_path = 'schema.sql'
        
        if os.path.exists(schema_path):
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
                async with self.pool.acquire() as conn:
                    await conn.execute(schema_sql)
                    
                    # Migration for wins/losses/games if they don't exist
                    # This check is basic but effective for adding columns if missing
                    try:
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS wins INTEGER DEFAULT 0")
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS losses INTEGER DEFAULT 0")
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS games INTEGER DEFAULT 0")
                        print("Schema migration checked/applied.")
                    except Exception as e:
                        print(f"Migration warning: {e}")

            print("Database schema initialized.")
        else:
            print(f"Warning: schema.sql not found at {schema_path}")

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def register_user(self, discord_id: int, riot_id: str, puuid: str):
        query = """
        INSERT INTO users (discord_id, riot_id, puuid, update_date)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        ON CONFLICT (discord_id) 
        DO UPDATE SET riot_id = $2, puuid = $3, update_date = CURRENT_TIMESTAMP
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, discord_id, riot_id, puuid)

    async def get_user_by_discord_id(self, discord_id: int):
        query = "SELECT * FROM users WHERE discord_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, discord_id)

    async def register_schedule(self, schedule_time, channel_id: int, created_by: int, period_days: int):
        # schedule_time might be string 'HH:MM' or 'HH:MM:SS'
        if isinstance(schedule_time, str):
            # Try to parse HH:MM or HH:MM:SS
            try:
                if len(schedule_time.split(':')) == 2:
                    dt = datetime.strptime(schedule_time, "%H:%M")
                else:
                    dt = datetime.strptime(schedule_time, "%H:%M:%S")
                schedule_time = dt.time()
            except ValueError as e:
                raise ValueError(f"Invalid time format: {schedule_time}") from e

        query = """
        INSERT INTO schedules (schedule_time, channel_id, created_by, period_days, update_date)
        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
        RETURNING id
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, schedule_time, channel_id, created_by, period_days)

    async def get_all_schedules(self):
        query = "SELECT * FROM schedules"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)

    async def add_rank_history(self, discord_id: int, tier: str, rank: str, lp: int, wins: int, losses: int, fetch_date: date):
        # Calculate games
        games = wins + losses
        
        query = """
        INSERT INTO rank_history (discord_id, tier, rank, lp, wins, losses, games, fetch_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, discord_id, tier, rank, lp, wins, losses, games, fetch_date)

    async def get_rank_history(self, discord_id: int, start_date: date, end_date: date):
        query = """
        SELECT * FROM rank_history
        WHERE discord_id = $1 AND fetch_date BETWEEN $2 AND $3
        ORDER BY fetch_date ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, discord_id, start_date, end_date)
            
    async def get_all_users(self):
        query = "SELECT * FROM users"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)
    async def delete_schedule(self, schedule_id: int):
        query = "DELETE FROM schedules WHERE id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, schedule_id)

    async def update_schedule(self, schedule_id: int, schedule_time, channel_id: int, period_days: int):
        if isinstance(schedule_time, str):
            try:
                if len(schedule_time.split(':')) == 2:
                    dt = datetime.strptime(schedule_time, "%H:%M")
                else:
                    dt = datetime.strptime(schedule_time, "%H:%M:%S")
                schedule_time = dt.time()
            except ValueError as e:
                raise ValueError(f"Invalid time format: {schedule_time}") from e

        query = """
        UPDATE schedules 
        SET schedule_time = $2, channel_id = $3, period_days = $4, update_date = CURRENT_TIMESTAMP
        WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, schedule_id, schedule_time, channel_id, period_days)

    async def get_schedule_by_id(self, schedule_id: int):
        query = "SELECT * FROM schedules WHERE id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, schedule_id)

db = Database()
