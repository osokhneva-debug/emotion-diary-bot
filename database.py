import asyncpg
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import DATABASE_URL


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5  # Ограничиваем количество подключений для бесплатного Supabase
        )
        await self._create_tables()

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    timezone INTEGER DEFAULT 3,
                    check_start_hour INTEGER DEFAULT 9,
                    check_end_hour INTEGER DEFAULT 22,
                    checks_per_day INTEGER DEFAULT 4,
                    onboarding_complete BOOLEAN DEFAULT FALSE
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    category TEXT,
                    emotion TEXT NOT NULL,
                    intensity INTEGER,
                    body_sensation TEXT,
                    reason TEXT,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_checks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    scheduled_time TIMESTAMP NOT NULL,
                    sent BOOLEAN DEFAULT FALSE
                )
            """)

            # Add new columns if they don't exist (for existing databases)
            try:
                await conn.execute("ALTER TABLE entries ADD COLUMN IF NOT EXISTS intensity INTEGER")
                await conn.execute("ALTER TABLE entries ADD COLUMN IF NOT EXISTS body_sensation TEXT")
                await conn.execute("ALTER TABLE entries ADD COLUMN IF NOT EXISTS note TEXT")
                await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_complete BOOLEAN DEFAULT FALSE")
                await conn.execute("ALTER TABLE entries ALTER COLUMN category DROP NOT NULL")
            except Exception:
                pass

    # === Users ===

    async def add_user(self, user_id: int, timezone: int = 3) -> bool:
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    """INSERT INTO users (user_id, timezone) VALUES ($1, $2)
                       ON CONFLICT (user_id) DO NOTHING""",
                    user_id, timezone
                )
                return True
            except Exception:
                return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            return dict(row) if row else None

    async def update_user_timezone(self, user_id: int, timezone: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET timezone = $1 WHERE user_id = $2",
                timezone, user_id
            )

    async def complete_onboarding(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET onboarding_complete = TRUE WHERE user_id = $1",
                user_id
            )

    async def update_user_settings(self, user_id: int, start_hour: int, end_hour: int, checks_per_day: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """UPDATE users SET check_start_hour = $1, check_end_hour = $2, checks_per_day = $3
                   WHERE user_id = $4""",
                start_hour, end_hour, checks_per_day, user_id
            )

    async def get_all_users(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users")
            return [dict(row) for row in rows]

    async def get_all_users_with_settings(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, timezone, check_start_hour, check_end_hour, checks_per_day FROM users"
            )
            return [dict(row) for row in rows]

    # === Entries ===

    async def save_entry(
        self,
        user_id: int,
        emotion: str,
        category: str = None,
        intensity: int = None,
        body_sensation: str = None,
        reason: str = None,
        note: str = None
    ):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO entries (user_id, category, emotion, intensity, body_sensation, reason, note, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                user_id, category, emotion, intensity, body_sensation, reason, note, datetime.now()
            )

    async def get_entries(self, user_id: int, limit: int = 50, offset: int = 0) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT category, emotion, intensity, body_sensation, reason, note, created_at
                   FROM entries WHERE user_id = $1
                   ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
                user_id, limit, offset
            )
            return [dict(row) for row in rows]

    async def get_entries_count(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM entries WHERE user_id = $1", user_id
            )

    # === Statistics ===

    async def get_emotion_stats(self, user_id: int) -> Dict:
        async with self.pool.acquire() as conn:
            top_emotions = await conn.fetch(
                """SELECT emotion, COUNT(*) as count
                   FROM entries WHERE user_id = $1
                   GROUP BY emotion ORDER BY count DESC LIMIT 5""",
                user_id
            )

            top_categories = await conn.fetch(
                """SELECT category, COUNT(*) as count
                   FROM entries WHERE user_id = $1 AND category IS NOT NULL
                   GROUP BY category ORDER BY count DESC LIMIT 5""",
                user_id
            )

            total = await conn.fetchval(
                "SELECT COUNT(*) FROM entries WHERE user_id = $1", user_id
            )

            avg_intensity = await conn.fetchval(
                "SELECT AVG(intensity) FROM entries WHERE user_id = $1 AND intensity IS NOT NULL", user_id
            )

            # Streak calculation
            streak = await self._calculate_streak(conn, user_id)

            return {
                "total": total,
                "top_emotions": [dict(r) for r in top_emotions],
                "top_categories": [dict(r) for r in top_categories],
                "avg_intensity": round(avg_intensity, 1) if avg_intensity else None,
                "streak": streak
            }

    async def _calculate_streak(self, conn, user_id: int) -> int:
        rows = await conn.fetch(
            """SELECT DISTINCT DATE(created_at) as entry_date
               FROM entries WHERE user_id = $1
               ORDER BY entry_date DESC""",
            user_id
        )

        if not rows:
            return 0

        dates = [row['entry_date'] for row in rows]
        today = datetime.now().date()

        if dates[0] != today and dates[0] != today - timedelta(days=1):
            return 0

        streak = 1
        for i in range(1, len(dates)):
            if dates[i - 1] - dates[i] == timedelta(days=1):
                streak += 1
            else:
                break

        return streak

    async def get_weekly_summary(self, user_id: int) -> Dict:
        async with self.pool.acquire() as conn:
            week_ago = datetime.now() - timedelta(days=7)

            total = await conn.fetchval(
                """SELECT COUNT(*) FROM entries
                   WHERE user_id = $1 AND created_at >= $2""",
                user_id, week_ago
            )

            top_categories = await conn.fetch(
                """SELECT category, COUNT(*) as count
                   FROM entries WHERE user_id = $1 AND created_at >= $2 AND category IS NOT NULL
                   GROUP BY category ORDER BY count DESC LIMIT 3""",
                user_id, week_ago
            )

            top_emotions = await conn.fetch(
                """SELECT emotion, COUNT(*) as count
                   FROM entries WHERE user_id = $1 AND created_at >= $2
                   GROUP BY emotion ORDER BY count DESC LIMIT 5""",
                user_id, week_ago
            )

            # Top reasons/triggers
            top_reasons = await conn.fetch(
                """SELECT reason, COUNT(*) as count
                   FROM entries WHERE user_id = $1 AND created_at >= $2 AND reason IS NOT NULL AND reason != ''
                   GROUP BY reason ORDER BY count DESC LIMIT 3""",
                user_id, week_ago
            )

            # Time of day analysis
            time_distribution = await conn.fetch(
                """SELECT
                    CASE
                        WHEN EXTRACT(HOUR FROM created_at) BETWEEN 6 AND 11 THEN 'утро'
                        WHEN EXTRACT(HOUR FROM created_at) BETWEEN 12 AND 17 THEN 'день'
                        WHEN EXTRACT(HOUR FROM created_at) BETWEEN 18 AND 22 THEN 'вечер'
                        ELSE 'ночь'
                    END as time_of_day,
                    COUNT(*) as count
                   FROM entries WHERE user_id = $1 AND created_at >= $2
                   GROUP BY time_of_day ORDER BY count DESC LIMIT 1""",
                user_id, week_ago
            )

            avg_intensity = await conn.fetchval(
                """SELECT AVG(intensity) FROM entries
                   WHERE user_id = $1 AND created_at >= $2 AND intensity IS NOT NULL""",
                user_id, week_ago
            )

            days_with_entries = await conn.fetchval(
                """SELECT COUNT(DISTINCT DATE(created_at))
                   FROM entries WHERE user_id = $1 AND created_at >= $2""",
                user_id, week_ago
            )

            return {
                "total": total,
                "top_categories": [dict(r) for r in top_categories],
                "top_emotions": [dict(r) for r in top_emotions],
                "top_reasons": [dict(r) for r in top_reasons],
                "peak_time": time_distribution[0]['time_of_day'] if time_distribution else None,
                "avg_intensity": round(avg_intensity, 1) if avg_intensity else None,
                "days_with_entries": days_with_entries
            }

    # === Scheduled Checks ===

    async def save_scheduled_checks(self, user_id: int, check_times: List[datetime]):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM scheduled_checks WHERE user_id = $1 AND sent = FALSE",
                user_id
            )
            for check_time in check_times:
                await conn.execute(
                    "INSERT INTO scheduled_checks (user_id, scheduled_time) VALUES ($1, $2)",
                    user_id, check_time
                )

    async def add_delayed_check(self, user_id: int, delay_minutes: int = 15):
        """Add a delayed check (for 'Remind me later' feature)"""
        async with self.pool.acquire() as conn:
            delayed_time = datetime.now() + timedelta(minutes=delay_minutes)
            await conn.execute(
                "INSERT INTO scheduled_checks (user_id, scheduled_time) VALUES ($1, $2)",
                user_id, delayed_time
            )

    async def skip_today_checks(self, user_id: int):
        """Mark all today's unsent checks as sent (skip)"""
        async with self.pool.acquire() as conn:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            await conn.execute(
                """UPDATE scheduled_checks SET sent = TRUE
                   WHERE user_id = $1 AND sent = FALSE
                   AND scheduled_time >= $2 AND scheduled_time < $3""",
                user_id, today_start, today_end
            )

    async def get_pending_checks(self, current_time: datetime) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, user_id FROM scheduled_checks
                   WHERE sent = FALSE AND scheduled_time <= $1""",
                current_time
            )
            return [dict(row) for row in rows]

    async def mark_check_sent(self, check_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE scheduled_checks SET sent = TRUE WHERE id = $1",
                check_id
            )


db = Database()
