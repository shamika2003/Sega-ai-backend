
# app/db.py
import aiomysql
import os
import uuid


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Shamika@2003")
DB_NAME = os.getenv("DB_NAME", "segaai")

pool = None  # global pool

async def init_db_pool():
    global pool
    if pool is None:
        pool = await aiomysql.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            autocommit=True,
            charset="utf8mb4",
        )
    return pool


async def save_get_user(user_info: dict):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # Check if user exists
            await cur.execute(
                "SELECT * FROM users WHERE provider=%s AND provider_user_id=%s",
                (user_info["provider"], user_info["provider_user_id"])
            )
            existing_user = await cur.fetchone()
            if existing_user:
                return existing_user

            # Insert new user
            user_id = str(uuid.uuid4())
            await cur.execute(
                """
                INSERT INTO users (id, email, name, avatar_url, provider, provider_user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    user_info["email"],
                    user_info["name"],
                    user_info.get("avatar_url"),
                    user_info["provider"],
                    user_info["provider_user_id"]
                )
            )

            # Fetch and return the new user
            await cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            new_user = await cur.fetchone()
            return new_user
        

# Message operations
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
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # Check if conversation exists
            await cur.execute(
                """
                SELECT id, user_id, session_id
                FROM conversations
                WHERE id = %s
                """,
                (conversation_id,),
            )

            row = await cur.fetchone()

            # If exists → enforce ownership
            if row:
                # Logged-in user
                if user_id:
                    if row["user_id"] and row["user_id"] != user_id:
                        raise PermissionError("Conversation belongs to another user")

                    # Guest → user takeover allowed
                    if row["user_id"] is None and row["session_id"] != session_id:
                        raise PermissionError("Session mismatch")

                # Guest user
                else:
                    if row["user_id"] is not None:
                        raise PermissionError("Conversation owned by a user")
                    if row["session_id"] != session_id:
                        raise PermissionError("Session mismatch")

                # Safe to update
                await cur.execute(
                    """
                    UPDATE conversations
                    SET
                        title = %s,
                        user_id = COALESCE(user_id, %s),
                        session_id = COALESCE(session_id, %s)
                    WHERE id = %s
                    """,
                    (title, user_id, session_id, conversation_id),
                )

            # If not exists → insert
            else:
                await cur.execute(
                    """
                    INSERT INTO conversations (id, title, user_id, session_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (conversation_id, title, user_id, session_id),
                )
        await conn.commit()


async def save_user_message(conversation_id: str, content: str):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'User', %s)",
                (conversation_id, content)
            )

async def save_assistant_message(conversation_id: str, content: str):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'Assistant', %s)",
                (conversation_id, content)
            )
            
async def get_conversation_messages(conversation_id: str):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT
                    m.id,
                    m.role,
                    m.content,
                    c.user_id,
                    c.session_id
                FROM messages AS m
                JOIN conversations AS c
                  ON m.conversation_id = c.id
                WHERE c.id = %s
                ORDER BY m.created_at ASC
                """,
                (conversation_id,)
            )
            return await cur.fetchall()

        
        
async def get_conversation_list(user_id: str):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, title, created_at FROM conversations WHERE user_id=%s ORDER BY created_at DESC",
                (user_id,)
            )
            return await cur.fetchall()