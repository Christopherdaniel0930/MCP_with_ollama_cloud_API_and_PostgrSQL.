
import os
import uuid

import psycopg
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]


def create_session(user_id: str) -> str:
    """Create a persistent conversation session."""
    session_id = str(uuid.uuid4())

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """
            INSERT INTO public.chat_sessions (session_id, user_id)
            VALUES (%s, %s)
            """,
            (session_id, user_id),
        )

    return session_id


def save_message(session_id: str, role: str, content: str):
    """Persist a user message, assistant response, or tool result."""
    if role not in {"user", "assistant", "tool"}:
        raise ValueError("Unsupported message role")

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """
            INSERT INTO public.chat_messages
                (session_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (session_id, role, content),
        )

        conn.execute(
            """
            UPDATE public.chat_sessions
            SET last_activity_at = NOW()
            WHERE session_id = %s
            """,
            (session_id,),
        )


def get_recent_messages(session_id: str, limit: int = 20):
    """Retrieve recent conversation context."""
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM (
                SELECT id, role, content
                FROM public.chat_messages
                WHERE session_id = %s
                ORDER BY id DESC
                LIMIT %s
            ) recent
            ORDER BY id
            """,
            (session_id, limit),
        ).fetchall()

    return [
        {"role": role, "content": content}
        for role, content in rows
    ]


def save_context(user_id: str, session_id: str,
                 memory_type: str, content: dict,
                 memory_key: str | None = None):
    """Save reusable context from any feature."""
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """
            INSERT INTO public.context_memories
                (user_id, session_id, memory_type,
                 memory_key, content)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user_id,
                session_id,
                memory_type,
                memory_key,
                Jsonb(content),
            ),
        )


def search_context(user_id: str, keyword: str, limit: int = 10):
    """Basic keyword search across saved context."""
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """
            SELECT id, memory_type, memory_key, content
            FROM public.context_memories
            WHERE user_id = %s
              AND (content::text ILIKE %s OR memory_key ILIKE %s)
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()

    return [
        {
            "id": row[0],
            "memory_type": row[1],
            "memory_key": row[2],
            "content": row[3],
        }
        for row in rows
    ]