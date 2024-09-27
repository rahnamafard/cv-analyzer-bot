import json
from datetime import datetime
import asyncpg
import logging
from config import DB_URL

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        self.db_pool = None

    async def get_db_pool(self):
        if self.db_pool is None:
            self.db_pool = await asyncpg.create_pool(DB_URL)
        return self.db_pool

    async def prepare_postgres_database(self):
        try:
            pool = await self.get_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        is_premium BOOLEAN DEFAULT FALSE,
                        cv_count INTEGER DEFAULT 0,
                        last_activity TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS cv_data (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username TEXT,
                        file_id TEXT NOT NULL,
                        analyzed_data TEXT NOT NULL,
                        model TEXT NOT NULL,
                        rating INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS job_positions (
                        position_id SERIAL PRIMARY KEY,
                        position_name TEXT UNIQUE
                    );

                    CREATE TABLE IF NOT EXISTS cv_job_positions (
                        cv_id INTEGER REFERENCES cv_data(id),
                        position_id INTEGER REFERENCES job_positions(position_id),
                        job_position TEXT NOT NULL,
                        PRIMARY KEY (cv_id, position_id)
                    );
                """)
        except Exception as e:
            logger.error(f"Error creating PostgreSQL tables: {e}")
            raise

    async def save_user(self, user_id, username):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, last_activity)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE
                SET username = $2, last_activity = $3
            """, user_id, username, datetime.now())

    async def get_user(self, user_id):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            user_data = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            if user_data:
                return dict(user_data)
            return None

    async def save_cv(self, cv_data):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO cv_data (user_id, username, file_id, analyzed_data, model, rating)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, cv_data['user_id'], cv_data['username'], cv_data['file_id'], 
                cv_data['analyzed_data'], cv_data['model'], cv_data['rating'])
            return result['id']

    async def save_cv_job_positions(self, cv_id, job_positions):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO cv_job_positions (cv_id, job_position)
                VALUES ($1, $2)
            """, [(cv_id, position) for position in job_positions])

    async def update_cv_rating(self, cv_id, rating):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE cv_data
                SET rating = $1
                WHERE id = $2
            """, rating, cv_id)

    async def get_cv_data(self, cv_id):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT * FROM cv_data
                WHERE id = $1
            """, cv_id)
            return dict(result) if result else None

    async def get_cv_job_positions(self, cv_id):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT job_position FROM cv_job_positions
                WHERE cv_id = $1
            """, cv_id)
            return [row['job_position'] for row in results]

    async def get_all_cvs(self):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            results = await conn.fetch('SELECT * FROM cv_data')
            return [dict(row) for row in results]

    async def increment_user_cv_count(self, user_id):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('UPDATE users SET cv_count = cv_count + 1 WHERE user_id = $1', user_id)

    async def get_service_quality_metrics(self):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            ratings = await conn.fetch('SELECT rating FROM cv_data WHERE rating IS NOT NULL')
            ratings = [row['rating'] for row in ratings]

        total_ratings = len(ratings)
        rating_sum = sum(ratings)
        rating_distribution = {i: ratings.count(i) for i in range(1, 6)}

        if total_ratings > 0:
            average_rating = rating_sum / total_ratings
        else:
            average_rating = 0

        return {
            "total_ratings": total_ratings,
            "average_rating": average_rating,
            "rating_distribution": rating_distribution
        }

    async def save_job_position(self, position_name):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO job_positions (position_name)
                VALUES ($1)
                ON CONFLICT (position_name) DO UPDATE
                SET position_name = $1
                RETURNING position_id
            """, position_name)
            return result['position_id']

    async def get_similar_cvs(self, job_position, limit=5):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT c.id, c.analyzed_data, COUNT(DISTINCT cvjp.position_id) as match_count
                FROM cv_data c
                JOIN cv_job_positions cvjp ON c.id = cvjp.cv_id
                JOIN job_positions jp ON cvjp.position_id = jp.position_id
                WHERE jp.position_name = $1
                GROUP BY c.id
                ORDER BY match_count DESC
                LIMIT $2
            """, job_position, limit)
            return [{'cv_id': row['id'], 'analyzed_data': json.loads(row['analyzed_data']), 'match_count': row['match_count']} for row in results]
