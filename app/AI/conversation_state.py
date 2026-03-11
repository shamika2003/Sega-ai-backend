from typing import TypedDict, List, Optional

# app/AI/conversation_state.py

from ..db import get_conversation_messages

async def build_conversation_state(conversation_id: str):
    messages = await get_conversation_messages(conversation_id)
    fifth_messages = list(reversed(list(reversed(messages))[:10]))

    if not fifth_messages:
        past_chat = []
    else:
        past_chat = []

        for m in fifth_messages:
            past_chat.append({
                "role": m["role"],
                "content": m["content"]
            })


    return {
        "Past_conversation_history": past_chat,
    }