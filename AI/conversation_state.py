from typing import TypedDict, List, Optional


class AssistantOffer(TypedDict):
    type: str              # e.g. "nearby_info"
    subject: Optional[str] # e.g. "Srawasthipura"
    expires: Optional[int] # unix timestamp or None


class ConversationState(TypedDict):
    last_user_message: Optional[str]
    last_assistant_message: Optional[str]
    entities: dict
    open_offers: List[AssistantOffer]


# app/AI/conversation_state.py

from ..db import get_conversation_messages
import re

async def build_conversation_state(conversation_id: str) -> ConversationState:
    messages = await get_conversation_messages(conversation_id)

    last_user = None
    last_assistant = None

    for m in reversed(messages):
        if not last_user and m["role"] == "user":
            last_user = m["content"]
        if not last_assistant and m["role"] == "assistant":
            last_assistant = m["content"]
        if last_user and last_assistant:
            break

    entities = {}
    open_offers = []

    if last_assistant:
        # Detect assistant offers (generic but extendable)
        if re.search(r"nearby|restaurants|attractions|transport", last_assistant, re.I):
            open_offers.append({
                "type": "nearby_info",
                "subject": extract_location(last_assistant),
                "expires": None
            })

        # Extract locations (simple now, NLP later)
        loc = extract_location(last_assistant)
        if loc:
            entities["location"] = loc

    return {
        "last_user_message": last_user,
        "last_assistant_message": last_assistant,
        "entities": entities,
        "open_offers": open_offers
    }


def extract_location(text: str) -> str | None:
    # Simple heuristic for now
    for place in ["Srawasthipura", "Anuradhapura", "Sri Lanka"]:
        if place.lower() in text.lower():
            return place
    return None
