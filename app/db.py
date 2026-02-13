# app/db.py
import os
import uuid
import asyncpg
from urllib.parse import urlparse

DATABASE_URL = os.getenv("DATABASE_URL")  # Render provides this automatically

# Parse DATABASE_URL
if DATABASE_URL:
    result = urlparse(DATABASE_URL)
    DB_HOST = result.hostname
    DB_PORT = result.port or 5432
    DB_USER = result.username
    DB_PASSWORD = result.password
    DB_NAME = result.path.lstrip("/")
else:
    # fallback for local dev
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "Shamika@2003")
    DB_NAME = os.getenv("DB_NAME", "segaai")

pool: asyncpg.Pool | None = None  # global pool

async def init_db_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )
    return pool

async def save_get_user(user_info: dict):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        # Check if user exists
        existing_user = await conn.fetchrow(
            "SELECT * FROM users WHERE provider=$1 AND provider_user_id=$2",
            user_info["provider"],
            user_info["provider_user_id"]
        )
        if existing_user:
            return dict(existing_user)

        # Insert new user
        user_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO users (id, email, name, avatar_url, provider, provider_user_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            user_id,
            user_info["email"],
            user_info["name"],
            user_info.get("avatar_url"),
            user_info["provider"],
            user_info["provider_user_id"]
        )

        # Fetch and return the new user
        new_user = await conn.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
        return dict(new_user)


async def ensure_conversation(
    conversation_id: str,
    title: str,
    user_id: str | None = None,
    session_id: str | None = None,
):
    if not user_id and not session_id:
        raise ValueError("Either user_id or session_id is required")

    pool = await init_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, user_id, session_id FROM conversations WHERE id=$1",
            conversation_id
        )

        if row:
            # Logged-in user
            if user_id:
                if row["user_id"] and row["user_id"] != user_id:
                    raise PermissionError("Conversation belongs to another user")
                if row["user_id"] is None and row["session_id"] != session_id:
                    raise PermissionError("Session mismatch")
            # Guest user
            else:
                if row["user_id"] is not None:
                    raise PermissionError("Conversation owned by a user")
                if row["session_id"] != session_id:
                    raise PermissionError("Session mismatch")

            # Safe to update
            await conn.execute(
                """
                UPDATE conversations
                SET title=$1,
                    user_id=COALESCE(user_id, $2),
                    session_id=COALESCE(session_id, $3)
                WHERE id=$4
                """,
                title, user_id, session_id, conversation_id
            )
        else:
            # Insert new conversation
            await conn.execute(
                """
                INSERT INTO conversations (id, title, user_id, session_id)
                VALUES ($1, $2, $3, $4)
                """,
                conversation_id, title, user_id, session_id
            )


async def save_user_message(conversation_id: str, content: str):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'User', $2)",
            conversation_id,
            content
        )

async def save_assistant_message(conversation_id: str, content: str):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'Assistant', $2)",
            conversation_id,
            content
        )

async def get_conversation_messages(conversation_id: str):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                m.id,
                m.role,
                m.content,
                c.user_id,
                c.session_id
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.id=$1
            ORDER BY m.created_at ASC
            """,
            conversation_id
        )
        return [dict(r) for r in rows]

async def get_conversation_list(user_id: str):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, title, created_at FROM conversations WHERE user_id=$1 ORDER BY created_at DESC",
            user_id
        )
        return [dict(r) for r in rows]
