import os
from ollama import Client
import yaml
from dotenv import load_dotenv
import re

load_dotenv()

from ..db import get_conversation_messages

BASE_DIR = os.path.dirname(__file__)
RESPONDER_YAML = os.path.join(BASE_DIR, "responder_prompt_text.yaml")
RESPONDER_MAIN_YAML = os.path.join(BASE_DIR, "responder_prompt_main.yaml")

API_KEY = "9dca452ca8ff4bdcbad638dce38edb3e.6wrp2ylkOaocRcRUFPN88d-e"
MODEL_NAME = "gpt-oss:120b-cloud"

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {API_KEY}"}
)

# Regex to detect multiple %%EXTRA%% blocks in content
EXTRA_RE = re.compile(r"%%EXTRA%%\s*(.*?)\s*%%EXTRA%%", re.DOTALL)


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


import yaml

async def build_responder_prompt(
    user_input: str,
    conversation_id: str,
    planner_output: dict,
    vision_context: str,
    tool_results: dict | None = None,
    include_past_messages: bool = True,
) -> list[dict]:
    

    with open(RESPONDER_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
        
    with open(RESPONDER_MAIN_YAML, "r", encoding="utf-8") as f:
        main_cfg = yaml.safe_load(f) or {}

    tool_results = tool_results or {}

    def format_section(name: str, data) -> str:
        if data is None:
            return ""
        dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
        return f"{name}:\n{dumped}"

    system_sections: list[str] = []

    description = main_cfg.get("description")
    if description:
        system_sections.append(str(description).strip())

    for key in [
        "identity",
        "personality",
        "emotional_state",
        "self_expression",
        "core_principles",
        "core_principles",
        "response_style_mapping",
        "user_focus",
    ]:
        section = format_section(key.upper().replace("_", " "), main_cfg.get(key))
        if section:
            system_sections.append(section)
            
    for key in [
        "conversation_style",
        "output_rules",
    ]:
        section = format_section(key.upper().replace("_", " "), cfg.get(key))
        if section:
            system_sections.append(section)

    system_prompt = "\n\n".join(system_sections)

    user_context_sections: list[str] = []

    if planner_output:
        user_context_sections.append(
            format_section("PLANNER OUTPUT (READ-ONLY)", planner_output)
        )

    if tool_results:
        user_context_sections.append(
            format_section("TOOL RESULTS (READ-ONLY)", tool_results)
        )

    if vision_context:
        user_context_sections.append(
            f"""
            VISUAL FILE ANALYSIS (AUTO-GENERATED CONTEXT):
            The user uploaded images or files. A vision model analyzed them and produced
            the following description of their visual content.

            Use this information when answering questions related to the files.

            --- BEGIN VISUAL ANALYSIS ---
            {vision_context}
            --- END VISUAL ANALYSIS ---
            """.strip()
        )

    if include_past_messages and conversation_id:
        past_messages = await get_conversation_messages(conversation_id)
        if past_messages:
            user_context_sections.append(render_memory(past_messages))

    user_context_sections.append(f"CURRENT USER INPUT:\n{user_input}")

    user_prompt = "\n\n".join(user_context_sections)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]


async def call_responder_text(
    user_input: str,
    conversation_id: str,
    planner_output: dict,
    tool_results: dict,
    vision_context: str,
):
    messages = await build_responder_prompt(
        user_input,
        conversation_id,
        planner_output,
        vision_context,
        tool_results,
    )
    for part in client.chat(MODEL_NAME, messages=messages, stream=True):
        yield part["message"]["content"]