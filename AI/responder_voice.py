import os
from ollama import Client
import yaml
import json
from dotenv import load_dotenv
import re
import uuid
import base64

load_dotenv()

from ..db import get_conversation_messages

BASE_DIR = os.path.dirname(__file__)
RESPONDER_YAML = os.path.join(BASE_DIR, "responder_prompt_voice.yaml")

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


async def build_responder_prompt(
    user_input: str,
    conversation_id: str,
    planner_output: dict,
    tool_results: dict | None = None,
    include_past_messages: bool = True,
) -> list[dict]:

    with open(RESPONDER_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    tool_results = tool_results or {}

    system_sections: list[str] = []

    description = cfg.get("description")
    if description:
        system_sections.append(str(description).strip())

    def format_section(name: str, data) -> str:
        if data is None:
            return ""
        dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
        return f"{name}:\n{dumped}"

    for key in [
        "identity",
        "personality",
        "conversation_style",
        "self_expression",
        "core_principles",
        "extra_block_system", 
        "voice_output_rules",
        "response_style_rules",
        "response_style_mapping",
        "output_rules",
        "safety_and_accuracy",
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

    if include_past_messages and conversation_id:
        past_messages = await get_conversation_messages(conversation_id)
        if past_messages:
            user_context_sections.append(render_memory(past_messages))

    user_context_sections.append(f"CURRENT USER INPUT:\n{user_input}")

    user_prompt = "\n\n".join(user_context_sections)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

async def call_responder_voice(
    user_input: str,
    conversation_id: str,
    planner_output: dict,
    tool_results: dict,
):
    messages = await build_responder_prompt(
        user_input,
        conversation_id,
        planner_output,
        tool_results,
    )
    buffer = ""

    for part in client.chat(MODEL_NAME, messages=messages, stream=True):
        content = part.get("message", {}).get("content", "")
        if not content:
            continue

        buffer += content

        while True:
            match = EXTRA_RE.search(buffer)
            if not match:
                # No more extras in buffer, keep accumulating
                break

            # Text before the extra
            pre_text = buffer[:match.start()].strip()
            if pre_text:
                yield {"type": "token", "content": pre_text}

            # Extract the extra JSON
            extra_json = match.group(1).strip()
            try:
                extra_data = json.loads(extra_json.replace("'", '"'))
                yield {"type": "extra", "content": extra_data}
            except json.JSONDecodeError:
                yield {"type": "extra", "content": extra_json}  # fallback raw string

            # Remove processed part from buffer
            buffer = buffer[match.end():]

    # Yield any remaining text after the last EXTRA
    final_text = buffer.strip()
    if final_text:
        yield {"type": "token", "content": final_text}
        
    