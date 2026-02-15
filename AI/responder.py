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
            "You are currently in VOICE MODE. All responses must be optimized for natural spoken delivery.\n"
            "Speak in a natural, conversational tone as if talking to a real human.\n"
            "Use short, clear sentences suitable for voice output.\n"
            "Do NOT use markdown, bullet points, numbered lists, tables, emojis, JSON, or any formatting that would sound unnatural when spoken.\n"

            "If you need to include factual information, statistics, numbers, summaries, references, URLs, images, code, or any structured data, you MUST insert it inline using %%EXTRA%% blocks exactly where the information becomes relevant in your speech.\n"

            "%%EXTRA%% BLOCK REQUIREMENTS:\n"
            "Each block MUST start with %%EXTRA%% on its own line and end with %%EXTRA%% on its own line.\n"
            "Do NOT nest %%EXTRA%% blocks.\n"
            "Do NOT place all %%EXTRA%% blocks at the beginning or end of the response.\n"
            "Insert each block immediately after the sentence where the structured information is referenced.\n"

            "Inside %%EXTRA%% blocks, full Markdown formatting IS REQUIRED for links and images.\n"
            "All website links MUST be formatted as Markdown clickable links using this format: [Link Text](https://example.com).\n"
            "Raw URLs such as 'url: https://example.com' are NOT allowed.\n"
            "If including images, you MUST format them as Markdown images using this format: ![Alt Text](https://example.com/image.jpg).\n"
            "Do NOT describe images without providing a proper Markdown image link.\n"
            "When listing multiple links, you MUST format them as a Markdown bullet list using '- ' before each link.\n"
            "Each link must appear on its own line.\n"
            "Do NOT place multiple links on the same line.\n"

            "Only include structured, factual, or extraction-relevant content inside the block.\n"
            "Do NOT include conversational text inside %%EXTRA%% blocks.\n"

            "When providing multiple links inside a %%EXTRA%% block, you MUST format them as a Markdown list with each link on a separate line using `- [Text](URL)` format.\n"
            "Do NOT fabricate, guess, or invent URLs.\n"
            "Only include URLs if you are confident they are valid and complete.\n"

            "Failure to follow this formatting exactly will break frontend rendering, so strict compliance is mandatory."
        )

    system_prompt = "\n\n".join(s for s in system_sections if s)

    user_context_sections = []

    if planner_output:
        user_context_sections.append(
            dump_section("PLANNER OUTPUT (READ-ONLY)", planner_output)
        )

    if tool_results:
        # print("Tool results to include in prompt:", tool_results)  # Debug print
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

async def call_responder_text(
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