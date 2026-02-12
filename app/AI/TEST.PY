import os
from ollama import Client
import yaml
import json
from dotenv import load_dotenv

load_dotenv()

from ..db import get_conversation_messages

BASE_DIR = os.path.dirname(__file__)
RESPONDER_YAML = os.path.join(BASE_DIR, "responder_prompt.yaml")

API_KEY = "9dca452ca8ff4bdcbad638dce38edb3e.6wrp2ylkOaocRcRUFPN88d-e"
MODEL_NAME = "gpt-oss:120b-cloud"

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {API_KEY}"}
)

def dump_section(title: str, data) -> str:
    if not data:
        return ""
    if isinstance(data, (dict, list)):
        body = yaml.dump(data, sort_keys=False).strip()
    else:
        body = str(data).strip()
    return f"{title}:\n{body}\n"

def render_memory(messages: list[dict]) -> str:
    if not messages:
        return ""
    lines = []
    for m in messages:
        lines.append(f"{m['role']}: {m['content']}")
    return "PAST CONVERSATION:\n" + "\n".join(lines) + "\n"

async def build_responder_prompt(
    user_input: str,
    conversation_id: str,
    planner_output: dict,
    response_mode: str,
    tool_results: dict | None = None,
    include_past_messages: bool = True,
) -> list[dict]:

    with open(RESPONDER_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    tool_results = tool_results or {}

    system_sections = []

    system_sections.append(cfg.get("description", "").strip())

    system_sections.append(dump_section("IDENTITY", cfg.get("identity")))
    system_sections.append(dump_section("PERSONALITY", cfg.get("personality")))

    system_sections.append(dump_section("CONVERSATION STYLE", cfg.get("conversation_style")))
    system_sections.append(dump_section("SELF-EXPRESSION", cfg.get("self_expression")))
    system_sections.append(dump_section("CORE PRINCIPLES", cfg.get("core_principles")))
    system_sections.append(dump_section("RESPONSE STYLE RULES", cfg.get("response_style_rules")))
    system_sections.append(dump_section("RESPONSE STYLE DEFINITIONS", cfg.get("response_style_mapping")))
    system_sections.append(dump_section("OUTPUT RULES", cfg.get("output_rules")))
    system_sections.append(dump_section("SAFETY AND ACCURACY", cfg.get("safety_and_accuracy")))

    # --- Response Mode Control ---
    if response_mode == "voice_stream":
        system_sections.append(
            "VOICE MODE INSTRUCTIONS:\n"
            "Respond as natural spoken dialogue.\n"
            "Do NOT use markdown, bullet points, tables, code blocks, emojis or structured formatting.\n"
            "Use short, conversational sentences.\n"
            "Write as if you are speaking aloud to a human.\n"
            "Avoid symbols that would sound unnatural when read by text-to-speech.\n"
        )
    else:
        system_sections.append(
            "TEXT MODE INSTRUCTIONS:\n"
            "Formatting such as markdown and structured responses is allowed when useful.\n"
        )


    system_prompt = "\n\n".join(s for s in system_sections if s)

    user_context_sections = []

    if planner_output:
        user_context_sections.append(
            dump_section("PLANNER OUTPUT (READ-ONLY)", planner_output)
        )

    if tool_results:
        print("Tool results to include in prompt:", tool_results)  # Debug print
        user_context_sections.append(
            dump_section("TOOL RESULTS (READ-ONLY)", tool_results)
        )

    if include_past_messages and conversation_id:
        past_messages = await get_conversation_messages(conversation_id)
        if past_messages:
            user_context_sections.append(render_memory(past_messages))

    user_context_sections.append(f"CURRENT USER INPUT:\n{user_input}")

    user_prompt = "\n\n".join(user_context_sections)

    # print("SYSTEM PROMPT:", system_prompt)
    # print("USER PROMPT:", user_prompt)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
   
async def call_responder(
    user_input: str,
    conversation_id: str,
    planner_output: dict,
    tool_results: dict,
    response_mode: str,
):
    messages = await build_responder_prompt(
        user_input,
        conversation_id,
        planner_output,
        response_mode,
        tool_results,
    )

    for part in client.chat(MODEL_NAME, messages=messages, stream=True):
        yield part["message"]["content"]
