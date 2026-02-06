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
                    
                    # Migration for composite key (discord_id, riot_id)
                    try:
                        # 1. Check if discord_id is the only PK
                        pk_check = await conn.fetchrow("""
                            SELECT a.attname
                            FROM   pg_index i
                            JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                            WHERE  i.indrelid = 'users'::regclass AND i.indisprimary;
                        """)
                        
                        # If we have only one PK (discord_id), we need to migrate
                        # Simple check: if we can't find multiple PKs, or if it's just discord_id
                        # Better to just try to swap PK if it's not already composite
                        
                        # We'll try to drop the old constraint if it's named 'users_pkey'
                        await conn.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_pkey CASCADE")
                        await conn.execute("ALTER TABLE users ADD PRIMARY KEY (discord_id, riot_id)")
                        
                        # Migration for rank_history
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS riot_id VARCHAR(255)")
                        # If riot_id is null in rank_history, try to populate it from users (heuristic)
                        await conn.execute("""
                            UPDATE rank_history rh
                            SET riot_id = u.riot_id
                            FROM users u
                            WHERE rh.discord_id = u.discord_id AND rh.riot_id IS NULL
                        """)
                        # Add composite FK to rank_history
                        # First drop old FK if exists
                        await conn.execute("ALTER TABLE rank_history DROP CONSTRAINT IF EXISTS rank_history_discord_id_fkey")
                        await conn.execute("ALTER TABLE rank_history DROP CONSTRAINT IF EXISTS rank_history_user_fkey")
                        await conn.execute("""
                            ALTER TABLE rank_history 
                            ADD CONSTRAINT rank_history_user_fkey 
                            FOREIGN KEY (discord_id, riot_id) REFERENCES users(discord_id, riot_id)
                            ON DELETE CASCADE
                        """)
                        
                        # Migration for wins/losses/games if they don't exist
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS wins INTEGER DEFAULT 0")
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS losses INTEGER DEFAULT 0")
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS games INTEGER DEFAULT 0")
                        
                        # Migration for schedules
                        await conn.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'ENABLED'")
                        await conn.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS output_type VARCHAR(50) DEFAULT 'table'")
                        
                        print("Schema migration checked/applied (Composite Key & Schedules).")
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
        ON CONFLICT (discord_id, riot_id) 
        DO UPDATE SET puuid = $3, update_date = CURRENT_TIMESTAMP
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, discord_id, riot_id, puuid)

    async def get_user_by_discord_id(self, discord_id: int):
        query = "SELECT * FROM users WHERE discord_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, discord_id) # Returns potentially multiple

    async def get_user_by_riot_id(self, riot_id: str):
        """Fetch a user by their Riot ID."""
        query = "SELECT * FROM users WHERE riot_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, riot_id)

    async def register_schedule(self, schedule_time, channel_id: int, created_by: int, period_days: int, output_type: str = 'table'):
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
        INSERT INTO schedules (schedule_time, channel_id, created_by, period_days, output_type, status, update_date)
        VALUES ($1, $2, $3, $4, $5, 'ENABLED', CURRENT_TIMESTAMP)
        RETURNING id
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, schedule_time, channel_id, created_by, period_days, output_type)

    async def get_all_schedules(self):
        query = "SELECT * FROM schedules"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)

    async def add_rank_history(self, discord_id: int, riot_id: str, tier: str, rank: str, lp: int, wins: int, losses: int, fetch_date: date):
        # Calculate games
        games = wins + losses
        
        query = """
        INSERT INTO rank_history (discord_id, riot_id, tier, rank, lp, wins, losses, games, fetch_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (discord_id, riot_id, fetch_date)
        DO UPDATE SET 
            tier = $3, rank = $4, lp = $5, wins = $6, losses = $7, games = $8
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, discord_id, riot_id, tier, rank, lp, wins, losses, games, fetch_date)

    async def get_rank_history(self, discord_id: int, riot_id: str, start_date: date, end_date: date):
        query = """
        SELECT * FROM rank_history
        WHERE discord_id = $1 AND riot_id = $2 AND fetch_date BETWEEN $3 AND $4
        ORDER BY fetch_date ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, discord_id, riot_id, start_date, end_date)

    async def get_rank_history_for_graph(self, discord_id: int, riot_id: str, start_date: date):
        """Fetch rank history from start_date up to today, ordered by date."""
        query = """
        SELECT fetch_date, tier, rank, lp, wins, losses, games
        FROM rank_history
        WHERE discord_id = $1 AND riot_id = $2 AND fetch_date >= $3
        ORDER BY fetch_date ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, discord_id, riot_id, start_date)

            
    async def get_all_users(self):
        query = "SELECT * FROM users"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)
    async def delete_schedule(self, schedule_id: int):
        query = "DELETE FROM schedules WHERE id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, schedule_id)

    async def update_schedule(self, schedule_id: int, schedule_time, channel_id: int, period_days: int, output_type: str = 'table'):
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
        SET schedule_time = $2, channel_id = $3, period_days = $4, output_type = $5, update_date = CURRENT_TIMESTAMP
        WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, schedule_id, schedule_time, channel_id, period_days, output_type)

    async def set_schedule_status(self, schedule_id: int, status: str):
        query = """
        UPDATE schedules 
        SET status = $2, update_date = CURRENT_TIMESTAMP
        WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, schedule_id, status)

    async def get_schedule_by_id(self, schedule_id: int):
        query = "SELECT * FROM schedules WHERE id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, schedule_id)

    async def delete_user_by_riot_id(self, riot_id: str):
        query = "DELETE FROM users WHERE riot_id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, riot_id)

db = Database()
