import logging
import os
import asyncpg
from datetime import datetime, date, time

logger = logging.getLogger(__name__)

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
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        schema_path = os.path.join(base_dir, '..', 'schema.sql')
        
        if not os.path.exists(schema_path):
             if os.path.exists('schema.sql'):
                 schema_path = 'schema.sql'
        
        if os.path.exists(schema_path):
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
                async with self.pool.acquire() as conn:
                    await conn.execute(schema_sql)
                    
                    # Migration for server_id and composite keys
                    try:
                        # 1. Add server_id columns if missing
                        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS server_id BIGINT")
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS server_id BIGINT")
                        await conn.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS server_id BIGINT")
                        
                        # 2. Update Primary Key for users
                        # Check if server_id is part of the PK
                        pk_check = await conn.fetch("""
                            SELECT a.attname
                            FROM   pg_index i
                            JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                            WHERE  i.indrelid = 'users'::regclass AND i.indisprimary;
                        """)
                        pk_columns = [r['attname'] for r in pk_check]
                        
                        if 'server_id' not in pk_columns:
                            logger.info("Migrating 'users' Primary Key to include server_id...")
                            await conn.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_pkey CASCADE")
                            # Set a default value for existing rows (0 or NULL, but PK can't be NULL)
                            # We'll use 0 as a placeholder for migration
                            await conn.execute("UPDATE users SET server_id = 0 WHERE server_id IS NULL")
                            await conn.execute("ALTER TABLE users ADD PRIMARY KEY (server_id, discord_id, riot_id)")

                        # 3. Update Rank History
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS riot_id VARCHAR(255)")
                        await conn.execute("UPDATE rank_history SET server_id = 0 WHERE server_id IS NULL")
                        
                        # Fix FK and Unique constraint
                        await conn.execute("ALTER TABLE rank_history DROP CONSTRAINT IF EXISTS rank_history_user_fkey")
                        await conn.execute("ALTER TABLE rank_history DROP CONSTRAINT IF EXISTS rank_history_discord_id_fkey")
                        await conn.execute("ALTER TABLE rank_history DROP CONSTRAINT IF EXISTS rank_history_server_id_discord_id_riot_id_fetch_date_key")
                        await conn.execute("ALTER TABLE rank_history DROP CONSTRAINT IF EXISTS rank_history_discord_id_riot_id_fetch_date_key")
                        
                        await conn.execute("""
                            ALTER TABLE rank_history 
                            ADD CONSTRAINT rank_history_user_fkey 
                            FOREIGN KEY (server_id, discord_id, riot_id) REFERENCES users(server_id, discord_id, riot_id)
                            ON DELETE CASCADE
                        """)
                        await conn.execute("""
                            ALTER TABLE rank_history 
                            ADD CONSTRAINT rank_history_unique_entry 
                            UNIQUE (server_id, discord_id, riot_id, fetch_date)
                        """)

                        # 4. Migration for Wins/Losses/Games
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS wins INTEGER DEFAULT 0")
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS losses INTEGER DEFAULT 0")
                        await conn.execute("ALTER TABLE rank_history ADD COLUMN IF NOT EXISTS games INTEGER DEFAULT 0")
                        
                        # 5. Migration for Schedules
                        await conn.execute("UPDATE schedules SET server_id = 0 WHERE server_id IS NULL")
                        await conn.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'ENABLED'")
                        await conn.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS output_type VARCHAR(50) DEFAULT 'table'")
                        
                        logger.info("Schema migration checked/applied (server_id & Composite Keys).")
                    except Exception as e:
                        logger.warning(f"Migration warning: {e}")

            logger.info("Database schema initialized.")
        else:
            logger.warning(f"Warning: schema.sql not found at {schema_path}")

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def register_user(self, server_id: int, discord_id: int, riot_id: str, puuid: str):
        query = """
        INSERT INTO users (server_id, discord_id, riot_id, puuid, update_date)
        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
        ON CONFLICT (server_id, discord_id, riot_id) 
        DO UPDATE SET puuid = $4, update_date = CURRENT_TIMESTAMP
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, server_id, discord_id, riot_id, puuid)

    async def get_user_by_discord_id(self, server_id: int, discord_id: int):
        query = "SELECT * FROM users WHERE server_id = $1 AND discord_id = $2"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, server_id, discord_id)

    async def get_user_by_riot_id(self, server_id: int, riot_id: str):
        """Fetch a user by their Riot ID within a specific server."""
        query = "SELECT * FROM users WHERE server_id = $1 AND riot_id = $2"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, server_id, riot_id)

    async def register_schedule(self, server_id: int, schedule_time, channel_id: int, created_by: int, period_days: int, output_type: str = 'table'):
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
        INSERT INTO schedules (server_id, schedule_time, channel_id, created_by, period_days, output_type, status, update_date)
        VALUES ($1, $2, $3, $4, $5, $6, 'ENABLED', CURRENT_TIMESTAMP)
        RETURNING id
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, server_id, schedule_time, channel_id, created_by, period_days, output_type)

    async def get_all_schedules(self):
        query = "SELECT * FROM schedules"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)

    async def get_schedules_by_server(self, server_id: int):
        query = "SELECT * FROM schedules WHERE server_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, server_id)

    async def add_rank_history(self, server_id: int, discord_id: int, riot_id: str, tier: str, rank: str, lp: int, wins: int, losses: int, fetch_date: date):
        games = wins + losses
        query = """
        INSERT INTO rank_history (server_id, discord_id, riot_id, tier, rank, lp, wins, losses, games, fetch_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (server_id, discord_id, riot_id, fetch_date)
        DO UPDATE SET 
            tier = $4, rank = $5, lp = $6, wins = $7, losses = $8, games = $9
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, server_id, discord_id, riot_id, tier, rank, lp, wins, losses, games, fetch_date)

    async def get_rank_history(self, server_id: int, discord_id: int, riot_id: str, start_date: date, end_date: date):
        query = """
        SELECT * FROM rank_history
        WHERE server_id = $1 AND discord_id = $2 AND riot_id = $3 AND fetch_date BETWEEN $4 AND $5
        ORDER BY fetch_date ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, server_id, discord_id, riot_id, start_date, end_date)

    async def get_rank_history_for_graph(self, server_id: int, discord_id: int, riot_id: str, start_date: date):
        query = """
        SELECT fetch_date, tier, rank, lp, wins, losses, games
        FROM rank_history
        WHERE server_id = $1 AND discord_id = $2 AND riot_id = $3 AND fetch_date >= $4
        ORDER BY fetch_date ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, server_id, discord_id, riot_id, start_date)

    async def get_all_users(self):
        query = "SELECT * FROM users"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)

    async def get_users_by_server(self, server_id: int):
        query = "SELECT * FROM users WHERE server_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, server_id)

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

    async def delete_user_by_riot_id(self, server_id: int, riot_id: str):
        query = "DELETE FROM users WHERE server_id = $1 AND riot_id = $2"
        async with self.pool.acquire() as conn:
            await conn.execute(query, server_id, riot_id)

db = Database()
