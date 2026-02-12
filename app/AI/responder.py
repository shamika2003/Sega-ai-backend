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
RESPONDER_YAML = os.path.join(BASE_DIR, "responder_prompt.yaml")

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
            "Speak naturally as if to a human. Do NOT use JSON formatting.\n"
            "Use short, conversational sentences.\n"
            "\n"
            "Whenever you mention a fact, number, summary, or structured data, insert it inline using a %%EXTRA%% block at the exact place it is relevant.\n"
            "**IMPORTANT:** Inside %%EXTRA%% blocks, ignore voice mode restrictions. Treat the content as normal chat/text mode, allowing markdown, lists, numbering, tables, code blocks, or any formatting as needed.\n"
            "Do NOT put all %%EXTRA%% blocks at the start or end. Place them naturally where the information is discussed.\n"
            "\n"
            "Example:\n"
            "The Hercules-Corona Borealis Great Wall stretches for ten billion light-years.\n"
            "%%EXTRA%%\n"
            "This is where my code says that thing:\n"
            "1. Length (light-years): ≈10 billion\n"
            "2. Discovery method: Mapping gamma-ray bursts\n"
            "You can use **bold**, *italics*, code blocks, or tables here as needed.\n"
            "%%EXTRA%%\n"
            "It was discovered by mapping gamma-ray bursts across the sky...\n"
            "\n"
            "You can include multiple %%EXTRA%% blocks wherever necessary, inline with your explanation.\n"
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

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

EXTRA_RE = re.compile(r"%%EXTRA%%\s*(.*?)\s*%%EXTRA%%", re.DOTALL)


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